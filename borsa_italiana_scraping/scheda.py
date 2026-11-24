"""Scraping della pagina scheda di uno strumento su Borsa Italiana."""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from bs4 import BeautifulSoup, Tag

from .eccezioni import DatiNonDisponibili, StrumentoNonRisolto, StrumentoNonTrovato
from .sessione import Sessione
from .tipi import (
    Azionista,
    ContattiSocieta,
    DatoSocietario,
    Dirigente,
    IndirizzoSocieta,
    ProfiloSocieta,
    SchedaStrumento,
)


# URL universale (segue redirect)
_URL_SCHEDA = "https://www.borsaitaliana.it/borsa/search/scheda.html"

# URL dati completi
_URL_DATI_COMPLETI_BOND = "https://www.borsaitaliana.it/borsa/obbligazioni/mot/btp/" "dati-completi.html"
_URL_DATI_COMPLETI_AZIONE = "https://www.borsaitaliana.it/borsa/azioni/dati-completi.html"


# ------------------------------------------------------------------
# Utilità parsing numeri
# ------------------------------------------------------------------


def _pulisci_testo(testo: str) -> str:
    """Rimuove spazi extra, newline e caratteri non stampabili."""
    return " ".join(testo.split()).strip()


def _parsa_numero(testo: str, lingua: str = "en") -> Decimal | None:
    """Converte una stringa numerica in Decimal, gestendo formati EN/IT.

    - EN: ``1,234.56`` → virgola=migliaia, punto=decimale
    - IT: ``1.234,56`` → punto=migliaia, virgola=decimale
    """
    if not testo:
        return None
    testo = _pulisci_testo(testo)
    # Rimuovi simboli di valuta e percentuali
    testo = testo.replace("€", "").replace("%", "").replace("$", "").strip()
    # Gestisci il segno meno tipografico
    testo = testo.replace("−", "-").replace("–", "-")

    if not testo or testo == "-" or testo.lower() in ("n.a.", "n/a", "n.d.", "--"):
        return None

    try:
        if lingua == "it":
            # Formato IT: 1.234,56 → rimuovi punti migliaia, virgola → punto decimale
            testo = testo.replace(".", "").replace(",", ".")
        else:
            # Formato EN: 1,234.56 → rimuovi virgole migliaia
            testo = testo.replace(",", "")
        return Decimal(testo)
    except (InvalidOperation, ValueError):
        return None


