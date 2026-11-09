"""Estrazione dati NAV per i fondi comuni su Borsa Italiana.

I fondi comuni **non** sono quotati sul mercato XMIL, quindi le API
``grafici.borsaitaliana.it`` (storico/intraday) non li coprono. L'unica
pagina con il NAV è ``/borsa/fondi/dettaglio/{codice}.html`` dove ``codice``
è un identificativo interno di Borsa Italiana **diverso dall'ISIN**.

Questo modulo estrae i dati dalla pagina-fondo dato il **codice interno**
(o l'URL della pagina). La risoluzione ISIN/nome -> codice è responsabilità
del chiamante e resta fuori da questa libreria:

- per **nome**: la site-search interna (``ricerca.cerca``) restituisce già il
  codice nel campo ``symbol`` delle quote di tipo ``FUNDS``;
- per **ISIN**: non esiste una rotta interna di Borsa Italiana; va risolto a
  monte (es. un motore di ricerca esterno) fino a ottenere l'URL o il codice.

Il NAV di un fondo è pubblicato una volta al giorno con ritardo: la ``data``
estratta è la data reale del NAV, **non** ``date.today()``.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from .eccezioni import DatiNonDisponibili, StrumentoNonTrovato
from .scheda import _parsa_data_scheda, _parsa_numero, _parsa_percentuale, _pulisci_testo
from .sessione import Sessione

# Pagina di dettaglio del fondo (codice = identificativo interno BI).
_URL_FONDO_DETTAGLIO = "https://www.borsaitaliana.it/borsa/fondi/dettaglio/{codice}.html"

# Estrae il codice interno da un URL /borsa/fondi/dettaglio/{codice}.html
# oppure dai link con query-string ``?code={codice}`` (es. scheda.html?code=...).
_RE_DETTAGLIO = re.compile(r"/borsa/fondi/dettaglio/([A-Z0-9]+)\.html", re.IGNORECASE)
_RE_CODE_QS = re.compile(r"[?&]code=([A-Z0-9]+)", re.IGNORECASE)

# Pattern ISIN: 2 lettere paese + 9 alfanumerici + 1 check digit.
_RE_ISIN = re.compile(r"\b([A-Z]{2}[A-Z0-9]{9}[0-9])\b")


@dataclass
class DatiFondo:
    """Dati estratti dalla pagina di dettaglio di un fondo comune."""

    codice: str  # identificativo interno Borsa Italiana
    nome: str
    nav: Decimal
    variazione_percentuale: Decimal | None
    valuta: str
    data_nav: date
    url: str
    isin: str | None = None  # estratto dalla pagina, se presente
    # Dettagli descrittivi estratti dalle sezioni della pagina-fondo (solo voci
    # valorizzate: le voci "N.D." vengono scartate). Utili per arricchire la
    # descrizione dell'asset lato consumatore.
    caratteristiche: dict[str, str] = field(default_factory=dict)
    societa_gestione: dict[str, str] = field(default_factory=dict)
    costi: dict[str, str] = field(default_factory=dict)


def estrai_codice_da_url(url: str) -> str | None:
    """Estrae il codice interno del fondo da un URL di Borsa Italiana.

    Riconosce sia ``/borsa/fondi/dettaglio/{codice}.html`` sia i link con
    query-string ``?code={codice}`` (es. ``scheda.html?code=...``).

    Returns:
        Il codice in maiuscolo, oppure ``None`` se l'URL non è riconoscibile.
    """
    if not url:
        return None
    match = _RE_DETTAGLIO.search(url) or _RE_CODE_QS.search(url)
    return match.group(1).upper() if match else None


def _estrai_isin_pagina(soup) -> str | None:
    """Estrae il primo ISIN presente nel testo della pagina-fondo (best-effort)."""
    match = _RE_ISIN.search(soup.get_text(" ", strip=True).upper())
    return match.group(1) if match else None


def _norm_heading(testo: str) -> str:
    """Normalizza un heading per il confronto (senza accenti, minuscolo, spazi collassati)."""
    senza_accenti = unicodedata.normalize("NFKD", testo or "").encode("ascii", "ignore").decode()
    return " ".join(senza_accenti.split()).lower()


def _e_non_disponibile(valore: str) -> bool:
    """True se il valore è un placeholder "non disponibile" di Borsa Italiana."""
    v = (valore or "").strip().upper().replace(" ", "")
    return v in {"N.D.", "N.D", "ND", "-", "--", ""}


def _estrai_dettagli_sezione(soup, heading_testo: str, escludi: tuple[str, ...] = ()) -> dict[str, str]:
    """Estrae le coppie label:value dalla tabella che segue un heading di sezione.

    Le pagine-fondo di Borsa Italiana raggruppano i dettagli sotto heading
    (``<h3>``: "Caratteristiche", "Società di Gestione", "Costi", …), ciascuno
    seguito da una tabella label/valore. Restituisce solo le voci **valorizzate**
    (scarta ``N.D.``/``-``/vuoto) e con label non presente in ``escludi``.

    Il confronto sul testo dell'heading è esatto ma insensibile ad accenti,
    maiuscole e spaziatura, così da evitare falsi positivi (es. un ``<h2>`` di
    titolo pagina che elenca più sezioni).
    """
    obiettivo = _norm_heading(heading_testo)
    escludi_norm = {_norm_heading(e) for e in escludi}
    for h in soup.find_all(["h2", "h3", "h4"]):
        if _norm_heading(h.get_text()) != obiettivo:
            continue
        # La tabella della sezione è quella che segue l'heading **prima** del
        # prossimo heading: se dopo l'heading arriva subito un altro heading la
        # sezione non ha tabella propria (es. valori tutti "N.D." senza tabella).
        successivo = h.find_next(["h2", "h3", "h4", "table"])
        if successivo is None or successivo.name != "table":
            return {}
        tabella = successivo
        dettagli: dict[str, str] = {}
        for tr in tabella.find_all("tr"):
            celle = [_pulisci_testo(td.get_text()) for td in tr.find_all(["td", "th"])]
            celle = [c for c in celle if c]
            if len(celle) < 2:
                continue
            label, valore = celle[0], celle[1]
            if _e_non_disponibile(valore) or _norm_heading(label) in escludi_norm:
                continue
            dettagli[label] = valore
        return dettagli
    return {}


def _estrai_dati_pagina_fondo(
    soup,
) -> tuple[str | None, Decimal | None, Decimal | None, str, date | None]:
    """Estrae (nome, nav, variazione%, valuta, data_nav) dalla pagina fondo."""
    h1 = soup.find("h1")
    nome = _pulisci_testo(h1.get_text()) if h1 else None

    nav_el = soup.find("span", class_="-formatPrice")
    nav = _parsa_numero(nav_el.get_text(), "it") if nav_el else None

    var_el = soup.find("span", class_="-percPrice")
    variazione = _parsa_percentuale(var_el.get_text(), "it") if var_el else None

    valuta = "EUR"
    data_nav: date | None = None
    summary = soup.find("div", class_="summary-fase")
    if summary is not None:
        for span in summary.find_all("span"):
            etichetta = _pulisci_testo(span.get_text(" ")).lower()
            strong = span.find("strong")
            valore = _pulisci_testo(strong.get_text()) if strong else ""
            if etichetta.startswith("valuta") and valore:
                valuta = valore
            elif etichetta.startswith("data") and valore:
                # Fund pages are Italian only (no lang parameter): dd/mm/yy.
                data_nav = _parsa_data_scheda(valore, "it")

    return nome, nav, variazione, valuta, data_nav


def _estrai_da_url(url: str, sessione: Sessione, codice_atteso: str) -> DatiFondo:
    """Scarica la pagina-fondo indicata ed estrae i dati NAV.

    Args:
        url: URL della pagina-fondo (dettaglio o scheda).
        sessione: sessione HTTP da usare.
        codice_atteso: codice interno atteso (per i messaggi d'errore e come
            ripiego se il codice non è ricavabile dall'URL finale).

    Raises:
        StrumentoNonTrovato: se la pagina non è raggiungibile.
        DatiNonDisponibili: se la pagina non contiene NAV/data valorizzati.
    """
    try:
        soup, url_finale = sessione.get_html_con_url(url)
    except Exception as err:
        raise StrumentoNonTrovato(f"Pagina-fondo non raggiungibile per il codice '{codice_atteso}': {err}") from err

    nome, nav, variazione, valuta, data_nav = _estrai_dati_pagina_fondo(soup)
    if nav is None or data_nav is None:
        raise DatiNonDisponibili(f"NAV/data non disponibili nella pagina-fondo '{codice_atteso}'")

    # Dopo un eventuale redirect il codice può cambiare: preferisci l'URL finale.
    codice_finale = estrai_codice_da_url(url_finale) or codice_atteso

    return DatiFondo(
        codice=codice_finale,
        nome=nome or codice_finale,
        nav=nav,
        variazione_percentuale=variazione,
        valuta=valuta,
        data_nav=data_nav,
        url=url_finale,
        isin=_estrai_isin_pagina(soup),
        caratteristiche=_estrai_dettagli_sezione(soup, "Caratteristiche", escludi=("Isin", "Valuta")),
        societa_gestione=_estrai_dettagli_sezione(soup, "Società di Gestione"),
        costi=_estrai_dettagli_sezione(soup, "Costi"),
    )


def ottieni_dati_fondo(codice: str, sessione: Sessione | None = None) -> DatiFondo:
    """Ottiene i dati NAV di un fondo comune dato il **codice interno** di BI.

    Args:
        codice: identificativo interno della pagina-fondo (es. ``"2FADB602822"``).
        sessione: sessione HTTP riutilizzabile (ne viene creata una se ``None``).

    Returns:
        ``DatiFondo`` con NAV, data-NAV reale, valuta, nome, ISIN (se estraibile)
        e URL della pagina.

    Raises:
        StrumentoNonTrovato: se la pagina non esiste per il codice indicato.
        DatiNonDisponibili: se la pagina non contiene NAV/data valorizzati.
    """
    codice = codice.strip().upper()
    url = _URL_FONDO_DETTAGLIO.format(codice=codice)

    sessione_locale = sessione is None
    if sessione_locale:
        sessione = Sessione()
    try:
        return _estrai_da_url(url, sessione, codice_atteso=codice)
    finally:
        if sessione_locale:
            sessione.chiudi()


def ottieni_dati_fondo_da_url(url: str, sessione: Sessione | None = None) -> DatiFondo:
    """Come :func:`ottieni_dati_fondo` ma a partire dall'URL della pagina-fondo.

    Utile quando l'URL proviene da una fonte esterna (motore di ricerca): il
    codice interno viene estratto dall'URL stesso.

    Args:
        url: URL di una pagina-fondo di Borsa Italiana.
        sessione: sessione HTTP riutilizzabile (ne viene creata una se ``None``).

    Raises:
        StrumentoNonTrovato: se l'URL non è una pagina-fondo riconoscibile o non
            è raggiungibile.
        DatiNonDisponibili: se la pagina non contiene NAV/data valorizzati.
    """
    codice = estrai_codice_da_url(url)
    if not codice:
        raise StrumentoNonTrovato(f"URL non riconosciuto come pagina-fondo: {url}")

    sessione_locale = sessione is None
    if sessione_locale:
        sessione = Sessione()
    try:
        return _estrai_da_url(url, sessione, codice_atteso=codice)
    finally:
        if sessione_locale:
            sessione.chiudi()
