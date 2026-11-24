"""Scraping delle liste strumenti obbligazionari da Borsa Italiana."""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import TypeVar

from bs4 import BeautifulSoup

from .eccezioni import DatiNonDisponibili
from .scheda import _parsa_data
from .sessione import Sessione
from .tipi import StrumentoLista, StrumentoGreenSocial


# URL delle liste
_URL_LISTA_BTP          = ("https://www.borsaitaliana.it/borsa/obbligazioni/mot/btp/lista.html")
_URL_LISTA_DOMESTIC_MOT = ("https://www.borsaitaliana.it/borsa/obbligazioni/mot/obbligazioni-euro/lista.html")
_URL_LISTA_EURO_MOT     = ("https://www.borsaitaliana.it/borsa/obbligazioni/mot/euro-obbligazioni/lista.html")
_URL_LISTA_BOT          = ("https://www.borsaitaliana.it/borsa/obbligazioni/mot/bot/lista.html")
_URL_LISTA_CTZ          = ("https://www.borsaitaliana.it/borsa/obbligazioni/mot/ctz/lista.html")
_URL_LISTA_CCT          = ("https://www.borsaitaliana.it/borsa/obbligazioni/mot/cct/lista.html")
_URL_LISTA_GREEN_SOCIAL = ("https://www.borsaitaliana.it/borsa/obbligazioni/green-e-social-bond/lista.html")

# Limiti comuni a tutte le liste.
_PAUSA_TRA_PAGINE = 1.0

# The list is split into pages of 20 rows (?page=N): 12 pages in November 2026.
_MAX_PAGINE_LISTA = 50

T = TypeVar("T")


def _pulisci(testo: str) -> str:
    """Rimuove spazi extra e newline."""
    return " ".join(testo.split()).strip()


def _parsa_numero_lista(testo: str, lingua: str = "en") -> Decimal | None:
    """Converte una stringa numerica della lista in Decimal."""
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
    """Parsa una data dalla tabella lista."""
    return _parsa_data(testo, lingua)


def _estrai_isin_da_link(cella: BeautifulSoup) -> str | None:
    """Estrae un ISIN da href o testo della cella/riga."""
    # 2 lettere paese + 9 caratteri alfanumerici + cifra di controllo.
    isin_re = re.compile(r"\b([A-Z]{2}[A-Z0-9]{9}[0-9])\b")

    for link in cella.find_all("a"):
        href = str(link.get("href", "")).upper()
        match = isin_re.search(href)
        if match:
            return match.group(1)

    testo = _pulisci(cella.get_text()).upper()
    match = isin_re.search(testo)
    return match.group(1) if match else None


def _estrai_mic_da_link(cella: BeautifulSoup, fallback: str = "MOTX") -> str:
    """Estrae il MIC da un link, ad esempio IT...-MOTX.html.

    Il fallback MOTX mantiene il comportamento storico di lista_btp().
    Se una categoria usa un diverso mercato, il relativo link deve esporre
    il MIC oppure il fallback va specificato nella chiamata al parser.
    """
    for link in cella.find_all("a"):
        href = str(link.get("href", ""))
        match = re.search(r"-([A-Z]{4})\.html", href.upper())
        if match:
            return match.group(1)
    return fallback


def _indice_colonna(
    intestazioni: list[str],
    parole_chiave: tuple[str, ...],
) -> int | None:
    """Restituisce l'indice della prima intestazione che contiene una keyword."""
    for indice, intestazione in enumerate(intestazioni):
        if any(parola in intestazione for parola in parole_chiave):
            return indice
    return None


def _intestazioni_tabella(
    tabella: BeautifulSoup,
) -> tuple[list[BeautifulSoup], list[str], int]:
    """Restituisce righe, intestazioni normalizzate e indice della riga header."""
    righe = tabella.find_all("tr")
    for indice, riga in enumerate(righe):
        celle_header = riga.find_all("th")
        if celle_header:
            intestazioni = [_pulisci(cella.get_text()).lower() for cella in celle_header]
            return righe, intestazioni, indice
    return righe, [], -1