# Unambiguous formats: ``%Y`` needs exactly 4 digits, so none of these can
# swallow a 2-digit-year date. Valid for both page languages.
_FORMATI_DATA_4_CIFRE = ("%d/%m/%Y", "%Y/%m/%d", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y", "%m/%d/%Y")

# Borsa Italiana writes 2-digit-year dates in a language-dependent order:
# ``?lang=it`` → ``dd/mm/yy`` (15/07/27), ``?lang=en`` → ``yy/mm/dd`` (27/07/15).
# The page language's order comes first; the other one is only a last resort.
_FORMATI_DATA: dict[str, tuple[str, ...]] = {
    "it": _FORMATI_DATA_4_CIFRE + ("%d/%m/%y", "%y/%m/%d"),
    "en": _FORMATI_DATA_4_CIFRE + ("%y/%m/%d", "%d/%m/%y"),
}


def _parsa_data(testo: str, lingua: str) -> date | None:
    """Parse a Borsa Italiana date, using the page language for 2-digit years.

    Args:
        testo: raw date text (``15/07/27``, ``27/07/15``, ``06/11/2026``, …).
        lingua: language of the page the text comes from (``"it"`` or ``"en"``;
            anything else is treated as ``"en"``, like the number parser).
    """
    testo = _pulisci_testo(testo)
    if not testo or testo == "-":
        return None
    formati = _FORMATI_DATA["it"] if lingua.lower() == "it" else _FORMATI_DATA["en"]
    for fmt in formati:
        try:
            return datetime.strptime(testo, fmt).date()
        except ValueError:
            continue
    return None


def _parsa_data_scheda(testo: str, lingua: str) -> date | None:
    """Parsa una data dalla pagina scheda (formati vari).

    Supporta sia anni a 4 cifre (``dd/mm/YYYY``) che a 2 cifre, il cui ordine
    dipende dalla lingua della pagina (``it``: ``dd/mm/yy``, ``en``: ``yy/mm/dd``).
    """
    return _parsa_data(testo, lingua)


def _parsa_percentuale(testo: str, lingua: str = "en") -> Decimal | None:
    """Parsa un valore percentuale, rimuovendo il simbolo %."""
    if not testo:
        return None
    testo = testo.replace("%", "").strip()
    return _parsa_numero(testo, lingua)


# ------------------------------------------------------------------
# Estrazione valori dalla pagina
# ------------------------------------------------------------------


def _trova_valore(soup: BeautifulSoup, etichette: list[str], esatta: bool = False) -> str | None:
    """Cerca coppie chiave-valore nella pagina.

    Le pagine di Borsa Italiana usano layout con label in <span>/<strong>
    seguite dal valore nella cella/div successiva.

    Con ``esatta=True`` l'etichetta deve coincidere con il testo della cella: un'etichetta
    generica come «Valuta» non deve prendere «Valuta di Denominazione».
    """
    testo_pagina = soup.get_text(" ", strip=True).lower()

    def corrisponde(testo: str) -> bool:
        testo = testo.lower()
        return testo == etichetta_lower if esatta else (testo == etichetta_lower or etichetta_lower in testo)

    for etichetta in etichette:
        etichetta_lower = etichetta.lower()
        if etichetta_lower not in testo_pagina:
            continue

        # Strategia 1: cerco <span>/<strong> con il testo dell'etichetta
        for tag in soup.find_all(["span", "strong", "td", "th"]):
            tag_text = _pulisci_testo(tag.get_text())
            if corrisponde(tag_text):
                # Il valore è nel sibling successivo o nel parent → sibling
                sibling = tag.find_next_sibling()
                if sibling:
                    val = _pulisci_testo(sibling.get_text())
                    if val and val != "-":
                        return val

                # Oppure: il valore è nel tag <td> successivo (layout tabellare)
                if tag.name in ("td", "th"):
                    next_td = tag.find_next_sibling("td")
                    if next_td:
                        val = _pulisci_testo(next_td.get_text())
                        if val and val != "-":
                            return val

                # Oppure: il tag è dentro un <td>, e il valore è nel <td> successivo
                parent_td = tag.find_parent("td")
                if parent_td:
                    next_td = parent_td.find_next_sibling("td")
                    if next_td:
                        val = _pulisci_testo(next_td.get_text())
                        if val and val != "-":
                            return val

                parent_tr = tag.find_parent("tr")
                if parent_tr:
                    tds = parent_tr.find_all("td")
                    for i, td in enumerate(tds):
                        if corrisponde(_pulisci_testo(td.get_text())):
                            if i + 1 < len(tds):
                                val = _pulisci_testo(tds[i + 1].get_text())
                                if val and val != "-":
                                    return val

    return None


def _trova_prezzo_principale(soup: BeautifulSoup, lingua: str) -> Decimal | None:
    """Estrae il prezzo principale dalla pagina (grande, in evidenza)."""
    # Cerca il container summary-value (contiene prezzo + variazione %)
    for classe in ("summary-value", "t-text -black-c", "last-price"):
        tag = soup.find(class_=re.compile(classe, re.I))
        if tag:
            # Se il tag ha figli <span>, il prezzo è nel primo (il secondo è la variazione %)
            figli_span = tag.find_all("span")
            if figli_span:
                val = _parsa_numero(_pulisci_testo(figli_span[0].get_text()), lingua)
                if val:
                    return val
            # Altrimenti prova il testo diretto
            val = _parsa_numero(_pulisci_testo(tag.get_text()), lingua)
            if val:
                return val

    # Cerca label "Last Price" / "Ultimo Prezzo" / "Price" / "Prezzo"
    etichette = ["Last Price", "Ultimo Prezzo", "Price", "Prezzo", "Last", "Prezzo Ufficiale", "Official Price"]
    val_str = _trova_valore(soup, etichette)
    if val_str:
        val = _parsa_numero(val_str, lingua)
        if val:
            return val

    return None


def _determina_tipo(soup: BeautifulSoup, url_finale: str) -> str:
    """Determina il tipo di strumento dalla pagina."""
    url_lower = url_finale.lower()
    if "/obbligazioni/" in url_lower or "/mot/" in url_lower:
        return "obbligazione"
    if "/etf/" in url_lower or "/etfplus/" in url_lower:
        return "etf"
    if "/fondi/" in url_lower:
        return "fondo"
    if "/azioni/" in url_lower:
        return "azione"
    # Controlla anche il contenuto testuale
    testo = soup.get_text(" ", strip=True).lower()
    if "obbligazione" in testo or "bond" in testo or "coupon" in testo:
        return "obbligazione"
    if "etf" in testo:
        return "etf"
    return "azione"


def _estrai_nome(soup: BeautifulSoup) -> str:
    """Estrae il nome dello strumento dalla pagina."""
    # Cerca il tag <h1>
    h1 = soup.find("h1")
    if h1:
        nome = _pulisci_testo(h1.get_text())
        if nome:
            return nome
    # Fallback: titolo della pagina
    title = soup.find("title")
    if title:
        return _pulisci_testo(title.get_text()).split("|")[0].strip()
    return "Sconosciuto"


def _estrai_mercato(soup: BeautifulSoup, lingua: str, url_finale: str | None = None) -> str:
    """Estrae il mercato di negoziazione.

    Fallback: deriva dal path dell'URL finale (``/borsa/obbligazioni/eurotlx/scheda/…``
    → ``EUROTLX``). Mai inventare un mercato di default: se non ricavabile, ``""``
    (il chiamante omette il campo).
    """
    etichette = ["Market", "Mercato", "Mercato di quotazione", "Quotation Market", "Market Segment"]
    val = _trova_valore(soup, etichette)
    if val:
        return val
    if url_finale and "/scheda/" in url_finale:
        segs = [s for s in url_finale.split("?")[0].split("/") if s]
        non_mercato = {
            "borsa",
            "scheda",
            "obbligazioni",
            "azioni",
            "etf",
            "etc-etn",
            "cw-e-certificates",
            "fondi",
            "fondi-chiusi",
        }
        try:
            i, j = segs.index("borsa"), segs.index("scheda")
        except ValueError:
            return ""
        mid = [s for s in segs[i + 1 : j] if s not in non_mercato]
        if mid:
            return "/".join(s.upper() for s in mid)
    return ""


def _estrai_valuta(soup: BeautifulSoup, lingua: str) -> tuple[str, str | None]:
    """Estrae la valuta di negoziazione e liquidazione.

    Il campo "Negotiation Currency/ Settlement currency" ha formato
    ``EUR/EUR`` o ``USD/EUR``. Restituisce (negoziazione, liquidazione).
    Se il campo ha un solo valore, liquidazione è None.

    La valuta di *denominazione* («Valuta di Denominazione» / «Currency Denomination»,
    sulle schede ETF/ETC) non è la valuta di negoziazione: un ETC denominato in USD si
    negozia in EUR su Borsa Italiana. Per questo l'etichetta generica «Valuta» vale solo
    se coincide esattamente con la cella; la denominazione si legge a parte, con
    :func:`_estrai_valuta_denominazione`. Senza righe di negoziazione resta il default EUR.
    """
    etichette = [
        "Negotiation Currency",
        "Negotiation currency",
        "Valuta di Negoziazione",
        "Valuta di negoziazione",
        "Trading Currency",
        "Settlement Currency",
        "Valuta di Liquidazione",
    ]
    val = _trova_valore(soup, etichette) or _trova_valore(soup, ["Valuta", "Currency"], esatta=True)
    if val:
        val = val.strip().upper()
        # Formato "EUR/EUR" → negoziazione/liquidazione
        if "/" in val:
            parti = [p.strip() for p in val.split("/")]
            neg = parti[0] if len(parti[0]) == 3 and parti[0].isalpha() else "EUR"
            liq = parti[1] if len(parti) > 1 and len(parti[1]) == 3 and parti[1].isalpha() else None
            return neg, liq if liq != neg else None
        if len(val) == 3 and val.isalpha():
            return val, None
    return "EUR", None


def _estrai_valuta_denominazione(soup: BeautifulSoup) -> str | None:
    """Estrae la valuta di denominazione (schede ETF/ETC), se la pagina la riporta."""
    val = _trova_valore(soup, ["Valuta di Denominazione", "Currency Denomination", "Denomination Currency"])
    if val:
        val = val.strip().upper()
        if len(val) == 3 and val.isalpha():
            return val
    return None


# ------------------------------------------------------------------
# Funzione principale
# ------------------------------------------------------------------


def ottieni_scheda(
    isin: str,
    mic: str | None = None,
    lingua: str = "en",
    sessione: Sessione | None = None,
    platform: str | None = None,
    url_diretto: str | None = None,
) -> SchedaStrumento:
    """Esegue lo scraping della pagina scheda di uno strumento.

    Args:
        isin: codice ISIN dello strumento.
        mic: codice MIC (es. ``"MOTX"``). Se ``None`` usa l'URL
            universale con redirect automatico.
        lingua: ``"en"`` (consigliata) o ``"it"``.
        sessione: sessione HTTP riutilizzabile.
        platform: piattaforma (es. ``"TLX"`` per EuroTLX). Alcuni mercati
            redirigono l'URL universale solo con mic+platform.
        url_diretto: URL canonico già risolto (es. da un motore di ricerca
            esterno, ``…/obbligazioni/eurotlx/scheda/<ISIN>-<MIC>.html``).
            Bypassa del tutto la pagina universale: utile quando la search del
            sito non indicizza (ancora) lo strumento o non abbiamo mic/platform.

    Returns:
        ``SchedaStrumento`` con tutti i dati estratti.

    Raises:
        StrumentoNonRisolto: se la pagina universale non redirige a una
            scheda di mercato (strumento inesistente, mic/platform mancanti
            o mercato non gestito).
        StrumentoNonTrovato: se la pagina non esiste.
        DatiNonDisponibili: se il prezzo non è leggibile.
    """
    isin = isin.strip().upper()
    lingua = lingua.lower()

    sessione_locale = sessione is None
    if sessione_locale:
        sessione = Sessione()

    try:
        if url_diretto:
            # URL canonico già risolto: niente pagina universale, niente redirect.
            soup, url_finale = sessione.get_html_con_url(url_diretto, params={"lang": lingua})
        else:
            # Scarica la pagina scheda (segue redirect automatico)
            parametri: dict[str, str] = {"code": isin, "lang": lingua}
            if mic:
                parametri["mic"] = mic
            if platform:
                parametri["platform"] = platform

            soup, url_finale = sessione.get_html_con_url(_URL_SCHEDA, params=parametri)

        # Nessun redirect alla pagina di mercato: lo strumento non è risolto
        # (alcuni mercati, es. EuroTLX, richiedono mic+platform espliciti).
        if "/search/scheda.html" in url_finale:
            raise StrumentoNonRisolto(
                f"La ricerca universale non ha risolto '{isin}' "
                f"(mic={mic}, platform={platform}): strumento inesistente "
                "o mercato non gestito."
            )

        # Controlla se la pagina esiste
        testo_pagina = soup.get_text(" ", strip=True)
        if any(msg in testo_pagina for msg in ("Page not found", "Pagina non trovata", "404")):
            raise StrumentoNonTrovato(f"Pagina scheda non trovata per ISIN '{isin}'")

        # Determina tipo dall'URL finale (dopo redirect)
        tipo = _determina_tipo(soup, url_finale)
        nome = _estrai_nome(soup)
        mercato = _estrai_mercato(soup, lingua, url_finale)
        valuta, valuta_liq = _estrai_valuta(soup, lingua)

        # Descrizione dal meta tag
        descrizione = None
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc and isinstance(meta_desc, Tag):
            desc_content = meta_desc.get("content", "")
            if isinstance(desc_content, str):
                descrizione = _pulisci_testo(desc_content) or None

        # Prezzo principale
        prezzo = _trova_prezzo_principale(soup, lingua)
        soup_dc: BeautifulSoup | None = None
        if prezzo is None:
            # Tentativo: provo la pagina dati-completi
            try:
                soup_dc = _scarica_dati_completi(isin, tipo, lingua, sessione, mic, url_finale=url_finale)
                prezzo = _trova_prezzo_principale(soup_dc, lingua)
                # Estrai dati aggiuntivi dalla pagina dati-completi
                soup = soup_dc
            except Exception:
                pass

        if prezzo is None:
            raise DatiNonDisponibili(f"Impossibile estrarre il prezzo dalla pagina scheda di '{isin}'")

        # Variazione %
        variazione_str = _trova_valore(
            soup,
            [
                "Var %",
                "Var%",
                "Change %",
                "Variazione %",
                "Var. %",
                "Perf.",
            ],
        )
        variazione = _parsa_percentuale(variazione_str, lingua) if variazione_str else None

        # Campi comuni: range giornaliero e annuale
        apertura = _parsa_numero(_trova_valore(soup, ["Opening", "Apertura"]) or "", lingua)
        minimo_giorno = _parsa_numero(_trova_valore(soup, ["Day Low", "Minimo Giorno", "Min Oggi"]) or "", lingua)
        massimo_giorno = _parsa_numero(_trova_valore(soup, ["Day High", "Massimo Giorno", "Max Oggi"]) or "", lingua)

        # Year Low/High — il formato può essere "8.808 - 26/02/19"
        min_anno_raw = _trova_valore(soup, ["Year Low", "Minimo Anno", "Min Anno"])
        max_anno_raw = _trova_valore(soup, ["Year High", "Massimo Anno", "Max Anno"])
        minimo_anno = _parsa_numero(
            min_anno_raw.split("-")[0].strip() if min_anno_raw and "-" in min_anno_raw else (min_anno_raw or ""), lingua
        )
        massimo_anno = _parsa_numero(
            max_anno_raw.split("-")[0].strip() if max_anno_raw and "-" in max_anno_raw else (max_anno_raw or ""), lingua
        )

        # Costruisci il risultato base
        scheda = SchedaStrumento(
            isin=isin,
            nome=nome,
            prezzo=prezzo,
            variazione_percentuale=variazione,
            valuta=valuta,
            tipo=tipo,
            mercato=mercato,
            descrizione=descrizione,
            url_pagina=url_finale or None,
            valuta_liquidazione=valuta_liq,
            valuta_denominazione=_estrai_valuta_denominazione(soup),
            apertura=apertura,
            minimo_giorno=minimo_giorno,
            massimo_giorno=massimo_giorno,
            minimo_anno=minimo_anno,
            massimo_anno=massimo_anno,
        )

        # Campi specifici per obbligazioni
        if tipo == "obbligazione":
            _arricchisci_obbligazione(scheda, soup, lingua)
            # Alcuni mercati (es. EuroTLX) non mostrano emittente/scadenza nella
            # pagina scheda: integra da dati-completi riempiendo solo i campi mancanti.
            if scheda.emittente is None or scheda.scadenza is None:
                if soup_dc is None:
                    try:
                        soup_dc = _scarica_dati_completi(isin, tipo, lingua, sessione, mic, url_finale=url_finale)
                    except Exception:
                        soup_dc = None
                if soup_dc is not None:
                    _integra_obbligazione_da_dati_completi(scheda, soup_dc, lingua)
            _correggi_secolo_scadenza(scheda)

        # Campi specifici per azioni
        if tipo == "azione":
            _arricchisci_azione(scheda, soup, lingua)

        return scheda

    finally:
        if sessione_locale:
            sessione.chiudi()


def _correggi_secolo_scadenza(scheda: SchedaStrumento) -> None:
    """Fix the century of a bond expiry date written with a 2-digit year.

    The scheda writes the expiry as ``20/09/17`` (it) or ``17/09/20`` (en), and
    ``%y`` maps 00-68 to 20xx and 69-99 to 19xx. So the Austria 2117 bond
    (AT0000A1XML2) came out as 2017-09-20 and the BTP 2072 (IT0005441883) as
    1972-03-01.

    A bond trades only before it matures, so its expiry cannot come before the
    reference price date (always written with 4 digits) or the first day of
    trading. While the expiry is earlier than the later of the two, add 100 years.
    The check applies to any expiry: a 4-digit one is never earlier than those
    dates. Without either date the expiry is left as it is (no guess based on
    today's date, which could push an already expired bond into the next century).
    """
    if scheda.scadenza is None:
        return
    riferimenti = [d for d in (scheda.data_prezzo_riferimento, scheda.data_primo_giorno) if d is not None]
    if not riferimenti:
        return
    limite = max(riferimenti)
    scadenza = scheda.scadenza
    for _ in range(2):  # 19xx -> 20xx -> 21xx at most
        if scadenza >= limite:
            break
        try:
            scadenza = scadenza.replace(year=scadenza.year + 100)
        except ValueError:  # 29 February of a year whose +100 is not a leap year
            scadenza = scadenza.replace(year=scadenza.year + 100, day=28)
    scheda.scadenza = scadenza


def _scarica_dati_completi(
    isin: str,
    tipo: str,
    lingua: str,
    sessione: Sessione,
    mic: str | None = None,
    url_finale: str | None = None,
) -> BeautifulSoup:
    """Scarica la pagina dati-completi per uno strumento.

    Il path di mercato è derivato dall'URL finale della scheda (dopo redirect):
    ``…/<market-path>/scheda/<ISIN>-<MIC>.html`` → ``…/<market-path>/dati-completi.html``.
    Copre ogni mercato (MOT/BTP, EuroTLX, ExtraMOT, GEM, …) senza mappe hardcoded;
    se l'URL finale non è riconoscibile si ripiega sui path storici azioni/MOT.
    """
    url = _url_dati_completi(url_finale, tipo)

    parametri: dict[str, str] = {"isin": isin, "lang": lingua}
    if mic:
        parametri["mic"] = mic

    return sessione.get_html(url, params=parametri)


def _url_dati_completi(url_finale: str | None, tipo: str) -> str:
    """Deriva l'URL dati-completi dall'URL finale della scheda, con fallback storico."""
    if url_finale and "/scheda/" in url_finale:
        base = url_finale.split("/scheda/")[0]
        return f"{base}/dati-completi.html"
    return _URL_DATI_COMPLETI_BOND if tipo == "obbligazione" else _URL_DATI_COMPLETI_AZIONE


def _integra_obbligazione_da_dati_completi(
    scheda: SchedaStrumento,
    soup_dc: BeautifulSoup,
    lingua: str,
) -> None:
    """Riempie i campi obbligazionari mancanti dalla pagina dati-completi.

    Rilancia l'arricchimento sulla pagina dati-completi e poi ripristina i valori
    già presenti (la scheda vince; dati-completi colma solo i vuoti).
    """
    campi = (
        "rendimento_lordo",
        "rendimento_netto",
        "rateo_lordo",
        "rateo_netto",
        "duration_modificata",
        "cedola_annua",
        "cedola_periodale",
        "scadenza",
        "emittente",
        "tipo_bond",
        "lotto_minimo",
        "descrizione_payout",
        "frequenza_cedola",
        "convenzione_giorni",
        "struttura_bond",
        "outstanding",
        "tipologia",
        "prezzo_riferimento",
        "data_prezzo_riferimento",
        "data_primo_giorno",
    )
    backup = {c: getattr(scheda, c, None) for c in campi}
    _arricchisci_obbligazione(scheda, soup_dc, lingua)
    for campo, valore in backup.items():
        if valore is not None:
            setattr(scheda, campo, valore)


def _arricchisci_obbligazione(
    scheda: SchedaStrumento,
    soup: BeautifulSoup,
    lingua: str,
) -> None:
    """Popola i campi specifici per obbligazioni."""
    # Rendimento lordo
    val = _trova_valore(
        soup,
        [
            "Gross Yield",
            "Rendimento Lordo",
            "YTM Gross",
            "Gross Yield to Maturity",
            "Gross yield to maturity",
            "Rendimento effettivo a scadenza lordo",
        ],
    )
    scheda.rendimento_lordo = _parsa_percentuale(val, lingua) if val else None

    # Rendimento netto
    val = _trova_valore(
        soup,
        [
            "Net Yield",
            "Rendimento Netto",
            "YTM Net",
            "Net Yield to Maturity",
            "Net yield to maturity",
            "Rendimento effettivo a scadenza netto",
        ],
    )
    scheda.rendimento_netto = _parsa_percentuale(val, lingua) if val else None

    # Rateo lordo
    val = _trova_valore(
        soup,
        [
            "Gross Accrued Interest",
            "Rateo Lordo",
            "Accrued Interest Gross",
            "Gross accrued interest",
        ],
    )
    scheda.rateo_lordo = _parsa_numero(val, lingua) if val else None

    # Rateo netto
    val = _trova_valore(
        soup,
        [
            "Net Accrued Interest",
            "Rateo Netto",
            "Accrued Interest Net",
            "Net accrued interest",
        ],
    )
    scheda.rateo_netto = _parsa_numero(val, lingua) if val else None

    # Duration modificata
    val = _trova_valore(
        soup,
        [
            "Modified Duration",
            "Duration Modificata",
            "Mod. Duration",
        ],
    )
    scheda.duration_modificata = _parsa_numero(val, lingua) if val else None

    # Cedola annua
    val = _trova_valore(
        soup,
        [
            "Annual Coupon Rate",
            "Cedola Annua",
            "Annual Coupon",
            "Tasso Cedola Annuale",
            "Tasso Cedola su base Annua",
        ],
    )
    scheda.cedola_annua = _parsa_percentuale(val, lingua) if val else None

    # Cedola periodale
    val = _trova_valore(
        soup,
        [
            "Periodic Coupon Rate",
            "Cedola Periodale",
            "Periodic Coupon",
            "Tasso Cedola Periodale",
        ],
    )
    scheda.cedola_periodale = _parsa_percentuale(val, lingua) if val else None

    # Scadenza. Exact match first: as substrings, "Scadenza" and "Maturity" also
    # match the yield rows ("Rendimento effettivo a scadenza lordo",
    # "Gross yield to maturity"), which come earlier in the scheda page.
    etichette_scadenza = [
        "Maturity Date",
        "Scadenza",
        "Maturity",
        "Data Scadenza",
        "Expiry Date",
        "Data Scadenza",
    ]
    val = _trova_valore(soup, etichette_scadenza, esatta=True) or _trova_valore(soup, etichette_scadenza)
    scheda.scadenza = _parsa_data_scheda(val, lingua) if val else None

    # Emittente
    val = _trova_valore(
        soup,
        [
            "Issuer",
            "Emittente",
            "Issuer Name",
        ],
    )
    scheda.emittente = val

    # Tipo bond (coupon type)
    val = _trova_valore(
        soup,
        [
            "Coupon Type",
            "Tipo Cedola",
            "Bond Type",
            "Tipo Obbligazione",
        ],
    )
    scheda.tipo_bond = val

    # Lotto minimo
    val = _trova_valore(
        soup,
        [
            "Lot Size",
            "Minimum Lot",
            "Lotto Minimo",
            "Min. Lot",
            "Min Lot",
        ],
    )
    if val:
        numero = _parsa_numero(val, lingua)
        scheda.lotto_minimo = int(numero) if numero else None

    # Descrizione payout
    val = _trova_valore(
        soup,
        [
            "Payout Description",
            "Descrizione Payout",
            "Coupon Description",
        ],
    )
    scheda.descrizione_payout = val

    # --- Nuovi campi ---

    # Frequenza cedola
    val = _trova_valore(
        soup,
        [
            "Coupon Frequency",
            "Frequenza Cedola",
            "Frequenza Cedole",
            "Periodicità cedola",
        ],
    )
    scheda.frequenza_cedola = val

    # Convenzione giorni
    val = _trova_valore(
        soup,
        [
            "Day Count Convention",
            "Convenzione Giorni",
            "Day Count",
            "Base di Calcolo",
        ],
    )
    scheda.convenzione_giorni = val

    # Struttura bond
    val = _trova_valore(
        soup,
        [
            "Bond Structure",
            "Struttura Obbligazione",
            "Struttura Bond",
        ],
    )
    scheda.struttura_bond = val

    # Outstanding (ammontare in circolazione)
    val = _trova_valore(
        soup,
        [
            "Outstanding",
            "Ammontare in Circolazione",
            "Circolante",
            "Ammontare Emesso",
        ],
    )
    scheda.outstanding = _parsa_numero(val, lingua) if val else None

    # Tipologia (Italian Government Bonds, Corporate, etc.)
    val = _trova_valore(
        soup,
        [
            "Tipology",
            "Tipologia",
        ],
    )
    scheda.tipologia = val

    # Prezzo di riferimento
    val = _trova_valore(
        soup,
        [
            "Reference price",
            "Prezzo di Riferimento",
            "Reference Price",
        ],
    )
    scheda.prezzo_riferimento = _parsa_numero(val, lingua) if val else None

    # Data prezzo di riferimento
    val = _trova_valore(
        soup,
        [
            "Reference price date",
            "Data Prezzo di Riferimento",
            "Data di riferimento",
            "Reference Price Date",
        ],
    )
    scheda.data_prezzo_riferimento = _parsa_data_scheda(val, lingua) if val else None

    # Data primo giorno di negoziazione
    val = _trova_valore(
        soup,
        [
            "First Day of Trading",
            "Primo Giorno di Negoziazione",
            "Prima Data di Negoziazione",
            "Data Inizio Negoziazione",
        ],
    )
    scheda.data_primo_giorno = _parsa_data_scheda(val, lingua) if val else None


def _arricchisci_azione(
    scheda: SchedaStrumento,
    soup: BeautifulSoup,
    lingua: str,
) -> None:
    """Popola i campi specifici per azioni."""
    # Settore
    val = _trova_valore(
        soup,
        [
            "Super Sector",
            "Settore",
            "Sector",
            "Industry Sector",
        ],
    )
    scheda.settore = val

    # Capitalizzazione
    val = _trova_valore(
        soup,
        [
            "Market Cap",
            "Capitalizzazione",
            "Market Capitalization",
            "Cap. di Mercato",
        ],
    )
    scheda.capitalizzazione = _parsa_numero(val, lingua) if val else None

    # Ticker
    val = _trova_valore(
        soup,
        [
            "Alphanumeric Code",
            "Codice Alfanumerico",
            "Ticker",
            "Symbol",
            "Alpha Code",
        ],
    )
    scheda.ticker = val

    # Performance 1 mese
    val = _trova_valore(
        soup,
        [
            "1 Month Performance",
            "Perf. 1 month",
            "Perf. 1 mese",
            "Performance 1 mese",
            "Performance 1M",
            "Perf 1M",
            "1 Month",
        ],
    )
    scheda.performance_1m = _parsa_percentuale(val, lingua) if val else None

    # Performance 6 mesi
    val = _trova_valore(
        soup,
        [
            "6 Months Performance",
            "Perf. 6 months",
            "Perf. 6 mesi",
            "Performance 6 mesi",
            "Performance 6M",
            "Perf 6M",
            "6 Months",
        ],
    )
    scheda.performance_6m = _parsa_percentuale(val, lingua) if val else None

    # Performance 1 anno
    val = _trova_valore(
        soup,
        [
            "1 Year Performance",
            "Perf. 1 year",
            "Perf. 1 anno",
            "Performance 1 anno",
            "Performance 1Y",
            "Perf 1Y",
            "1 Year",
        ],
    )
    scheda.performance_1y = _parsa_percentuale(val, lingua) if val else None

    # Indici di appartenenza
    val = _trova_valore(
        soup,
        [
            "Index",
            "Indice",
            "Indices",
            "Indici",
        ],
    )
    if val:
        scheda.indici = [s.strip() for s in val.split(",") if s.strip()]


# ------------------------------------------------------------------
# Profilo società
# ------------------------------------------------------------------


_URL_PROFILO_SOCIETA = ("https://www.borsaitaliana.it/borsa/azioni/profilo-societa-dettaglio.html")

def _trova_articolo_sezione(
    soup: BeautifulSoup,
    intestazioni: tuple[str, ...],
) -> Tag | None:
    """Individua l'articolo corrispondente a una sezione del profilo."""

    intestazioni_normalizzate = {
        _pulisci_testo(t).casefold()
        for t in intestazioni
    }

    for titolo in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
        testo = _pulisci_testo(
            titolo.get_text(" ", strip=True)
        ).casefold()

        if testo in intestazioni_normalizzate:
            articolo = titolo.find_parent("article")

            if articolo is not None:
                return articolo

    return None

def _testo_cella(cella: Tag) -> str:
    """Estrae il testo di una cella, normalizzando spazi e ritorni a capo."""
    return _pulisci_testo(cella.get_text(" ", strip=True))


def _righe_tabella(tabella: Tag) -> list[list[str]]:
    """Restituisce le righe non vuote di una tabella HTML."""
    righe: list[list[str]] = []
    for tr in tabella.find_all("tr"):
        celle = tr.find_all(["th", "td"], recursive=False)
        if not celle:
            celle = tr.find_all(["th", "td"])
        valori = [_testo_cella(c) for c in celle]
        if any(valori):
            righe.append(valori)
    return righe


def _valore_profilo(testo: str, lingua: str) -> Decimal | date | str | None:
    """Converte una cella finanziaria mantenendo testo e date non numerici."""
    testo = _pulisci_testo(testo)
    if not testo or testo in {"-", "--", "n.d.", "n/a", "n.a."}:
        return None

    # Le date della tabella sono normalmente ISO (YYYY-MM-DD).
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", testo):
            return date.fromisoformat(testo)
    except ValueError:
        pass

    numero = _parsa_numero(testo, lingua)
    if numero is not None:
        return numero
    return testo


def _estrai_descrizione_profilo(soup: BeautifulSoup) -> str | None:
    """Estrae la descrizione dal blocco COMPANY-PROFILE.

    Nel markup di Borsa Italiana la descrizione è testo diretto di uno <span>
    dentro il contenitore bianco del profilo; la fonte e la data sono invece
    in un <p> annidato nello stesso span. Quel paragrafo viene escluso.
    """
    intestazione = None
    for tag in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
        if _pulisci_testo(tag.get_text()).casefold() in {"profilo società", "profilo societa", "company profile"}:
            intestazione = tag
            break

    if intestazione is None:
        return None

    # Caso standard: <article> ... <h3>Profilo società</h3> ...
    # <div class="... h-bg--white"> ... <span>descrizione <p>Fonte...</p>
    articolo = intestazione.find_parent("article")
    ambito = articolo if articolo is not None else intestazione.parent
    if ambito is None:
        return None

    contenitore = ambito.find(
        lambda tag: isinstance(tag, Tag)
        and tag.name == "div"
        and "h-bg--white" in (tag.get("class") or [])
    )
    if contenitore is None:
        contenitore = ambito

    span = contenitore.find("span", class_=lambda classi: classi and "line-height-md" in classi)
    if span is not None:
        # Non includere il <p> annidato: contiene Fonte e Ultimo aggiornamento.
        frammenti = [
            str(nodo).strip()
            for nodo in span.find_all(string=True)
            if str(nodo).strip() and nodo.find_parent("p") is None
        ]
        descrizione = _pulisci_testo(" ".join(frammenti))
        if descrizione:
            return descrizione

    # Fallback per eventuali varianti del markup: cerca il primo testo utile
    # dopo l'intestazione, fermandosi prima del blocco dei dirigenti.
    parti: list[str] = []
    for elemento in intestazione.find_all_next(["span", "p", "table", "h1", "h2", "h3", "h4", "h5", "h6"]):
        if elemento.name in {"table", "h1", "h2", "h3", "h4", "h5", "h6"}:
            break
        if elemento.name == "span" and elemento.find_parent("table") is None:
            testo = _pulisci_testo(" ".join(
                str(n).strip() for n in elemento.find_all(string=True)
                if str(n).strip() and n.find_parent("p") is None
            ))
            if testo:
                parti.append(testo)
                break
    return " ".join(parti) or None



def _estrai_metadati_fonte(
    contenitore: Tag,
) -> tuple[str | None, date | None]:
    """Estrae fonte e data di aggiornamento del Profilo Società.

    Supporta le etichette:
    - Fonte
    - Source
    - Ultimo aggiornamento
    - Last update

    Supporta date ISO, numeriche e testuali inglesi.
    """
    testo = _pulisci_testo(
        contenitore.get_text(" ", strip=True)
    )

    fonte: str | None = None
    aggiornamento: date | None = None
    etichetta_fonte = r"(?:Fonte|Source)"
    etichetta_data = r"(?:Ultimo aggiornamento|Last update)"

    match_fonte = re.search(rf"{etichetta_fonte}\s*:?\s*(.*?)"rf"(?=\s*{etichetta_data}\s*:|$)",testo,re.IGNORECASE)

    if match_fonte:
        fonte = match_fonte.group(1).strip(" :-–,")
        fonte = fonte or None

    pattern_data = (
        r"\d{4}-\d{2}-\d{2}"
        r"|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}"
        r"|[A-Z][a-z]+\s+\d{1,2},?\s+\d{4}"
        r"|\d{1,2}\s+[A-Z][a-z]+\s+\d{4}"
    )

    match_data = re.search(rf"{etichetta_data}\s*:?\s*({pattern_data})",testo,re.IGNORECASE)

    if match_data:
        raw_data = match_data.group(1).strip()

        # Prima prova i formati già supportati dal parser principale.
        aggiornamento = _parsa_data(raw_data, "it")

        # Fallback per date testuali inglesi.
        if aggiornamento is None:
            for fmt in ("%B %d, %Y", "%B %d %Y", "%d %B %Y"):
                try:
                    aggiornamento = datetime.strptime(raw_data, fmt).date()
                    break
                except ValueError:
                    continue

    return fonte, aggiornamento



def _estrai_indirizzo_e_contatti(
    articolo_indirizzo: Tag | None,
    articolo_contatti: Tag | None,
) -> tuple[IndirizzoSocieta | None, ContattiSocieta]:

    telefono = None
    sito_web = None
    email = None

    ragione_sociale = None
    via = None
    cap = None
    comune = None
    paese = None
    
    # INDIRIZZO
    if articolo_indirizzo is not None:

        contenitore = articolo_indirizzo.find("div", class_=lambda c: c and "h-bg--white" in c)

        if contenitore is not None:

            # Ragione sociale: normalmente è nell'h3 interno.
            intestazione = contenitore.find("h3")

            if intestazione is not None:
                ragione_sociale = _pulisci_testo(
                    intestazione.get_text(" ", strip=True)
                ) or None

            # Telefono dal link tel:
            link_tel = contenitore.find(
                "a",
                href=re.compile(r"^tel:", re.I)
            )

            if link_tel is not None:
                telefono = _pulisci_testo(
                    link_tel.get_text(" ", strip=True)
                ) or str(link_tel.get("href", "")).removeprefix("tel:")

            # Sito web: primo link esterno.
            for link in contenitore.find_all("a", href=True):

                href = str(link["href"]).strip()

                if not href.lower().startswith(("http://", "https://")):
                    continue

                dominio = re.sub(
                    r"^https?://",
                    "",
                    href,
                    flags=re.I,
                ).split("/")[0].lower()

                if dominio not in {
                    "borsaitaliana.it",
                    "www.borsaitaliana.it",
                    "londonstockexchange.com",
                    "www.londonstockexchange.com",
                }:
                    sito_web = href
                    break

            # Estrazione delle righe dell'indirizzo.
            righe = [
                _pulisci_testo(x)
                for x in contenitore.stripped_strings
                if _pulisci_testo(x)
            ]

            # Escludiamo intestazione, ragione sociale,
            # telefono e URL.
            righe_indirizzo = []

            for riga in righe:

                if ragione_sociale and riga == ragione_sociale:
                    continue

                if re.match(
                    r"^(numero di telefono|telefono|phone|tel)\s*:",
                    riga,
                    re.I,
                ):
                    continue

                if re.match(r"^https?://", riga, re.I):
                    continue

                if riga == (link_tel.get_text(" ", strip=True) if link_tel else None):
                    continue

                righe_indirizzo.append(riga)

            # Individuazione CAP e prefisso internazionale.
            for indice, riga in enumerate(righe_indirizzo):

                match = re.search(
                    r"\b(?:[A-Z]{2}[- ]?)?(\d{5})\b",
                    riga,
                    re.I,
                )

                if match:
                    cap = match.group(1)

                    # Eventuale comune sulla stessa riga.
                    resto = (riga[:match.start()] + riga[match.end():]).strip(" ,-")
                    if resto:
                        comune = resto

                    # La riga successiva normalmente contiene
                    # il comune.
                    if comune is None and indice + 1 < len(righe_indirizzo):
                        comune = righe_indirizzo[indice + 1]

                    # La riga successiva al comune contiene
                    # normalmente il paese.
                    if (
                        comune is not None
                        and indice + 2 < len(righe_indirizzo)
                    ):
                        paese = righe_indirizzo[indice + 2]

                    break

            # La prima riga precedente al CAP è normalmente
            # la via.
            if cap is not None:
                for riga in righe_indirizzo:
                    if re.search(r"\b\d{5}\b", riga):
                        break

                    if not via:
                        via = riga

            # Fallback per indirizzi senza CAP.
            elif righe_indirizzo:
                via = righe_indirizzo[0]

                if len(righe_indirizzo) > 1:
                    comune = righe_indirizzo[1]

                if len(righe_indirizzo) > 2:
                    paese = righe_indirizzo[2]

    # CONTATTI
    if articolo_contatti is not None:

        contenitore = articolo_contatti.find("div",class_=lambda c: c and "h-bg--white" in c)
        if contenitore is not None:
            link_email = contenitore.find("a",href=re.compile(r"^mailto:", re.I))
            if link_email is not None:
                email = str(link_email.get("href", "")).removeprefix("mailto:").strip()

    indirizzo = None

    if any((ragione_sociale, via, cap, comune, paese)):
        indirizzo = IndirizzoSocieta(ragione_sociale=ragione_sociale,via=via,cap=cap,comune=comune,paese=paese)

    contatti = ContattiSocieta(telefono=telefono,email=email,sito_web=sito_web)

    return indirizzo, contatti


def _estrai_tabelle_profilo(
    soup: BeautifulSoup,
    lingua: str,
) -> tuple[list[Dirigente], list[int], list[DatoSocietario], list[Azionista]]:
    """Classifica ed estrae le tabelle del Profilo Società.

    Estrae:
    - dirigenti;
    - anni disponibili;
    - dati societari;
    - azionisti e relative percentuali.

    La classificazione considera intestazioni, contenuto e struttura HTML.
    Non elimina automaticamente la prima riga delle tabelle azionarie.
    """
    dirigenti: list[Dirigente] = []
    anni: list[int] = []
    dati: list[DatoSocietario] = []
    azionisti: list[Azionista] = []

    parole_azionariato = (
        "azionariato",
        "azionista",
        "azionisti",
        "shareholder",
        "shareholders",
        "shareholding",
        "ownership",
        "ownership structure",
        "major shareholders",
    )

    parole_intestazione_azionisti = {
        "azionista",
        "azionisti",
        "shareholder",
        "shareholders",
        "shareholder name",
        "shareholding",
        "name",
        "nome",
        "percentage",
        "percentage held",
        "quota",
        "percentuale",
        "holding",
        "stake",
    }

    parole_intestazione_dirigenti = {
        "ruolo",
        "carica",
        "position",
        "title",
        "role",
        "nominativo",
        "nome",
        "name",
        "director",
        "directors",
    }

    parole_dirigenti = (
        "amministratore delegato",
        "chief executive",
        "chief financial",
        "chief operating",
        "chief",
        "ceo",
        "cfo",
        "coo",
        "presidente",
        "chairman",
        "chairperson",
        "director",
        "directors",
        "executive director",
        "non-executive director",
        "board of directors",
        "management",
        "dirigenti",
        "direttore",
    )

    def normalizza(testo: str) -> str:
        return _pulisci_testo(testo).casefold().strip(" :")

    def e_intestazione_azionisti(riga: list[str]) -> bool:
        valori = {normalizza(v) for v in riga if v}

        return bool(
            valori
            and any(
                valore in parole_intestazione_azionisti
                for valore in valori
            )
            and not any(
                re.search(r"\d", valore)
                for valore in valori
            )
        )

    def e_riga_percentuale(riga: list[str]) -> bool:
        if len(riga) < 2:
            return False

        ultimo = riga[-1].strip()

        # Per l'azionariato accettiamo percentuali esplicite.
        # Senza %, accettiamo solo numeri plausibili come percentuale.
        if "%" in ultimo:
            return _parsa_percentuale(ultimo, lingua) is not None

        valore = _parsa_numero(ultimo, lingua)

        return valore is not None and Decimal("0") <= valore <= Decimal("100")

    for tabella in soup.find_all("table"):
        righe = _righe_tabella(tabella)

        if len(righe) < 2:
            continue

        testo_tabella = " ".join(" ".join(riga) for riga in righe).casefold()
        intestazione = righe[0]

        # Individuazione della tabella azionariato
        contenitore_azionariato = tabella.find_parent(
            lambda tag: isinstance(tag, Tag)
            and tag.name in {"div", "section", "article"}
            and any(
                parola in _pulisci_testo(
                    tag.get_text(" ", strip=True)
                ).casefold()
                for parola in parole_azionariato
            )
        )

        azionariato_esplicito = contenitore_azionariato is not None

        contiene_parole_azionariato = any(
            parola in testo_tabella
            for parola in parole_azionariato
        )

        # Tabella dei dati societari
        colonne_anni: list[tuple[int, int]] = []

        for indice, cella in enumerate(intestazione):
            valore = cella.strip()

            if re.fullmatch(r"(?:19|20)\d{2}", valore):
                colonne_anni.append((indice, int(valore)))

        if len(colonne_anni) >= 2:
            anni_tabella = sorted(
                {anno for _, anno in colonne_anni},
                reverse=True,
            )

            anni = sorted(set(anni).union(anni_tabella),reverse=True)

            for riga in righe[1:]:
                if len(riga) < 2:
                    continue

                voce = riga[0].strip()

                if not voce:
                    continue

                valori: dict[int, Decimal | date | str | None] = {}

                for indice, anno in colonne_anni:
                    raw = riga[indice] if indice < len(riga) else ""
                    valori[anno] = _valore_profilo(raw, lingua)

                dati.append(DatoSocietario(voce=voce,valori=valori))

            continue

        # Tabella azionariato
        righe_azionisti = []

        for indice, riga in enumerate(righe):
            if len(riga) < 2:
                continue

            # Salta una riga solo se è effettivamente un'intestazione.
            if e_intestazione_azionisti(riga):
                continue

            if e_riga_percentuale(riga):
                righe_azionisti.append(riga)

        if (
            righe_azionisti
            and (
                azionariato_esplicito
                or contiene_parole_azionariato
            )
        ):
            for riga in righe_azionisti:
                nome = riga[0].strip()
                raw_percentuale = riga[-1].strip()

                percentuale = _parsa_percentuale(
                    raw_percentuale,
                    lingua,
                )

                if percentuale is None:
                    percentuale = _parsa_numero(
                        raw_percentuale,
                        lingua,
                    )

                if not nome or percentuale is None:
                    continue

                if not Decimal("0") <= percentuale <= Decimal("100"):
                    continue

                azionisti.append(Azionista(nome,percentuale))

            continue

        # Tabella dirigenti
        contiene_parole_dirigenti = any(
            parola in testo_tabella
            for parola in parole_dirigenti
        )

        if contiene_parole_dirigenti:
            for riga in righe:
                if len(riga) < 2:
                    continue

                ruolo = riga[0].strip()
                nominativo = riga[-1].strip()

                ruolo_norm = normalizza(ruolo)
                nominativo_norm = normalizza(nominativo)

                if (
                    ruolo_norm in parole_intestazione_dirigenti
                    or nominativo_norm in parole_intestazione_dirigenti
                ):
                    continue

                if not ruolo or not nominativo:
                    continue

                # Evita righe che sono chiaramente percentuali.
                if re.search(r"\d+\s*%", nominativo):
                    continue

                dirigenti.append(Dirigente(ruolo,nominativo))

    return dirigenti, anni, dati, azionisti



def ottieni_profilo_societa(
    isin: str,
    mic: str | None = None,
    lingua: str = "en",
    sessione: Sessione | None = None,
) -> ProfiloSocieta:
    """
    Scarica ed estrae il profilo societario da Borsa Italiana.

    Recupera descrizione, dirigenti, dati principali, azionariato,
    indirizzo, contatti e metadati della fonte.

    Args:
        isin: Codice ISIN dello strumento.
        mic: Codice MIC del mercato; se omesso viene ricavato dall'URL canonico.
        lingua: Lingua della pagina (it o en).
        sessione: Sessione HTTP riutilizzabile; se omessa viene creata
            e chiusa automaticamente.

    Returns:
        ProfiloSocieta con le informazioni disponibili.

    Raises:
        ValueError: Se il codice ISIN è vuoto.
        StrumentoNonRisolto: Se non è possibile ricavare il MIC.
        StrumentoNonTrovato: Se il profilo non esiste o non contiene dati.
    """
    isin = isin.strip().upper()
    mic = mic.strip().upper() if mic else None
    lingua = lingua.lower()

    if not isin:
        raise ValueError("Il codice ISIN è obbligatorio")

    sessione_locale = sessione is None
    if sessione_locale:
        sessione = Sessione()

    try:
        if mic is None:
            _, url_finale = sessione.get_html_con_url(_URL_SCHEDA,params={"code": isin, "lang": lingua})

            match_mic = re.search(
                rf"/{re.escape(isin)}-([A-Z0-9]{{4}})\.html(?:$|[?#])",
                url_finale,
                flags=re.IGNORECASE,
            )

            if match_mic is None:
                raise StrumentoNonRisolto(
                    f"Impossibile ricavare il MIC per '{isin}' "
                    f"dalla pagina universale (URL finale: {url_finale!r}). "
                    "Fornire il MIC esplicitamente."
                )

            mic = match_mic.group(1).upper()

        parametri = {"isin": isin, "mic": mic, "lang": lingua}
        soup = sessione.get_html(_URL_PROFILO_SOCIETA, params=parametri)

        testo_pagina = soup.get_text(" ", strip=True).casefold()
        if any(
            messaggio in testo_pagina
            for messaggio in (
                "page not found",
                "pagina non trovata",
                "pagina richiesta non esiste",
            )
        ):
            raise StrumentoNonTrovato(f"Profilo società non trovato per ISIN '{isin}' e MIC '{mic}'")

        articolo_profilo = _trova_articolo_sezione(soup,("Profilo società", "Profilo societa", "Company profile"))
        articolo_indirizzo = _trova_articolo_sezione(soup, ("Indirizzo", "Address"))
        articolo_contatti = _trova_articolo_sezione(soup,("Contatti", "Contacts", "Contact"))

        if articolo_profilo is None:
            raise StrumentoNonTrovato(f"Sezione Profilo Società non trovata per ISIN '{isin}' e MIC '{mic}'")

        descrizione = _estrai_descrizione_profilo(soup)
        dirigenti, anni, dati, azionisti = _estrai_tabelle_profilo(soup, lingua)
        indirizzo, contatti = _estrai_indirizzo_e_contatti(articolo_indirizzo, articolo_contatti)
        fonte, aggiornamento = _estrai_metadati_fonte(articolo_profilo)

        if not any((
            descrizione,
            dirigenti,
            anni,
            dati,
            azionisti,
            indirizzo,
            contatti.telefono,
            contatti.email,
            contatti.sito_web,
        )):
            raise StrumentoNonTrovato(f"Nessun dato del Profilo Società disponibile per ISIN '{isin}' e MIC '{mic}'")

        return ProfiloSocieta(
            isin=isin,
            mic=mic,
            descrizione=descrizione,
            dirigenti=dirigenti,
            anni_disponibili=anni,
            dati_principali=dati,
            azionisti=azionisti,
            indirizzo=indirizzo,
            contatti=contatti,
            fonte=fonte,
            ultimo_aggiornamento=aggiornamento,
            url_pagina=f"{_URL_PROFILO_SOCIETA}?isin={isin}&mic={mic}&lang={lingua}",
        )

    finally:
        if sessione_locale:
            sessione.chiudi()