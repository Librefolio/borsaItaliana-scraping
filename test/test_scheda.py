"""Test di integrazione per scheda.py — scraping pagina strumento."""

from datetime import date
from decimal import Decimal

import pytest

from borsa_italiana_scraping import Sessione, ottieni_profilo_societa, ottieni_scheda
from borsa_italiana_scraping.tipi import (
    Azionista,
    ContattiSocieta,
    DatoSocietario,
    Dirigente,
    IndirizzoSocieta,
    ProfiloSocieta,
    SchedaStrumento,
)

ISIN_ENEL = "IT0003128367"
ISIN_BTP = "IT0005634800"
ISIN_BTP_FISSO = "IT0005560948"


@pytest.fixture(scope="module")
def sessione():
    s = Sessione()
    yield s
    s.chiudi()


@pytest.mark.integration
class TestSchedaObbligazione:
    """Test scraping scheda BTP."""

    def test_scheda_btp_en(self, sessione: Sessione) -> None:
        """Scheda BTP in inglese — verifica campi base."""
        scheda = ottieni_scheda(ISIN_BTP, lingua="en", sessione=sessione)

        assert isinstance(scheda, SchedaStrumento)
        assert scheda.isin == ISIN_BTP
        assert isinstance(scheda.prezzo, Decimal)
        assert scheda.prezzo > 0
        assert scheda.valuta == "EUR"
        assert scheda.tipo == "obbligazione"
        assert scheda.nome

    def test_scheda_btp_campi_specifici(self, sessione: Sessione) -> None:
        """La scheda BTP deve avere i campi specifici obbligazione."""
        scheda = ottieni_scheda(ISIN_BTP_FISSO, lingua="en", sessione=sessione)

        assert scheda.tipo == "obbligazione"
        assert scheda.scadenza is None or isinstance(scheda.scadenza, date)

    def test_scheda_btp_campi_comuni(self, sessione: Sessione) -> None:
        """Verifica campi comuni (descrizione, URL, range)."""
        scheda = ottieni_scheda(ISIN_BTP, lingua="en", sessione=sessione)

        # Descrizione dal meta tag
        assert scheda.descrizione is not None
        assert ISIN_BTP in scheda.descrizione

        # URL pagina (dal redirect)
        assert scheda.url_pagina is not None
        assert "borsaitaliana.it" in scheda.url_pagina

        # Range giornaliero
        assert scheda.apertura is not None and scheda.apertura > 0

        # Range annuale
        assert scheda.minimo_anno is not None and scheda.minimo_anno > 0
        assert scheda.massimo_anno is not None and scheda.massimo_anno > 0
        assert scheda.minimo_anno <= scheda.massimo_anno

    def test_scheda_btp_nuovi_campi_bond(self, sessione: Sessione) -> None:
        """Verifica i nuovi campi obbligazione (frequenza, convenzione, ecc.)."""
        scheda = ottieni_scheda(ISIN_BTP, lingua="en", sessione=sessione)

        assert scheda.frequenza_cedola is not None  # "Quarterly"
        assert scheda.convenzione_giorni is not None  # "ACT/ACT (ICMA)"
        assert scheda.struttura_bond is not None
        assert scheda.outstanding is not None and scheda.outstanding > 0
        assert scheda.tipologia is not None  # "Italian Government Bonds"
        assert scheda.emittente is not None
        assert scheda.prezzo_riferimento is not None and scheda.prezzo_riferimento > 0
        assert scheda.data_prezzo_riferimento is not None
        assert isinstance(scheda.data_prezzo_riferimento, date)
        assert scheda.data_primo_giorno is not None
        assert isinstance(scheda.data_primo_giorno, date)


@pytest.mark.integration
class TestSchedaAzione:
    """Test scraping scheda azione."""

    def test_scheda_enel_en(self, sessione: Sessione) -> None:
        """Scheda ENEL in inglese — campi base."""
        scheda = ottieni_scheda(ISIN_ENEL, lingua="en", sessione=sessione)

        assert isinstance(scheda, SchedaStrumento)
        assert scheda.isin == ISIN_ENEL
        assert isinstance(scheda.prezzo, Decimal)
        assert scheda.prezzo > 0
        assert scheda.tipo == "azione"

    def test_scheda_enel_campi_comuni(self, sessione: Sessione) -> None:
        """Verifica campi comuni per azione."""
        scheda = ottieni_scheda(ISIN_ENEL, lingua="en", sessione=sessione)

        assert scheda.descrizione is not None
        assert scheda.url_pagina is not None
        assert scheda.apertura is not None and scheda.apertura > 0
        assert scheda.minimo_anno is not None
        assert scheda.massimo_anno is not None

    def test_scheda_enel_nuovi_campi_stock(self, sessione: Sessione) -> None:
        """Verifica nuovi campi azione (indici, performance)."""
        scheda = ottieni_scheda(ISIN_ENEL, lingua="en", sessione=sessione)

        assert scheda.settore is not None  # "Utilities"
        assert scheda.ticker is not None  # "ENEL"

        # Indici di appartenenza
        assert scheda.indici is not None
        assert isinstance(scheda.indici, list)
        assert len(scheda.indici) > 0
        assert any("FTSE MIB" in i for i in scheda.indici)

        # Performance (possono essere None fuori orario ma ENEL li ha sempre)
        assert scheda.performance_1m is not None
        assert scheda.performance_6m is not None
        assert scheda.performance_1y is not None