def _estrai_strumenti(
    tabella: BeautifulSoup,
    lingua: str,
) -> list[StrumentoLista]:
    """Estrae gli strumenti da una pagina di una lista obbligazionaria standard."""
    righe, intestazioni, header_idx = _intestazioni_tabella(tabella)
    if header_idx < 0:
        return []

    idx_nome = _indice_colonna(
        intestazioni,
        ("name", "nome", "title", "titolo", "description", "descrizione"),
    )
    idx_isin = _indice_colonna(intestazioni, ("isin", "code", "codice"))
    idx_prezzo = _indice_colonna(
        intestazioni, ("last", "ultimo", "price", "prezzo")
    )
    idx_cedola = _indice_colonna(intestazioni, ("coupon", "cedola"))
    idx_scadenza = _indice_colonna(
        intestazioni, ("expiry", "scadenza", "maturity")
    )

    risultati: list[StrumentoLista] = []

    for riga in righe[header_idx + 1:]:
        celle = riga.find_all("td")
        if not celle:
            continue

        isin = None
        if idx_isin is not None and idx_isin < len(celle):
            isin = _estrai_isin_da_link(celle[idx_isin])
        if not isin:
            isin = _estrai_isin_da_link(riga)
        if not isin:
            continue

        nome = ""
        if idx_nome is not None and idx_nome < len(celle):
            nome = _pulisci(celle[idx_nome].get_text())
        if not nome:
            primo_link = riga.find("a")
            nome = _pulisci(primo_link.get_text()) if primo_link else isin
        if not nome:
            nome = isin

        prezzo = (
            _parsa_numero_lista(celle[idx_prezzo].get_text(), lingua)
            if idx_prezzo is not None and idx_prezzo < len(celle)
            else None
        )
        cedola = (
            _parsa_numero_lista(celle[idx_cedola].get_text(), lingua)
            if idx_cedola is not None and idx_cedola < len(celle)
            else None
        )
        scadenza = (
            _parsa_data_lista(celle[idx_scadenza].get_text(), lingua)
            if idx_scadenza is not None and idx_scadenza < len(celle)
            else None
        )

        risultati.append(
            StrumentoLista(
                isin=isin,
                nome=nome,
                ultimo_prezzo=prezzo,
                cedola=cedola,
                scadenza=scadenza,
                mic=_estrai_mic_da_link(riga),
            )
        )

    return risultati


def _estrai_green_social(
    tabella: BeautifulSoup,
    lingua: str,
) -> list[StrumentoGreenSocial]:
    """Estrae gli strumenti dalla lista Green & Social Bond.

    La firma mantiene il parametro lingua, così il parser è intercambiabile
    con gli altri parser nel motore comune.
    """
    del lingua  # La tabella descrittiva non contiene campi numerici localizzati.

    righe, intestazioni, header_idx = _intestazioni_tabella(tabella)
    if header_idx < 0:
        return []

    idx_isin      = _indice_colonna(intestazioni, ("isin", "code", "codice"))
    idx_nome      = _indice_colonna(intestazioni,("name", "nome", "title", "titolo", "description", "descrizione"))
    idx_emittente = _indice_colonna(intestazioni, ("issuer", "emittente", "emitt"))
    idx_tipologia = _indice_colonna(intestazioni,("issue type", "emission type", "tipologia", "tipo emissione","transaction type"))

    risultati: list[StrumentoGreenSocial] = []

    for riga in righe[header_idx + 1:]:
        celle = riga.find_all("td")
        if not celle:
            continue

        isin = None
        if idx_isin is not None and idx_isin < len(celle):
            isin = _estrai_isin_da_link(celle[idx_isin])
        if not isin:
            isin = _estrai_isin_da_link(riga)
        if not isin:
            continue

        def valore_colonna(indice: int | None) -> str | None:
            if indice is None or indice >= len(celle):
                return None
            valore = _pulisci(celle[indice].get_text())
            return valore or None

        nome = valore_colonna(idx_nome)
        if not nome:
            primo_link = riga.find("a")
            nome = _pulisci(primo_link.get_text()) if primo_link else isin

        risultati.append(
            StrumentoGreenSocial(
                isin=isin,
                nome=nome or isin,
                mic = _estrai_mic_da_link(riga),
                emittente=valore_colonna(idx_emittente),
                tipologia_emissione=valore_colonna(idx_tipologia),
            )
        )

    return risultati


