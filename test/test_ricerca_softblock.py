"""Test unitari per la rilevazione del soft-block WAF in ricerca.py (mock, no rete)."""

from __future__ import annotations

import pytest

from borsa_italiana_scraping import RicercaNonDisponibile, cerca

_VUOTO = {"news": [], "pages": [], "terms": [], "documents": [], "quotes": []}
_ENEL_PIENO = {
    "news": [{"id": "x", "title": "Enel news"}],
    "pages": [],
    "terms": [],
    "documents": [],
    "quotes": [
        {
            "symbol": "IT0003128367",
            "title": "Enel",
            "typeLabel": "Azione",
            "mic": "MTAA",
            "mercato": "MTA",
            "link": "https://www.borsaitaliana.it/borsa/search/scheda.html?code=IT0003128367&mic=MTAA&lang=it",
        }
    ],
}


class FakeSessione:
    """Sessione finta: risponde per query, e registra le query fatte."""

    def __init__(self, per_query: dict[str, dict], default: dict):
        self.per_query = per_query
        self.default = default
        self.queries: list[str] = []

    def get_json(self, url, params=None):
        q = (params or {}).get("q", "")
        self.queries.append(q)
        return self.per_query.get(q, self.default)

    def chiudi(self):
        pass


def test_ricerca_vuota_legittima_non_e_blocco() -> None:
    """Query senza risultati + sonda ENEL piena → [] (strumento inesistente), nessun errore."""
    s = FakeSessione({"ENEL": _ENEL_PIENO}, default=_VUOTO)
    assert cerca("XYZNONEXISTENT123", sessione=s) == []
    assert "ENEL" in s.queries  # la sonda è stata fatta


def test_soft_block_rilevato() -> None:
    """Tutto vuoto anche per ENEL → RicercaNonDisponibile (rate-limit WAF), non []."""
    s = FakeSessione({}, default=_VUOTO)
    with pytest.raises(RicercaNonDisponibile, match="rate-limit"):
        cerca("US912810TU25", sessione=s)


def test_ricerca_con_risultati_non_sonda() -> None:
    """Con risultati presenti la sonda non parte mai (niente richiesta extra)."""
    s = FakeSessione({"ENEL": _ENEL_PIENO}, default=_VUOTO)
    risultati = cerca("ENEL", sessione=s)
    assert len(risultati) == 1
    assert risultati[0].isin == "IT0003128367"
    assert s.queries == ["ENEL"]


def test_soft_block_sonda_fallita_in_rete() -> None:
    """Se la sonda stessa va in errore di rete, si ricade nel '[]' legacy."""

    class SondaRotta(FakeSessione):
        def get_json(self, url, params=None):
            q = (params or {}).get("q", "")
            if q == "ENEL":
                raise ConnectionError("giù")
            return _VUOTO

    assert cerca("QUALCOSA", sessione=SondaRotta({}, _VUOTO)) == []
