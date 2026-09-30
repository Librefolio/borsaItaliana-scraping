"""Test offline di _estrai_valuta — la valuta di negoziazione non è la valuta di denominazione.

Le righe HTML riproducono quelle reali delle schede (verificate il 30/09/2026):

- ETC Invesco Physical Gold (IE00B579F325, ETFplus): l'unica riga di valuta è la
  *denominazione* — «Valuta di Denominazione USD» (it) / «Currency Denomination USD»
  (en). I prezzi però sono in EUR: la denominazione non è la valuta in cui lo
  strumento si negozia su Borsa Italiana.
- T-Bond USA (US912810TU25, EuroTLX): la riga di *negoziazione* —
  «Valuta di negoziazione USD» (it) / «Trading currency USD» (en).

Nessuna richiesta di rete: ogni caso è una pagina minima con la sola riga di valuta.
"""

from __future__ import annotations

import pytest
from bs4 import BeautifulSoup

from borsa_italiana_scraping.scheda import _estrai_valuta, _estrai_valuta_denominazione


def _pagina(righe: str) -> BeautifulSoup:
    return BeautifulSoup(f"<html><body><table>{righe}</table></body></html>", "lxml")


# Riga "denominazione" com'è nelle schede ETC/ETN (cella etichetta con classi, valore nudo).
RIGA_DENOMINAZIONE_IT = '<tr><td class="l-screen -xs-half">Valuta di Denominazione</td><td>USD</td></tr>'
RIGA_DENOMINAZIONE_EN = '<tr><td class="l-screen -xs-half">Currency Denomination</td><td>USD</td></tr>'

# Riga "negoziazione" com'è nelle schede obbligazioni EuroTLX (span/strong annidati).
RIGA_NEGOZIAZIONE_IT = '<tr><td><span class="t-text"><strong>Valuta di negoziazione</strong></span></td><td><span class="t-text -right">USD</span></td></tr>'
RIGA_NEGOZIAZIONE_EN = '<tr><td><span class="t-text"><strong>Trading currency</strong></span></td><td><span class="t-text -right">USD</span></td></tr>'


@pytest.mark.parametrize(
    ("riga", "lingua"),
    [(RIGA_DENOMINAZIONE_IT, "it"), (RIGA_DENOMINAZIONE_EN, "en")],
    ids=["denominazione-it", "denominazione-en"],
)
def test_la_denominazione_non_e_la_valuta_di_negoziazione(riga: str, lingua: str) -> None:
    """Una scheda con la sola denominazione in USD non si negozia in USD: resta il default EUR."""
    valuta, liquidazione = _estrai_valuta(_pagina(riga), lingua)
    assert valuta == "EUR"
    assert liquidazione is None


@pytest.mark.parametrize(
    ("riga", "lingua"),
    [(RIGA_DENOMINAZIONE_IT, "it"), (RIGA_DENOMINAZIONE_EN, "en")],
    ids=["denominazione-it", "denominazione-en"],
)
def test_la_denominazione_si_legge_a_parte(riga: str, lingua: str) -> None:
    assert _estrai_valuta_denominazione(_pagina(riga)) == "USD"


@pytest.mark.parametrize(
    ("riga", "lingua"),
    [(RIGA_NEGOZIAZIONE_IT, "it"), (RIGA_NEGOZIAZIONE_EN, "en")],
    ids=["negoziazione-it", "negoziazione-en"],
)
def test_la_valuta_di_negoziazione_resta_quella_della_pagina(riga: str, lingua: str) -> None:
    valuta, liquidazione = _estrai_valuta(_pagina(riga), lingua)
    assert valuta == "USD"
    assert liquidazione is None


def test_negoziazione_e_denominazione_insieme() -> None:
    """Con tutte e due le righe vince la negoziazione, e la denominazione resta disponibile a parte."""
    pagina = _pagina(RIGA_DENOMINAZIONE_IT.replace("USD", "GBP") + RIGA_NEGOZIAZIONE_IT)
    assert _estrai_valuta(pagina, "it") == ("USD", None)
    assert _estrai_valuta_denominazione(pagina) == "GBP"


def test_formato_negoziazione_liquidazione() -> None:
    riga = "<tr><td><strong>Negotiation Currency/ Settlement currency</strong></td><td>USD/EUR</td></tr>"
    assert _estrai_valuta(_pagina(riga), "en") == ("USD", "EUR")


def test_etichetta_generica_valuta_esatta() -> None:
    """L'etichetta generica «Valuta», da sola, è ancora la valuta di negoziazione."""
    riga = "<tr><td>Valuta</td><td>CHF</td></tr>"
    assert _estrai_valuta(_pagina(riga), "it") == ("CHF", None)


def test_nessuna_riga_di_valuta() -> None:
    """Pagina senza righe di valuta (es. azioni MTA): default EUR, nessuna denominazione."""
    pagina = _pagina("<tr><td>Codice Alfanumerico</td><td>ENEL</td></tr>")
    assert _estrai_valuta(pagina, "it") == ("EUR", None)
    assert _estrai_valuta_denominazione(pagina) is None