@pytest.mark.integration
@pytest.mark.parametrize("lingua", ["it", "en"])
class TestProfiloSocieta:
    """Test di integrazione per il Profilo Società ENEL."""

    def test_profilo_base(self, sessione: Sessione, lingua: str) -> None:
        profilo = ottieni_profilo_societa(ISIN_ENEL, lingua=lingua, sessione=sessione)
        assert isinstance(profilo, ProfiloSocieta)
        assert profilo.isin == ISIN_ENEL

    def test_descrizione(self, sessione: Sessione, lingua: str) -> None:
        profilo = ottieni_profilo_societa(ISIN_ENEL, lingua=lingua, sessione=sessione)
        assert profilo.descrizione is not None
        assert len(profilo.descrizione) > 20

    def test_dirigenti(self, sessione: Sessione, lingua: str) -> None:
        profilo = ottieni_profilo_societa(ISIN_ENEL, lingua=lingua, sessione=sessione)
        assert isinstance(profilo.dirigenti, list)

        for dirigente in profilo.dirigenti:
            assert isinstance(dirigente, Dirigente)
            assert dirigente.ruolo
            assert dirigente.nominativo

    def test_dati_societari(self, sessione: Sessione, lingua: str) -> None:
        profilo = ottieni_profilo_societa(ISIN_ENEL, lingua=lingua, sessione=sessione)
        assert isinstance(profilo.dati_principali, list)
        assert isinstance(profilo.anni_disponibili, list)
        assert all(isinstance(a, int) for a in profilo.anni_disponibili)
        assert profilo.anni_disponibili == sorted(profilo.anni_disponibili, reverse=True)

        for dato in profilo.dati_principali:
            assert isinstance(dato, DatoSocietario)
            assert dato.voce
            assert isinstance(dato.valori, dict)

    def test_azionisti(self, sessione: Sessione, lingua: str) -> None:
        profilo = ottieni_profilo_societa(ISIN_ENEL, lingua=lingua, sessione=sessione)
        assert isinstance(profilo.azionisti, list)
        assert len(profilo.azionisti) > 0

        for azionista in profilo.azionisti:
            assert isinstance(azionista, Azionista)
            assert azionista.nominativo
            assert azionista.percentuale is not None
            assert Decimal(0) <= azionista.percentuale <= Decimal(100)

    def test_indirizzo(self, sessione: Sessione, lingua: str) -> None:
        profilo = ottieni_profilo_societa(ISIN_ENEL, lingua=lingua, sessione=sessione)
        assert profilo.indirizzo is not None
        assert isinstance(profilo.indirizzo, IndirizzoSocieta)
        assert any((
            profilo.indirizzo.ragione_sociale,
            profilo.indirizzo.via,
            profilo.indirizzo.cap,
            profilo.indirizzo.comune,
            profilo.indirizzo.paese,
        ))

    def test_contatti(self, sessione: Sessione, lingua: str) -> None:
        profilo = ottieni_profilo_societa(ISIN_ENEL, lingua=lingua, sessione=sessione)
        assert isinstance(profilo.contatti, ContattiSocieta)
        assert any((profilo.contatti.telefono,profilo.contatti.sito_web))

    def test_metadati(self, sessione: Sessione, lingua: str) -> None:
        profilo = ottieni_profilo_societa(ISIN_ENEL, lingua=lingua, sessione=sessione)

        if profilo.fonte is not None:
            assert profilo.fonte.strip()

        if profilo.ultimo_aggiornamento is not None:
            assert isinstance(profilo.ultimo_aggiornamento, date)


def test_profilo_societa_lingua_default(sessione: Sessione) -> None:
    """La lingua predefinita deve essere inglese."""
    profilo = ottieni_profilo_societa(ISIN_ENEL, sessione=sessione)

    assert isinstance(profilo, ProfiloSocieta)
    assert profilo.isin == ISIN_ENEL
    assert profilo.descrizione is not None


ISIN_ETC_ORO = "IE00B579F325"  # Invesco Physical Gold ETC: denominazione USD, negoziazione EUR


@pytest.mark.integration
class TestSchedaValutaDenominazione:
    """La valuta di denominazione di un ETC non diventa la valuta di negoziazione."""

    @pytest.mark.parametrize("lingua", ["it", "en"])
    def test_etc_oro_negoziato_in_eur(self, sessione: Sessione, lingua: str) -> None:
        scheda = ottieni_scheda(ISIN_ETC_ORO, lingua=lingua, sessione=sessione)

        assert scheda.valuta == "EUR"
        assert scheda.valuta_denominazione == "USD"
