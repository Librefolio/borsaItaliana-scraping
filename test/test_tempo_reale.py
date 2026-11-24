"""Test di integrazione per tempo_reale.py — intraday e prezzo corrente."""

from datetime import date, datetime
from decimal import Decimal

import pytest

from borsa_italiana_scraping import (
    DatiNonDisponibili,
    Sessione,
    ottieni_intraday,
    ottieni_prezzo_corrente,
)
from borsa_italiana_scraping.tipi import IntradayRisultato, PrezzoCorrente, PuntoIntraday

ISIN_ENEL = "IT0003128367"
ISIN_BTP = "IT0005634800"


@pytest.fixture(scope="module")
def sessione():
    s = Sessione()
    yield s
    s.chiudi()


@pytest.mark.integration
class TestIntraday:
    """Test dei dati intraday."""

    def test_intraday_enel(self, sessione: Sessione) -> None:
        """Scarica intraday ENEL — può fallire se il mercato è chiuso."""
        try:
            risultato = ottieni_intraday(ISIN_ENEL, risoluzione="5MN", sessione=sessione)
            assert isinstance(risultato, IntradayRisultato)
            assert risultato.isin == ISIN_ENEL
            if risultato.punti:
                punto = risultato.punti[0]
                assert isinstance(punto, PuntoIntraday)
                assert isinstance(punto.orario, datetime)
                assert isinstance(punto.apertura, Decimal)
                assert punto.apertura > 0
        except DatiNonDisponibili:
            pytest.skip("Mercato chiuso — nessun dato intraday disponibile")

    def test_risoluzione_invalida(self, sessione: Sessione) -> None:
        """Una risoluzione non valida deve sollevare ValueError."""
        with pytest.raises(ValueError, match="non valida"):
            ottieni_intraday(ISIN_ENEL, risoluzione="2MN", sessione=sessione)


@pytest.mark.integration
class TestPrezzoCorrente:
    """Test del prezzo corrente."""

    def test_prezzo_corrente_enel(self, sessione: Sessione) -> None:
        """Ottiene il prezzo corrente di ENEL."""
        prezzo = ottieni_prezzo_corrente(ISIN_ENEL, sessione=sessione)

        assert isinstance(prezzo, PrezzoCorrente)
        assert prezzo.isin == ISIN_ENEL
        assert isinstance(prezzo.prezzo, Decimal)
        assert prezzo.prezzo > 0
        assert isinstance(prezzo.data, date)
        assert prezzo.fonte in ("api", "scraping")

    def test_prezzo_corrente_btp(self, sessione: Sessione) -> None:
        """Ottiene il prezzo corrente del BTP Più."""
        prezzo = ottieni_prezzo_corrente(ISIN_BTP, sessione=sessione)

        assert isinstance(prezzo, PrezzoCorrente)
        assert prezzo.prezzo > 0