def _ha_pagina_successiva(soup: BeautifulSoup, pagina: int) -> bool | None:
    """Indica se il paginatore contiene un link alla pagina successiva.

    True/False se il blocco di paginazione è presente; None se manca e
    quindi non è possibile stabilire dal paginatore se esistano altre pagine.
    """
    paginatore = soup.find("div", class_="m-pagination")
    if paginatore is None:
        return None

    successiva = re.compile(rf"[?&]page={pagina + 1}(?:&|$)")
    return any(
        successiva.search(str(link.get("href", "")))
        for link in paginatore.find_all("a")
    )


def _scarica_lista(
    url: str,
    estrattore: Callable[[BeautifulSoup, str], list[T]],
    lingua: str = "en",
    sessione: Sessione | None = None,
    *,
    nome_lista: str,
    pausa_tra_pagine: float = _PAUSA_TRA_PAGINE,
    max_pagine: int = _MAX_PAGINE_LISTA,
) -> list[T]:
    """Motore condiviso per scaricare tutte le pagine di una lista.

    Interrompe lo scraping quando il paginatore conferma che non ci sono
    altre pagine oppure quando una pagina non contiene nuovi ISIN.
    Se viene raggiunto il limite di sicurezza senza una condizione certa
    di fine, solleva DatiNonDisponibili anziché restituire dati potenzialmente
    incompleti.
    """
    lingua = lingua.lower()
    if lingua not in ("it", "en"):
        raise ValueError("lingua deve essere 'it' oppure 'en'")
    if pausa_tra_pagine < 0:
        raise ValueError("pausa_tra_pagine non può essere negativa")
    if not isinstance(max_pagine, int):
        raise TypeError("max_pagine deve essere un intero")
    if max_pagine < 1:
        raise ValueError("max_pagine deve essere almeno 1")

    sessione_locale = sessione is None
    if sessione_locale:
        sessione = Sessione()

    try:
        risultati: list[T] = []
        isin_visti: set[str] = set()

        pagina = 1

        while True:

            # Rispetta la pausa tra le richieste.
            if pagina > 1 and pausa_tra_pagine > 0:
                time.sleep(pausa_tra_pagine)

            parametri = {"lang": lingua}

            if pagina > 1:
                parametri["page"] = str(pagina)

            soup = sessione.get_html(url, params=parametri)

            tabella = soup.find("table")

            if tabella is None:
                if pagina == 1:
                    raise DatiNonDisponibili(f"Tabella {nome_lista} non trovata nella pagina")

                raise DatiNonDisponibili(
                    f"Tabella {nome_lista} non trovata a pagina {pagina}: "
                    "probabile blocco WAF; la lista sarebbe incompleta"
                )

            if pagina == 1 and len(tabella.find_all("tr")) < 2:
                raise DatiNonDisponibili(f"La tabella {nome_lista} è vuota")

            strumenti = estrattore(tabella, lingua)

            # Mantiene soltanto gli strumenti non ancora acquisiti.
            nuovi = [
                strumento
                for strumento in strumenti
                if strumento.isin not in isin_visti
            ]

            # Nessun nuovo ISIN: fine dello scraping.
            if not nuovi:
                break

            risultati.extend(nuovi)
            isin_visti.update(strumento.isin for strumento in nuovi)

            # Verifica la presenza della pagina successiva.
            pagina_successiva = _ha_pagina_successiva(soup, pagina)

            # Il paginatore conferma che siamo all'ultima pagina.
            if pagina_successiva is False:
                break

            # Raggiunto il numero massimo di pagine richiesto.
            if pagina >= max_pagine:
                break

            pagina += 1

        return risultati

    finally:
        if sessione_locale and sessione is not None:
            sessione.chiudi()


