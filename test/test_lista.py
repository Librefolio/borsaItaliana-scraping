"""Offline tests for lista_btp() pagination (issue #2).

The BTP list is split into pages of 20 rows (``?page=N``). The fixtures are
trimmed copies of the first two real pages (3 rows each); the second one is the
last page, so its paginator has no "Next" link.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from borsa_italiana_scraping import DatiNonDisponibili, lista_btp
from borsa_italiana_scraping import lista as lista_mod

_FIXTURES = Path(__file__).parent / "fixtures"

# Past the last page the site returns the table header only (seen live with page=50).
_HTML_PAGINA_VUOTA = """
<html><body>
  <table class="m-table -firstlevel">
    <tr class="m-table__first"></tr>
    <tr class="u-hidden -xs">
      <th><strong>Isin</strong></th><th><strong>Description</strong></th><th><strong>Last</strong></th>
      <th><strong>Coupon</strong></th><th><strong>Expiry</strong></th><th> </th>
    </tr>
  </table>
</body></html>
"""
_HTML_SENZA_TABELLA = "<html><body><p>Request unsuccessful. Incapsula incident ID: 0-0</p></body></html>"

_ISIN_P1 = ["IT0001174611", "IT0001247391", "IT0003535157"]
_ISIN_P2 = ["IT0003745541", "IT0003934657", "IT0004976541"]


def _pagina(n: int, senza_paginatore: bool = False) -> BeautifulSoup:
    soup = BeautifulSoup((_FIXTURES / f"lista_btp_en_p{n}.html").read_text(encoding="utf-8"), "lxml")
    if senza_paginatore:
        soup.find("div", class_="m-pagination").decompose()
    return soup


class FakeSessione:
    """Returns one page per ``page`` parameter and records every request."""

    def __init__(self, pagine: dict[int, BeautifulSoup], default: str = _HTML_PAGINA_VUOTA) -> None:
        self.pagine = pagine
        self.default = default
        self.richieste: list[dict] = []

    def get_html(self, url: str, params: dict | None = None) -> BeautifulSoup:
        params = dict(params or {})
        self.richieste.append(params)
        n = int(params.get("page", "1"))
        if n in self.pagine:
            return self.pagine[n]
        return BeautifulSoup(self.default, "lxml")

    def chiudi(self) -> None:
        pass


@pytest.fixture(autouse=True)
def niente_pause(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Record the pauses between pages instead of sleeping."""
    pause: list[float] = []
    monkeypatch.setattr(lista_mod.time, "sleep", pause.append)
    return pause


def test_legge_tutte_le_pagine(niente_pause: list[float]) -> None:
    s = FakeSessione({1: _pagina(1), 2: _pagina(2)})

    risultati = lista_btp(lingua="en", sessione=s)

    assert [r.isin for r in risultati] == _ISIN_P1 + _ISIN_P2
    # Page 2 has no "Next" link: no third request.
    assert s.richieste == [{"lang": "en"}, {"lang": "en", "page": "2"}]
    # A gentle pause before every page after the first one.
    assert niente_pause == [1.0]

    primo = risultati[0]
    assert primo.nome == "Btp-1nv27 6,5%"
    assert primo.ultimo_prezzo == Decimal("103.19")
    assert primo.cedola == Decimal("3.25")
    assert primo.scadenza == date(2027, 11, 1)
    assert primo.mic == "MOTX"
    assert risultati[-1].scadenza == date(2029, 9, 1)
    assert risultati[1].ultimo_prezzo is None


def test_senza_paginatore_si_ferma_alla_pagina_vuota() -> None:
    """Without a paginator block it keeps reading until an empty page."""
    s = FakeSessione({1: _pagina(1, senza_paginatore=True), 2: _pagina(2, senza_paginatore=True)})

    risultati = lista_btp(lingua="en", sessione=s)

    assert [r.isin for r in risultati] == _ISIN_P1 + _ISIN_P2
    assert [r.get("page") for r in s.richieste] == [None, "2", "3"]


def test_si_ferma_se_una_pagina_ripete_la_precedente() -> None:
    """A page that only repeats ISINs already read ends the loop (no duplicates)."""
    s = FakeSessione({1: _pagina(1, senza_paginatore=True), 2: _pagina(1, senza_paginatore=True)})

    risultati = lista_btp(lingua="en", sessione=s)

    assert [r.isin for r in risultati] == _ISIN_P1
    assert len(s.richieste) == 2


def test_limite_massimo_di_pagine() -> None:
    s = FakeSessione({1: _pagina(1), 2: _pagina(2)})

    risultati = lista_btp(lingua="en", sessione=s, max_pagine=1)

    assert [r.isin for r in risultati] == _ISIN_P1
    assert len(s.richieste) == 1


def test_pausa_configurabile(niente_pause: list[float]) -> None:
    s = FakeSessione({1: _pagina(1), 2: _pagina(2)})

    lista_btp(lingua="en", sessione=s, pausa_tra_pagine=0)

    assert niente_pause == []


def test_prima_pagina_senza_tabella_solleva() -> None:
    s = FakeSessione({}, default=_HTML_SENZA_TABELLA)

    with pytest.raises(DatiNonDisponibili, match="non trovata"):
        lista_btp(lingua="en", sessione=s)


def test_pagina_successiva_senza_tabella_non_restituisce_lista_incompleta() -> None:
    """A WAF/challenge page in the middle raises instead of truncating the list."""
    s = FakeSessione({1: _pagina(1)}, default=_HTML_SENZA_TABELLA)

    with pytest.raises(DatiNonDisponibili, match="pagina 2"):
        lista_btp(lingua="en", sessione=s)
