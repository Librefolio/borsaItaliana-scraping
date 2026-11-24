"""Test di integrazione per storico.py — dati storici OHLCV."""

from datetime import date
from decimal import Decimal

import pytest

from borsa_italiana_scraping import Sessione, StrumentoNonTrovato, ottieni_storico
from borsa_italiana_scraping.tipi import PuntoStorico, StoricoRisultato

# ISIN di test
ISIN_ENEL = "IT0003128367"
ISIN_BTP = "IT0005634800"


@pytest.fixture(scope="module")
def sessione():
    """Sessione condivisa per tutti i test del modulo."""
    s = Sessione()
    yield s
    s.chiudi()


@pytest.mark.integration
class TestStoricoAPI:
    """Test dei dati storici con richieste reali."""

    def test_storico_enel_1y(self, sessione: Sessione) -> None:
        """Scarica lo storico ENEL 1Y e verifica la struttura."""
        risultato = ottieni_storico(ISIN_ENEL, periodo="1Y", sessione=sessione)

        assert isinstance(risultato, StoricoRisultato)
        assert risultato.isin == ISIN_ENEL
        assert risultato.codice_borsa == "XMIL"
        assert len(risultato.punti) > 100  # ~250 giorni di borsa

    def test_storico_btp_3m(self, sessione: Sessione) -> None:
        """Scarica lo storico BTP 3M."""
        risultato = ottieni_storico(ISIN_BTP, periodo="3M", sessione=sessione)

        assert isinstance(risultato, StoricoRisultato)
        assert len(risultato.punti) > 30

    def test_punto_storico_struttura(self, sessione: Sessione) -> None:
        """Verifica che ogni PuntoStorico abbia i campi corretti."""
        risultato = ottieni_storico(ISIN_ENEL, periodo="1M", sessione=sessione)
        assert len(risultato.punti) > 0

        punto = risultato.punti[0]
        assert isinstance(punto, PuntoStorico)
        assert isinstance(punto.data, date)
        assert isinstance(punto.apertura, Decimal)
        assert isinstance(punto.chiusura, Decimal)
        assert isinstance(punto.massimo, Decimal)
        assert isinstance(punto.minimo, Decimal)
        assert isinstance(punto.ultimo, Decimal)
        assert isinstance(punto.volume, int)

        # I prezzi devono essere positivi
        assert punto.apertura > 0
        assert punto.chiusura > 0
        assert punto.massimo >= punto.minimo

    def test_periodo_invalido(self, sessione: Sessione) -> None:
        """Un periodo non valido deve sollevare ValueError."""
        with pytest.raises(ValueError, match="non valido"):
            ottieni_storico(ISIN_ENEL, periodo="2Y", sessione=sessione)

    def test_isin_inesistente(self, sessione: Sessione) -> None:
        """Un ISIN inventato deve sollevare un'eccezione."""
        with pytest.raises(Exception):
            ottieni_storico("XX0000000000", periodo="1M", sessione=sessione)

    def test_sessione_temporanea(self) -> None:
        """Senza passare una sessione, ne viene creata una temporanea."""
        risultato = ottieni_storico(ISIN_ENEL, periodo="1M")
        assert len(risultato.punti) > 0
