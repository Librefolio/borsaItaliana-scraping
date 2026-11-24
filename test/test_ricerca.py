"""Test di integrazione per ricerca.py — ricerca strumenti."""

import pytest

from borsa_italiana_scraping import Sessione, cerca
from borsa_italiana_scraping.tipi import RisultatoRicerca


@pytest.fixture(scope="module")
def sessione():
    s = Sessione()
    yield s
    s.chiudi()


@pytest.mark.integration
class TestRicerca:
    """Test della ricerca strumenti."""

    def test_cerca_enel(self, sessione: Sessione) -> None:
        """Cerca 'ENEL' e verifica il formato dei risultati."""
        risultati = cerca("ENEL", lingua="it", sessione=sessione)
        assert isinstance(risultati, list)
        assert len(risultati) > 0, "La ricerca 'ENEL' deve trovare almeno un risultato"
        r = risultati[0]
        assert isinstance(r, RisultatoRicerca)
        assert r.isin == "IT0003128367"
        assert r.nome
        assert r.tipo

    def test_cerca_btp(self, sessione: Sessione) -> None:
        """Cerca 'BTP' e verifica la presenza di obbligazioni."""
        risultati = cerca("BTP", lingua="it", sessione=sessione)
        assert isinstance(risultati, list)
        assert len(risultati) > 0
        # Tutti i risultati devono avere ISIN
        for r in risultati:
            assert r.isin
            assert r.isin.startswith("IT")

    def test_cerca_isin_esatto(self, sessione: Sessione) -> None:
        """Cerca un ISIN esatto — deve usare exactSymbolMatch."""
        risultati = cerca("IT0005634800", lingua="it", sessione=sessione)
        assert len(risultati) >= 1
        # Il match esatto deve essere il primo risultato
        assert risultati[0].isin == "IT0005634800"

    def test_cerca_inglese(self, sessione: Sessione) -> None:
        """Cerca in inglese."""
        risultati = cerca("ENEL", lingua="en", sessione=sessione)
        assert isinstance(risultati, list)
        assert len(risultati) > 0

    def test_cerca_campi_estesi(self, sessione: Sessione) -> None:
        """Verifica i nuovi campi (link, dettaglio_mercato, sotto_tipo)."""
        risultati = cerca("ENEL", lingua="en", sessione=sessione)
        r = risultati[0]
        assert r.link is not None
        assert "borsaitaliana.it" in r.link
        assert r.dettaglio_mercato is not None  # "Euronext Milan"
        assert r.sotto_tipo is not None  # "MTA"
        assert r.comparto is not None  # "AZIONARIO"

    def test_lingua_invalida(self, sessione: Sessione) -> None:
        """Una lingua non supportata deve sollevare ValueError."""
        with pytest.raises(ValueError):
            cerca("test", lingua="de", sessione=sessione)