def lista_btp(
    lingua: str = "en",
    sessione: Sessione | None = None,
    *,
    pausa_tra_pagine: float = _PAUSA_TRA_PAGINE,
    max_pagine: int = _MAX_PAGINE_LISTA
) -> list[StrumentoLista]:
    """Ottiene la lista completa dei BTP quotati sul MOT."""
    return _scarica_lista(
        _URL_LISTA_BTP,
        _estrai_strumenti,
        lingua,
        sessione,
        nome_lista="BTP",
        pausa_tra_pagine=pausa_tra_pagine,
        max_pagine=max_pagine
    )


def lista_domestic_mot(
    lingua: str = "en",
    sessione: Sessione | None = None,
    *,
    pausa_tra_pagine: float = _PAUSA_TRA_PAGINE,
    max_pagine: int = _MAX_PAGINE_LISTA
) -> list[StrumentoLista]:
    """Ottiene la lista delle obbligazioni domestiche quotate sul MOT."""
    return _scarica_lista(
        _URL_LISTA_DOMESTIC_MOT,
        _estrai_strumenti,
        lingua,
        sessione,
        nome_lista="Domestic MOT",
        pausa_tra_pagine=pausa_tra_pagine,
        max_pagine=max_pagine
    )


def lista_euro_mot(
    lingua: str = "en",
    sessione: Sessione | None = None,
    *,
    pausa_tra_pagine: float = _PAUSA_TRA_PAGINE,
    max_pagine: int = _MAX_PAGINE_LISTA
) -> list[StrumentoLista]:
    """Ottiene la lista delle obbligazioni in euro quotate sul MOT."""
    return _scarica_lista(
        _URL_LISTA_EURO_MOT,
        _estrai_strumenti,
        lingua,
        sessione,
        nome_lista="Euro MOT",
        pausa_tra_pagine=pausa_tra_pagine,
        max_pagine=max_pagine
    )


def lista_bot(
    lingua: str = "en",
    sessione: Sessione | None = None,
    *,
    pausa_tra_pagine: float = _PAUSA_TRA_PAGINE,
    max_pagine: int = _MAX_PAGINE_LISTA
) -> list[StrumentoLista]:
    """Ottiene la lista dei BOT quotati sul MOT."""
    return _scarica_lista(
        _URL_LISTA_BOT,
        _estrai_strumenti,
        lingua,
        sessione,
        nome_lista="BOT",
        pausa_tra_pagine=pausa_tra_pagine,
        max_pagine=max_pagine
    )


def lista_ctz(
    lingua: str = "en",
    sessione: Sessione | None = None,
    *,
    pausa_tra_pagine: float = _PAUSA_TRA_PAGINE,
    max_pagine: int = _MAX_PAGINE_LISTA
) -> list[StrumentoLista]:
    """Ottiene la lista dei CTZ quotati sul MOT."""
    return _scarica_lista(
        _URL_LISTA_CTZ,
        _estrai_strumenti,
        lingua,
        sessione,
        nome_lista="CTZ",
        pausa_tra_pagine=pausa_tra_pagine,
        max_pagine=max_pagine
    )


def lista_cct(
    lingua: str = "en",
    sessione: Sessione | None = None,
    *,
    pausa_tra_pagine: float = _PAUSA_TRA_PAGINE,
    max_pagine: int = _MAX_PAGINE_LISTA
) -> list[StrumentoLista]:
    """Ottiene la lista dei CCT quotati sul MOT."""
    return _scarica_lista(
        _URL_LISTA_CCT,
        _estrai_strumenti,
        lingua,
        sessione,
        nome_lista="CCT",
        pausa_tra_pagine=pausa_tra_pagine,
        max_pagine=max_pagine
    )


def lista_green_and_social(
    lingua: str = "en",
    sessione: Sessione | None = None,
    *,
    pausa_tra_pagine: float = _PAUSA_TRA_PAGINE,
    max_pagine: int = _MAX_PAGINE_LISTA
) -> list[StrumentoGreenSocial]:
    """Ottiene la lista degli strumenti Green & Social Bond."""
    return _scarica_lista(
        _URL_LISTA_GREEN_SOCIAL,
        _estrai_green_social,
        lingua,
        sessione,
        nome_lista="Green & Social Bond",
        pausa_tra_pagine=pausa_tra_pagine,
        max_pagine=max_pagine
    )
