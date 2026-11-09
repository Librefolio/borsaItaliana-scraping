"""Offline tests: bond dates read from scheda pages in both languages (issue #1).

The fixtures are trimmed copies of the real AT0000383864 pages. Its expiry
date is 15 July 2027: the ``?lang=it`` page writes ``15/07/27`` and the
``?lang=en`` page writes ``27/07/15``. Both must give 2027-07-15.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from borsa_italiana_scraping import ottieni_scheda
from borsa_italiana_scraping.scheda import _arricchisci_obbligazione
from borsa_italiana_scraping.tipi import SchedaStrumento

_FIXTURES = Path(__file__).parent / "fixtures"
_ISIN = "AT0000383864"
_URL_SCHEDA = "https://www.borsaitaliana.it/borsa/obbligazioni/mot/euro-obbligazioni/scheda/AT0000383864-MOTX.html"


def _soup(nome: str) -> BeautifulSoup:
    return BeautifulSoup((_FIXTURES / nome).read_text(encoding="utf-8"), "lxml")


class FakeSessione:
    """Serves the scheda fixture on the universal URL and dati-completi on get_html."""

    def __init__(self) -> None:
        self.richieste: list[tuple[str, dict]] = []

    def get_html_con_url(self, url: str, params: dict | None = None) -> tuple[BeautifulSoup, str]:
        lingua = (params or {})["lang"]
        self.richieste.append((url, dict(params or {})))
        return _soup(f"scheda_{_ISIN}_{lingua}.html"), f"{_URL_SCHEDA}?lang={lingua}"

    def get_html(self, url: str, params: dict | None = None) -> BeautifulSoup:
        lingua = (params or {})["lang"]
        self.richieste.append((url, dict(params or {})))
        return _soup(f"dati_completi_{_ISIN}_{lingua}.html")

    def chiudi(self) -> None:
        pass


@pytest.mark.parametrize(("lingua", "prezzo"), [("it", Decimal("102.193")), ("en", Decimal("102.193"))])
def test_ottieni_scheda_date_uguali_in_entrambe_le_lingue(lingua: str, prezzo: Decimal) -> None:
    scheda = ottieni_scheda(_ISIN, lingua=lingua, sessione=FakeSessione())

    assert scheda.tipo == "obbligazione"
    assert scheda.prezzo == prezzo
    assert scheda.scadenza == date(2027, 7, 15)
    assert scheda.data_prezzo_riferimento == date(2026, 11, 6)
    assert scheda.data_primo_giorno == date(2014, 4, 14)


@pytest.mark.parametrize("lingua", ["it", "en"])
def test_scadenza_letta_dalla_scheda_non_dal_rendimento(lingua: str) -> None:
    """The scheda page alone gives the expiry date.

    The yield rows ("Rendimento effettivo a scadenza lordo", "Gross yield to
    maturity") come before the expiry row and contain "scadenza"/"maturity":
    the expiry label must match exactly, not as a substring.
    """
    scheda = SchedaStrumento(
        isin=_ISIN,
        nome="Austria Tf 6.25% Lg27 Eur",
        prezzo=Decimal("102.193"),
        variazione_percentuale=None,
        valuta="EUR",
        tipo="obbligazione",
        mercato="",
    )
    _arricchisci_obbligazione(scheda, _soup(f"scheda_{_ISIN}_{lingua}.html"), lingua)

    assert scheda.scadenza == date(2027, 7, 15)
    assert scheda.data_prezzo_riferimento == date(2026, 11, 6)
    assert scheda.data_primo_giorno == date(2014, 4, 14)
    assert scheda.prezzo_riferimento == Decimal("102.344")
