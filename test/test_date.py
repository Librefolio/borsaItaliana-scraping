"""Unit tests (offline) for the language-aware date parsers.

Borsa Italiana writes 2-digit-year dates as ``dd/mm/yy`` on ``?lang=it`` pages
and as ``yy/mm/dd`` on ``?lang=en`` pages (issue #1). 4-digit-year dates
(``dd/mm/yyyy``, ``yyyy/mm/dd``, ISO) are unambiguous and must parse the same in
both languages. The sample values below are real strings seen on the site.
"""

from datetime import date

import pytest
from bs4 import BeautifulSoup

from borsa_italiana_scraping.fondi import _estrai_dati_pagina_fondo
from borsa_italiana_scraping.lista import _parsa_data_lista
from borsa_italiana_scraping.scheda import _parsa_data_scheda


@pytest.mark.parametrize(
    ("testo", "lingua", "atteso"),
    [
        # AT0000383864 expiry date: 15 July 2027
        ("15/07/27", "it", date(2027, 7, 15)),
        ("27/07/15", "en", date(2027, 7, 15)),
        # IT0005722514 first day of trading: 10 July 2026
        ("10/07/26", "it", date(2026, 7, 10)),
        ("26/07/10", "en", date(2026, 7, 10)),
        # DE000A30V9J0 expiry date: 7 June 2030
        ("07/06/30", "it", date(2030, 6, 7)),
        ("30/06/07", "en", date(2030, 6, 7)),
        # XS2338004497 expiry date: 17 February 2027
        ("17/02/27", "it", date(2027, 2, 17)),
        ("27/02/17", "en", date(2027, 2, 17)),
    ],
)
def test_scheda_data_ambigua_segue_la_lingua(testo: str, lingua: str, atteso: date) -> None:
    assert _parsa_data_scheda(testo, lingua) == atteso


@pytest.mark.parametrize("lingua", ["it", "en"])
@pytest.mark.parametrize(
    ("testo", "atteso"),
    [
        # "Data di riferimento" / "Reference price date": dd/mm/yyyy in both languages
        ("06/11/2026", date(2026, 11, 6)),
        ("2027/11/01", date(2027, 11, 1)),
        ("2027-11-01", date(2027, 11, 1)),
        ("01-11-2027", date(2027, 11, 1)),
        ("01.11.2027", date(2027, 11, 1)),
    ],
)
def test_scheda_data_non_ambigua_uguale_in_entrambe_le_lingue(testo: str, atteso: date, lingua: str) -> None:
    assert _parsa_data_scheda(testo, lingua) == atteso


@pytest.mark.parametrize("lingua", ["it", "en"])
@pytest.mark.parametrize("testo", ["", "-", "  ", "n.d.", "99/99/99"])
def test_scheda_data_vuota_o_invalida(testo: str, lingua: str) -> None:
    assert _parsa_data_scheda(testo, lingua) is None


def test_scheda_lingua_maiuscola() -> None:
    assert _parsa_data_scheda("15/07/27", "IT") == date(2027, 7, 15)


def test_scheda_ripiego_sul_formato_dell_altra_lingua() -> None:
    """A 2-digit date that is invalid in the page order falls back to the other one."""
    # "97/07/15" cannot be dd/mm/yy (day 97): read as yy/mm/dd.
    assert _parsa_data_scheda("97/07/15", "it") == date(1997, 7, 15)
    # "15/07/97" cannot be yy/mm/dd (day 97): read as dd/mm/yy.
    assert _parsa_data_scheda("15/07/97", "en") == date(1997, 7, 15)


@pytest.mark.parametrize(
    ("testo", "lingua", "atteso"),
    [
        # Real BTP list values (4-digit years in both languages)
        ("01/11/2027", "it", date(2027, 11, 1)),
        ("2027/11/01", "en", date(2027, 11, 1)),
        ("15/02/2037", "it", date(2037, 2, 15)),
        ("2037/02/15", "en", date(2037, 2, 15)),
        # 2-digit years follow the page language, like the scheda
        ("15/07/27", "it", date(2027, 7, 15)),
        ("27/07/15", "en", date(2027, 7, 15)),
        ("", "it", None),
        ("-", "en", None),
    ],
)
def test_lista_data(testo: str, lingua: str, atteso: date | None) -> None:
    assert _parsa_data_lista(testo, lingua) == atteso


def _pagina_fondo(data: str) -> BeautifulSoup:
    html = f"""
    <h1>Eurizon Next 2.0 Alloc. Divers. 40 P Cap Eur</h1>
    <span class="-formatPrice">122,05</span>
    <span class="-percPrice">+0,12%</span>
    <div class="summary-fase">
      <span>Valuta: <strong>EUR</strong></span>
      <span>Data: <strong>{data}</strong></span>
    </div>
    """
    return BeautifulSoup(html, "html.parser")


@pytest.mark.parametrize(
    ("testo", "atteso"),
    [
        # Fund pages are Italian only: dd/mm/yy
        ("05/11/26", date(2026, 11, 5)),
        ("12/03/26", date(2026, 3, 12)),
        ("05/11/2026", date(2026, 11, 5)),
    ],
)
def test_fondi_data_nav_in_italiano(testo: str, atteso: date) -> None:
    _nome, _nav, _var, _valuta, data_nav = _estrai_dati_pagina_fondo(_pagina_fondo(testo))
    assert data_nav == atteso
