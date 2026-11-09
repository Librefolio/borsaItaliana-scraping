"""Scraping delle liste strumenti (BTP, BOT, ecc.) da Borsa Italiana."""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from bs4 import BeautifulSoup

from .eccezioni import DatiNonDisponibili
from .sessione import Sessione
from .tipi import StrumentoLista

# URL lista BTP
_URL_LISTA_BTP = (
    "https://www.borsaitaliana.it/borsa/obbligazioni/mot/btp/lista.html"
)


def _pulisci(testo: str) -> str:
    """Rimuove spazi extra e newline."""
    return " ".join(testo.split()).strip()


def _parsa_numero_lista(testo: str, lingua: str = "en") -> Decimal | None:
    """Converte una stringa numerica nella lista in Decimal."""
    testo = _pulisci(testo)
    if not testo or testo in ("-", "--", "n.a.", "N/A"):
        return None
    try:
        if lingua == "it":
            testo = testo.replace(".", "").replace(",", ".")
        else:
            testo = testo.replace(",", "")
        return Decimal(testo)
    except (InvalidOperation, ValueError):
        return None


def _parsa_data_lista(testo: str) -> date | None:
    """Parsa una data dalla tabella lista."""
    testo = _pulisci(testo)
    if not testo or testo == "-":
        return None
    for fmt in ("%d/%m/%Y", "%m/%d/%Y", "%Y-%m-%d", "%d/%m/%y", "%Y/%m/%d"):
        try:
            return datetime.strptime(testo, fmt).date()
        except ValueError:
            continue
    return None


def _estrai_isin_da_link(cella: BeautifulSoup) -> str | None:
    """Estrae l'ISIN da un link nella cella della tabella.

    L'ISIN ha formato: 2 lettere paese + 9 alfanumerici + 1 check digit.
    Usiamo un pattern più restrittivo per evitare falsi positivi
    (es. "OBBLIGAZIONI" che ha 12 lettere maiuscole).
    """
    # Pattern ISIN: esattamente 2 lettere + 10 tra cui almeno 1 cifra, con word boundary
    isin_re = re.compile(r'\b([A-Z]{2}[A-Z0-9]{9}[0-9])\b')

    link = cella.find("a")
    if link:
        href = str(link.get("href", "")).upper()
        match = isin_re.search(href)
        if match:
            return match.group(1)
    # Fallback: tutti i link nella cella
    for link in cella.find_all("a"):
        href = str(link.get("href", "")).upper()
        match = isin_re.search(href)
        if match:
            return match.group(1)
    # Fallback: testo della cella
    testo = _pulisci(cella.get_text()).upper()
    match = isin_re.search(testo)
    if match:
        return match.group(1)
    return None


def _estrai_mic_da_link(cella: BeautifulSoup) -> str:
    """Estrae il MIC dal link nella cella (es. IT0005634800-MOTX.html)."""
    for link in cella.find_all("a"):
        href = str(link.get("href", ""))
        match = re.search(r"-([A-Z]{4})\.html", href.upper())
        if match:
            return match.group(1)
    return "MOTX"


def lista_btp(
    lingua: str = "en",
    sessione: Sessione | None = None,
    max_pages: int = 50,
) -> list[StrumentoLista]:
    """Ottiene i BTP quotati sul MOT, scorrendo le pagine disponibili."""

    lingua = lingua.lower()
    sessione_locale = sessione is None

    if sessione_locale:
        sessione = Sessione()

    try:
        risultati: list[StrumentoLista] = []
        isins_trovati: set[str] = set()

        for pagina in range(1, max_pages + 1):

            soup = sessione.get_html(
                _URL_LISTA_BTP,
                params={
                    "lang": lingua,
                    "page": pagina,
                },
            )

            tabella = soup.find("table")

            if not tabella:
                if pagina == 1:
                    raise DatiNonDisponibili(
                        "Tabella BTP non trovata nella pagina"
                    )
                break

            righe = tabella.find_all("tr")

            if len(righe) < 2:
                break

            # Individua l'header
            header = None
            header_idx = 0

            for i, riga in enumerate(righe):
                if riga.find("th"):
                    header = riga
                    header_idx = i
                    break

            intestazioni = []

            if header:
                intestazioni = [
                    _pulisci(th.get_text()).lower()
                    for th in header.find_all("th")
                ]

            # Mappa delle colonne
            idx_nome = None
            idx_isin = None
            idx_prezzo = None
            idx_cedola = None
            idx_scadenza = None

            for i, h in enumerate(intestazioni):
                if any(k in h for k in (
                    "name", "nome", "title", "titolo",
                    "description", "descrizione"
                )):
                    idx_nome = i

                elif "isin" in h or "code" in h or "codice" in h:
                    idx_isin = i

                elif any(k in h for k in (
                    "last", "ultimo", "price", "prezzo"
                )):
                    idx_prezzo = i

                elif "coupon" in h or "cedola" in h:
                    idx_cedola = i

                elif any(k in h for k in (
                    "expiry", "scadenza", "maturity"
                )):
                    idx_scadenza = i

            nuovi = 0

            for riga in righe[header_idx + 1:]:
                celle = riga.find_all("td")

                if not celle:
                    continue

                # ISIN
                isin = None

                if idx_isin is not None and idx_isin < len(celle):
                    isin = _estrai_isin_da_link(celle[idx_isin])

                if not isin:
                    isin = _estrai_isin_da_link(riga)

                if not isin:
                    continue

                # Evita duplicati tra pagine
                if isin in isins_trovati:
                    continue

                isins_trovati.add(isin)

                # MIC
                mic = _estrai_mic_da_link(riga)

                # Nome
                nome = ""

                if idx_nome is not None and idx_nome < len(celle):
                    nome = _pulisci(celle[idx_nome].get_text())

                if not nome:
                    link = riga.find("a")
                    nome = _pulisci(link.get_text()) if link else isin

                # Prezzo
                prezzo = None

                if idx_prezzo is not None and idx_prezzo < len(celle):
                    prezzo = _parsa_numero_lista(
                        celle[idx_prezzo].get_text(), lingua
                    )

                # Cedola
                cedola = None

                if idx_cedola is not None and idx_cedola < len(celle):
                    cedola = _parsa_numero_lista(
                        celle[idx_cedola].get_text(), lingua
                    )

                # Scadenza
                scadenza = None

                if idx_scadenza is not None and idx_scadenza < len(celle):
                    scadenza = _parsa_data_lista(
                        celle[idx_scadenza].get_text()
                    )

                risultati.append(
                    StrumentoLista(
                        isin=isin,
                        nome=nome,
                        ultimo_prezzo=prezzo,
                        cedola=cedola,
                        scadenza=scadenza,
                        mic=mic,
                    )
                )

                nuovi += 1

            # Nessun nuovo ISIN: probabilmente ultima pagina
            # oppure il parametro page non è supportato.
            if nuovi == 0:
                break

        return risultati

    finally:
        if sessione_locale:
            sessione.chiudi()