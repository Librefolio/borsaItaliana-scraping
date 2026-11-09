"""Offline tests: the scheda gives the same numbers in Italian and in English.

The ``?lang=it`` pages use their own labels («Min Oggi», «Rendimento effettivo a
scadenza lordo», «Tasso Cedola su base Annua», «Performance 1 mese», …), which the
parser did not know: those fields stayed ``None`` in Italian. The fixtures are
trimmed copies of the real pages of a bond (AT0000383864) and a stock (Enel).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from borsa_italiana_scraping import ottieni_scheda

_FIXTURES = Path(__file__).parent / "fixtures"
_URL = {
    "AT0000383864": "https://www.borsaitaliana.it/borsa/obbligazioni/mot/euro-obbligazioni/scheda/AT0000383864-MOTX.html",
    "IT0003128367": "https://www.borsaitaliana.it/borsa/azioni/scheda/IT0003128367-MTAA.html",
}


def _soup(nome: str) -> BeautifulSoup:
    return BeautifulSoup((_FIXTURES / nome).read_text(encoding="utf-8"), "lxml")


class FakeSessione:
    """Serves the scheda fixture of the requested ISIN, and dati-completi for the bond."""

    def get_html_con_url(self, url: str, params: dict | None = None) -> tuple[BeautifulSoup, str]:
        isin, lingua = params["code"], params["lang"]
        return _soup(f"scheda_{isin}_{lingua}.html"), f"{_URL[isin]}?lang={lingua}"

    def get_html(self, url: str, params: dict | None = None) -> BeautifulSoup:
        return _soup(f"dati_completi_{params['isin']}_{params['lang']}.html")

    def chiudi(self) -> None:
        pass


_CAMPI_OBBLIGAZIONE = {
    "prezzo": Decimal("102.193"),
    "apertura": Decimal("102.193"),
    "minimo_giorno": Decimal("102.193"),
    "massimo_giorno": Decimal("102.193"),
    "minimo_anno": Decimal("101.932"),
    "massimo_anno": Decimal("106.41"),
    "rendimento_lordo": Decimal("2.67"),
    "rendimento_netto": Decimal("1.92"),
    "rateo_lordo": Decimal("2.02055"),
    "rateo_netto": Decimal("1.76798"),
    "duration_modificata": Decimal("0.66"),
    "cedola_annua": Decimal("6.25"),
    "cedola_periodale": Decimal("6.25"),
    "outstanding": Decimal("7131099000"),
    "convenzione_giorni": "ACT/ACT (PERIODIC BASIS)",
    "prezzo_riferimento": Decimal("102.344"),
    "scadenza": date(2027, 7, 15),
    "data_prezzo_riferimento": date(2026, 11, 6),
    "data_primo_giorno": date(2014, 4, 14),
}

_CAMPI_AZIONE = {
    "prezzo": Decimal("9.861"),
    "minimo_giorno": Decimal("9.619"),
    "massimo_giorno": Decimal("9.863"),
    "minimo_anno": Decimal("8.599"),
    "massimo_anno": Decimal("10.31"),
    "performance_1m": Decimal("12.59"),
    "performance_6m": Decimal("2.45"),
    "performance_1y": Decimal("11.25"),
}


@pytest.mark.parametrize("lingua", ["it", "en"])
@pytest.mark.parametrize(
    ("isin", "attesi"),
    [("AT0000383864", _CAMPI_OBBLIGAZIONE), ("IT0003128367", _CAMPI_AZIONE)],
    ids=["obbligazione", "azione"],
)
def test_stessi_valori_in_entrambe_le_lingue(isin: str, attesi: dict, lingua: str) -> None:
    scheda = ottieni_scheda(isin, lingua=lingua, sessione=FakeSessione())

    letti = {campo: getattr(scheda, campo) for campo in attesi}
    assert letti == attesi


def test_frequenza_cedola_nella_lingua_della_pagina() -> None:
    """Text fields keep the page's wording."""
    assert ottieni_scheda("AT0000383864", lingua="it", sessione=FakeSessione()).frequenza_cedola == "Annuale"
    assert ottieni_scheda("AT0000383864", lingua="en", sessione=FakeSessione()).frequenza_cedola == "Annually"
