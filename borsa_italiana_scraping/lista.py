"""Scraping delle liste strumenti (BTP, BOT, ecc.) da Borsa Italiana."""

from __future__ import annotations

import re
import time
from datetime import date
from decimal import Decimal, InvalidOperation

from bs4 import BeautifulSoup

from .eccezioni import DatiNonDisponibili
from .scheda import _parsa_data
from .sessione import Sessione
from .tipi import StrumentoLista

# URL lista BTP
_URL_LISTA_BTP = (
    "https://www.borsaitaliana.it/borsa/obbligazioni/mot/btp/lista.html"
)

# The list is split into pages of 20 rows (?page=N): 12 pages in November 2026.
_MAX_PAGINE_LISTA = 50
_PAUSA_TRA_PAGINE = 1.0


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


def _parsa_data_lista(testo: str, lingua: str) -> date | None:
    """Parsa una data dalla tabella lista.

    Oggi la lista usa l'anno a 4 cifre in entrambe le lingue (``01/11/2027`` /
    ``2027/11/01``); la lingua serve per le date a 2 cifre, come nella scheda.
    """
    return _parsa_data(testo, lingua)


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


def _estrai_strumenti(tabella: BeautifulSoup, lingua: str) -> list[StrumentoLista]:
    """Extract the instruments from one list table (one page of results)."""
    righe = tabella.find_all("tr")
    risultati: list[StrumentoLista] = []

    # Identifica la riga header (la prima con <th>)
    header = None
    header_idx = 0
    for i, riga in enumerate(righe):
        if riga.find("th"):
            header = riga
            header_idx = i
            break

    intestazioni: list[str] = []
    if header:
        intestazioni = [_pulisci(th.get_text()).lower() for th in header.find_all("th")]

    # Mappa colonne (flessibile per EN e IT)
    idx_nome: int | None = None
    idx_isin: int | None = None
    idx_prezzo: int | None = None
    idx_cedola: int | None = None
    idx_scadenza: int | None = None

    for i, h in enumerate(intestazioni):
        if any(k in h for k in ("name", "nome", "title", "titolo", "description", "descrizione")):
            idx_nome = i
        elif "isin" in h or "code" in h or "codice" in h:
            idx_isin = i
        elif "last" in h or "ultimo" in h or "price" in h or "prezzo" in h:
            idx_prezzo = i
        elif "coupon" in h or "cedola" in h:
            idx_cedola = i
        elif "expiry" in h or "scadenza" in h or "maturity" in h:
            idx_scadenza = i

    for riga in righe[header_idx + 1:]:
        celle = riga.find_all("td")
        if not celle:
            continue

        # ISIN: prova dalla colonna dedicata, oppure dal primo link
        isin: str | None = None
        if idx_isin is not None and idx_isin < len(celle):
            isin = _estrai_isin_da_link(celle[idx_isin])
        if not isin:
            # Prova dal primo link nella riga
            isin = _estrai_isin_da_link(riga)
        if not isin:
            continue

        # MIC dal link
        mic = _estrai_mic_da_link(riga)

        # Nome
        nome = ""
        if idx_nome is not None and idx_nome < len(celle):
            nome = _pulisci(celle[idx_nome].get_text())
        if not nome:
            # Prova il testo del primo link
            link = riga.find("a")
            if link:
                nome = _pulisci(link.get_text())
            if not nome:
                nome = isin

        # Prezzo
        prezzo: Decimal | None = None
        if idx_prezzo is not None and idx_prezzo < len(celle):
            prezzo = _parsa_numero_lista(celle[idx_prezzo].get_text(), lingua)

        # Cedola
        cedola: Decimal | None = None
        if idx_cedola is not None and idx_cedola < len(celle):
            cedola = _parsa_numero_lista(celle[idx_cedola].get_text(), lingua)

        # Scadenza
        scadenza: date | None = None
        if idx_scadenza is not None and idx_scadenza < len(celle):
            scadenza = _parsa_data_lista(celle[idx_scadenza].get_text(), lingua)

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

    return risultati


def _ha_pagina_successiva(soup: BeautifulSoup, pagina: int) -> bool | None:
    """Tell whether the page's paginator links to page ``pagina + 1``.

    Returns:
        ``True``/``False`` when the page has the paginator block
        (``div.m-pagination``), ``None`` when it has none: the caller cannot
        rely on it then, and keeps reading until a page is empty or repeated.
        The "last page" icon is not used: it may point before the real last page.
    """
    paginatore = soup.find("div", class_="m-pagination")
    if paginatore is None:
        return None
    successiva = re.compile(rf"[?&]page={pagina + 1}(?:&|$)")
    return any(successiva.search(str(a.get("href", ""))) for a in paginatore.find_all("a"))


def lista_btp(
    lingua: str = "en",
    sessione: Sessione | None = None,
    *,
    max_pagine: int = _MAX_PAGINE_LISTA,
    pausa_tra_pagine: float = _PAUSA_TRA_PAGINE,
) -> list[StrumentoLista]:
    """Ottiene la lista completa dei BTP quotati sul MOT.

    Esegue lo scraping della tabella HTML dei BTP. Il sito la divide in pagine
    da 20 righe (``?page=N``): le legge tutte, una dopo l'altra, e si ferma
    quando il paginatore non ha una pagina successiva, quando una pagina è vuota
    o ripete ISIN già letti, oppure dopo ``max_pagine`` pagine.

    Args:
        lingua: ``"en"`` o ``"it"``.
        sessione: sessione HTTP riutilizzabile.
        max_pagine: numero massimo di pagine da leggere (limite di sicurezza).
        pausa_tra_pagine: secondi di attesa fra una pagina e la successiva,
            oltre alla pausa minima della ``Sessione``.

    Returns:
        Lista di ``StrumentoLista``, uno per ogni BTP (senza duplicati).

    Raises:
        DatiNonDisponibili: se la prima pagina non contiene la tabella o la
            tabella è vuota, oppure se una pagina successiva non contiene la
            tabella (probabile blocco del WAF: la lista sarebbe incompleta).
    """
    lingua = lingua.lower()
    sessione_locale = sessione is None
    if sessione_locale:
        sessione = Sessione()

    try:
        risultati: list[StrumentoLista] = []
        isin_visti: set[str] = set()

        for pagina in range(1, max_pagine + 1):
            parametri = {"lang": lingua}
            if pagina > 1:
                parametri["page"] = str(pagina)
                if pausa_tra_pagine > 0:
                    time.sleep(pausa_tra_pagine)

            soup = sessione.get_html(_URL_LISTA_BTP, params=parametri)

            tabella = soup.find("table")
            if not tabella:
                if pagina == 1:
                    raise DatiNonDisponibili("Tabella BTP non trovata nella pagina")
                # Past the last page the site still returns the (empty) table:
                # a page without any table is a WAF/challenge page.
                raise DatiNonDisponibili(
                    f"Tabella BTP non trovata a pagina {pagina}: probabile blocco del WAF, "
                    "la lista sarebbe incompleta"
                )
            if pagina == 1 and len(tabella.find_all("tr")) < 2:
                raise DatiNonDisponibili("La tabella BTP è vuota")

            strumenti = _estrai_strumenti(tabella, lingua)
            nuovi = [s for s in strumenti if s.isin not in isin_visti]
            if not nuovi:
                # Empty page (past the end) or a page repeating the previous one.
                break
            risultati.extend(nuovi)
            isin_visti.update(s.isin for s in nuovi)

            if _ha_pagina_successiva(soup, pagina) is False:
                break

        return risultati

    finally:
        if sessione_locale:
            sessione.chiudi()
