"""Scraping della pagina scheda di uno strumento su Borsa Italiana."""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from bs4 import BeautifulSoup, Tag

from .eccezioni import DatiNonDisponibili, StrumentoNonRisolto, StrumentoNonTrovato
from .sessione import Sessione
from .tipi import SchedaStrumento

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


def _parsa_data_scheda(testo: str) -> date | None:
    """Parsa una data dalla pagina scheda (formati vari).

    Supporta sia anni a 4 cifre (``dd/mm/YYYY``) che a 2 cifre
    (``dd/mm/YY`` → interpretato come 20YY).
    """
    testo = _pulisci_testo(testo)
    if not testo or testo == "-":
        return None
    for fmt in ("%d/%m/%Y", "%m/%d/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y", "%y/%m/%d"):
        try:
            return datetime.strptime(testo, fmt).date()
        except ValueError:
            continue
    return None


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
        minimo_giorno = _parsa_numero(_trova_valore(soup, ["Day Low", "Minimo Giorno"]) or "", lingua)
        massimo_giorno = _parsa_numero(_trova_valore(soup, ["Day High", "Massimo Giorno"]) or "", lingua)

        # Year Low/High — il formato può essere "8.808 - 26/02/19"
        min_anno_raw = _trova_valore(soup, ["Year Low", "Minimo Anno"])
        max_anno_raw = _trova_valore(soup, ["Year High", "Massimo Anno"])
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

        # Campi specifici per azioni
        if tipo == "azione":
            _arricchisci_azione(scheda, soup, lingua)

        return scheda

    finally:
        if sessione_locale:
            sessione.chiudi()


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

    # Scadenza
    val = _trova_valore(
        soup,
        [
            "Maturity Date",
            "Scadenza",
            "Maturity",
            "Data Scadenza",
            "Expiry Date",
            "Data Scadenza",
        ],
    )
    scheda.scadenza = _parsa_data_scheda(val) if val else None

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
            "Reference Price Date",
        ],
    )
    scheda.data_prezzo_riferimento = _parsa_data_scheda(val) if val else None

    # Data primo giorno di negoziazione
    val = _trova_valore(
        soup,
        [
            "First Day of Trading",
            "Primo Giorno di Negoziazione",
            "Prima Data di Negoziazione",
        ],
    )
    scheda.data_primo_giorno = _parsa_data_scheda(val) if val else None


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
