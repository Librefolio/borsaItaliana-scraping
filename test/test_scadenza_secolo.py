"""Offline tests: bond expiry dates beyond 2068 (issue #4).

The scheda writes the expiry with a 2-digit year, and ``%y`` maps 00-68 to 20xx
and 69-99 to 19xx: Austria 2117 (AT0000A1XML2, ``20/09/17``) came out as
2017-09-20 and BTP 2072 (IT0005441883, ``01/03/72``) as 1972-03-01. The
fixtures are trimmed copies of the real AT0000A1XML2 pages.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from borsa_italiana_scraping import ottieni_scheda
from borsa_italiana_scraping.scheda import _correggi_secolo_scadenza
from borsa_italiana_scraping.tipi import SchedaStrumento

_FIXTURES = Path(__file__).parent / "fixtures"
_ISIN = "AT0000A1XML2"
_URL_SCHEDA = "https://www.borsaitaliana.it/borsa/obbligazioni/mot/euro-obbligazioni/scheda/AT0000A1XML2-MOTX.html"


class FakeSessione:
    """Serves the scheda fixture; the page has the issuer, so dati-completi is not needed."""

    def get_html_con_url(self, url: str, params: dict | None = None) -> tuple[BeautifulSoup, str]:
        lingua = (params or {})["lang"]
        html = (_FIXTURES / f"scheda_{_ISIN}_{lingua}.html").read_text(encoding="utf-8")
        return BeautifulSoup(html, "lxml"), f"{_URL_SCHEDA}?lang={lingua}"

    def get_html(self, url: str, params: dict | None = None) -> BeautifulSoup:
        raise AssertionError(f"unexpected request: {url}")

    def chiudi(self) -> None:
        pass


@pytest.mark.parametrize("lingua", ["it", "en"])
def test_scadenza_oltre_il_2100(lingua: str) -> None:
    scheda = ottieni_scheda(_ISIN, lingua=lingua, sessione=FakeSessione())

    assert scheda.nome == "Austria Tf 2,1% St2117 Eur"
    assert scheda.scadenza == date(2117, 9, 20)
    # The other dates are really in the past and stay as they are.
    assert scheda.data_primo_giorno == date(2017, 9, 26)
    assert scheda.data_prezzo_riferimento == date(2026, 11, 9)


def _scheda(scadenza: date | None, riferimento: date | None, primo_giorno: date | None = None) -> SchedaStrumento:
    scheda = SchedaStrumento(
        isin="XX0000000000",
        nome="test",
        prezzo=Decimal(100),
        variazione_percentuale=None,
        valuta="EUR",
        tipo="obbligazione",
        mercato="MOT",
    )
    scheda.scadenza = scadenza
    scheda.data_prezzo_riferimento = riferimento
    scheda.data_primo_giorno = primo_giorno
    return scheda


@pytest.mark.parametrize(
    ("letta", "riferimento", "primo_giorno", "attesa"),
    [
        # BTP 2072: "72" is read as 1972.
        (date(1972, 3, 1), date(2026, 11, 9), date(2021, 4, 12), date(2072, 3, 1)),
        # Austria 2117: "17" is read as 2017.
        (date(2017, 9, 20), date(2026, 11, 9), date(2017, 9, 26), date(2117, 9, 20)),
        # Only the first day of trading is known: it is enough.
        (date(2017, 9, 20), None, date(2017, 9, 26), date(2117, 9, 20)),
        # Normal expiry: unchanged.
        (date(2027, 7, 15), date(2026, 11, 6), date(2014, 4, 14), date(2027, 7, 15)),
        # Expires on the reference date itself: unchanged.
        (date(2026, 11, 9), date(2026, 11, 9), None, date(2026, 11, 9)),
        # 29 February into a year that is not a leap year.
        (date(2000, 2, 29), date(2026, 11, 9), None, date(2100, 2, 28)),
    ],
)
def test_correggi_secolo_scadenza(
    letta: date, riferimento: date | None, primo_giorno: date | None, attesa: date
) -> None:
    scheda = _scheda(letta, riferimento, primo_giorno)

    _correggi_secolo_scadenza(scheda)

    assert scheda.scadenza == attesa
    assert scheda.data_prezzo_riferimento == riferimento
    assert scheda.data_primo_giorno == primo_giorno


def test_senza_date_di_confronto_non_cambia_nulla() -> None:
    scheda = _scheda(date(1972, 3, 1), None, None)

    _correggi_secolo_scadenza(scheda)

    assert scheda.scadenza == date(1972, 3, 1)


def test_senza_scadenza_non_fa_nulla() -> None:
    scheda = _scheda(None, date(2026, 11, 9))

    _correggi_secolo_scadenza(scheda)

    assert scheda.scadenza is None
