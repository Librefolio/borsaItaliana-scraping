"""Offline tests for ottieni_profilo_societa() on the saved Enel profile pages.

The fixtures are the real ``profilo-societa-dettaglio`` pages of Enel (IT0003128367)
in Italian and in English. The two pages carry the same data with translated labels,
so the parsed profile must have the same numbers, dates and shape in both languages.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from borsa_italiana_scraping import (
    Azionista,
    ContattiSocieta,
    DatoSocietario,
    Dirigente,
    IndirizzoSocieta,
    ProfiloSocieta,
    StrumentoNonTrovato,
    ottieni_profilo_societa,
)

_FIXTURES = Path(__file__).parent / "fixtures"
_ISIN = "IT0003128367"
_URL_SCHEDA = "https://www.borsaitaliana.it/borsa/azioni/scheda/IT0003128367-MTAA.html"


def _soup(nome: str) -> BeautifulSoup:
    return BeautifulSoup((_FIXTURES / nome).read_text(encoding="utf-8"), "lxml")


class FakeSessione:
    """Serves the profile fixture of the requested language and records every request."""

    def __init__(self) -> None:
        self.richieste_scheda: list[dict] = []
        self.richieste_profilo: list[dict] = []

    def get_html_con_url(self, url: str, params: dict | None = None) -> tuple[BeautifulSoup, str]:
        self.richieste_scheda.append(dict(params or {}))
        lingua = params["lang"]
        return _soup(f"scheda_{_ISIN}_{lingua}.html"), f"{_URL_SCHEDA}?lang={lingua}"

    def get_html(self, url: str, params: dict | None = None) -> BeautifulSoup:
        self.richieste_profilo.append(dict(params or {}))
        return _soup(f"profilo_societa_{_ISIN}_{params['lang']}.html")

    def chiudi(self) -> None:
        pass


def _profilo(lingua: str) -> ProfiloSocieta:
    return ottieni_profilo_societa(_ISIN, lingua=lingua, sessione=FakeSessione())


# Same figures on both pages; only the labels change with the language.
_ANNI = [2025, 2024, 2023, 2022, 2021]
_FATTURATO = {
    2021: Decimal("81900"),
    2022: Decimal("135653"),
    2023: Decimal("92882"),
    2024: Decimal("73914"),
    2025: Decimal("78057"),
}
_UTILE_NETTO = {
    2021: Decimal("3857"),
    2022: Decimal("2920"),
    2023: Decimal("4267"),
    2024: Decimal("8229"),
    2025: Decimal("5617"),
}
_ATTIVITA_DISMESSE = {
    2021: Decimal("0"),
    2022: Decimal("-2234"),
    2023: Decimal("-371"),
    2024: None,
    2025: None,
}
_CHIUSURA_ESERCIZIO = {anno: date(anno, 12, 31) for anno in _ANNI}
_PERCENTUALI_AZIONISTI = [Decimal("75.11"), Decimal("23.58"), Decimal("1.31")]
_NOMINATIVI_DIRIGENTI = [
    "Flavio Cattaneo",
    "Stefano De Angelis",
    "Omar Al Bayaty",
    "Elisabetta Colacchia",
    "Michela Mossini",
    "Michela Mossini",
    "Francesco Puntillo",
]

_PER_LINGUA = {
    "it": {
        "descrizione": "Enel S.p.A. è il primo produttore e distributore italiano di elettricità.",
        "primo_dirigente": Dirigente(ruolo="Amministratore Delegato", nominativo="Flavio Cattaneo"),
        "voci": ("Fatturato", "Utile netto", "Risultato netto delle attività dismesse", "Chiusura esercizio fiscale"),
        "unita": ("Valuta e unità di misura", "EUR - milioni"),
        "primo_azionista": Azionista(nominativo="Investitori istituzionali e privati", percentuale=Decimal("75.11")),
        "ultimo_azionista": "Azioni proprie",
    },
    "en": {
        "descrizione": "Enel S.p.A. is Italian No. 1 producer and distributor of electricity.",
        "primo_dirigente": Dirigente(ruolo="Chief Executive Officer", nominativo="Flavio Cattaneo"),
        "voci": ("Net sales", "Net income", "Net profit from discontinued activities", "Fiscal year end"),
        "unita": ("Currency & Unit", "EUR - millions"),
        "primo_azionista": Azionista(nominativo="Institutional and private investors", percentuale=Decimal("75.11")),
        "ultimo_azionista": "Treasury shares",
    },
}


@pytest.mark.parametrize("lingua", ["it", "en"])
class TestProfiloSocietaOffline:
    def test_identificativi(self, lingua: str) -> None:
        profilo = _profilo(lingua)

        assert isinstance(profilo, ProfiloSocieta)
        assert profilo.isin == _ISIN
        assert profilo.mic == "MTAA"
        assert profilo.url_pagina == (
            f"https://www.borsaitaliana.it/borsa/azioni/profilo-societa-dettaglio.html?isin={_ISIN}&mic=MTAA&lang={lingua}"
        )

    def test_descrizione(self, lingua: str) -> None:
        descrizione = _profilo(lingua).descrizione

        assert descrizione
        assert descrizione.startswith(_PER_LINGUA[lingua]["descrizione"])
        assert "1,881,651" in descrizione or "1.881.651" in descrizione
        # The "Company profile" heading and the source line are not part of the text.
        assert "Cofisem" not in descrizione

    def test_dirigenti(self, lingua: str) -> None:
        dirigenti = _profilo(lingua).dirigenti

        assert len(dirigenti) == 7
        assert all(isinstance(d, Dirigente) and d.ruolo and d.nominativo for d in dirigenti)
        assert dirigenti[0] == _PER_LINGUA[lingua]["primo_dirigente"]
        assert [d.nominativo for d in dirigenti] == _NOMINATIVI_DIRIGENTI

    def test_dati_principali(self, lingua: str) -> None:
        profilo = _profilo(lingua)
        voce_fatturato, voce_utile, voce_dismesse, voce_chiusura = _PER_LINGUA[lingua]["voci"]
        voce_unita, valore_unita = _PER_LINGUA[lingua]["unita"]
        dati = {d.voce: d for d in profilo.dati_principali}

        assert profilo.anni_disponibili == _ANNI
        assert len(profilo.dati_principali) == 12
        assert all(isinstance(d, DatoSocietario) for d in profilo.dati_principali)
        assert profilo.dati_principali[0].voce == voce_fatturato
        assert dati[voce_fatturato].valori == _FATTURATO
        assert dati[voce_utile].valori == _UTILE_NETTO
        assert dati[voce_dismesse].valori == _ATTIVITA_DISMESSE  # empty cells become None, not 0
        assert dati[voce_chiusura].valori == _CHIUSURA_ESERCIZIO
        assert dati[voce_unita].valori == dict.fromkeys(_ANNI, valore_unita)

    def test_azionisti(self, lingua: str) -> None:
        azionisti = _profilo(lingua).azionisti

        # The residual free-float row ("Institutional and private investors") is the first one.
        assert len(azionisti) == 3
        assert all(isinstance(a, Azionista) for a in azionisti)
        assert azionisti[0] == _PER_LINGUA[lingua]["primo_azionista"]
        assert azionisti[-1].nominativo == _PER_LINGUA[lingua]["ultimo_azionista"]
        assert [a.percentuale for a in azionisti] == _PERCENTUALI_AZIONISTI
        assert sum(a.percentuale for a in azionisti) == Decimal("100")

    def test_indirizzo(self, lingua: str) -> None:
        indirizzo = _profilo(lingua).indirizzo

        assert isinstance(indirizzo, IndirizzoSocieta)
        assert indirizzo.ragione_sociale == "Enel S.p.A."
        assert indirizzo.via == "Viale Regina Margherita 137"
        assert indirizzo.cap == "00198"
        assert indirizzo.comune == "Roma"
        assert indirizzo.paese == "Italy"  # not the "Source:" or "Phone number:" line that follows

    def test_contatti(self, lingua: str) -> None:
        contatti = _profilo(lingua).contatti

        assert contatti == ContattiSocieta(
            telefono="+39 (0)6 8305 7975",
            email="investor.relations@enel.com",
            sito_web="https://www.enel.com/investors/overview",
        )

    def test_fonte_e_data_aggiornamento(self, lingua: str) -> None:
        profilo = _profilo(lingua)

        assert profilo.fonte == "Cofisem"
        assert profilo.ultimo_aggiornamento == date(2026, 10, 23)


def _valori_non_testuali(profilo: ProfiloSocieta) -> list[dict]:
    """Per-year values of the numeric and date rows (text rows like the currency are translated)."""
    return [d.valori for d in profilo.dati_principali if not any(isinstance(v, str) for v in d.valori.values())]


def test_stessi_dati_in_entrambe_le_lingue() -> None:
    """Numbers, names, dates and contacts do not depend on the page language."""
    it, en = _profilo("it"), _profilo("en")

    assert it.anni_disponibili == en.anni_disponibili
    assert [d.nominativo for d in it.dirigenti] == [d.nominativo for d in en.dirigenti]
    assert _valori_non_testuali(it) == _valori_non_testuali(en)
    assert [a.percentuale for a in it.azionisti] == [a.percentuale for a in en.azionisti]
    assert it.indirizzo == en.indirizzo
    assert it.contatti == en.contatti
    assert (it.fonte, it.ultimo_aggiornamento) == (en.fonte, en.ultimo_aggiornamento)


def test_mic_ricavato_dalla_scheda_e_lingua_inoltrata() -> None:
    sessione = FakeSessione()

    profilo = ottieni_profilo_societa(_ISIN.lower(), lingua="IT", sessione=sessione)

    assert profilo.mic == "MTAA"
    assert sessione.richieste_scheda == [{"code": _ISIN, "lang": "it"}]
    assert sessione.richieste_profilo == [{"isin": _ISIN, "mic": "MTAA", "lang": "it"}]


def test_mic_esplicito_salta_la_scheda() -> None:
    sessione = FakeSessione()

    profilo = ottieni_profilo_societa(_ISIN, mic="mtaa", lingua="en", sessione=sessione)

    assert profilo.mic == "MTAA"
    assert sessione.richieste_scheda == []
    assert sessione.richieste_profilo == [{"isin": _ISIN, "mic": "MTAA", "lang": "en"}]


def test_isin_vuoto() -> None:
    with pytest.raises(ValueError):
        ottieni_profilo_societa("  ", sessione=FakeSessione())


@pytest.mark.parametrize("html", ["<html><body><h1>Page not found</h1></body></html>", "<html><body></body></html>"])
def test_pagina_senza_profilo(html: str) -> None:
    class SessioneVuota(FakeSessione):
        def get_html(self, url: str, params: dict | None = None) -> BeautifulSoup:
            return BeautifulSoup(html, "lxml")

    with pytest.raises(StrumentoNonTrovato):
        ottieni_profilo_societa(_ISIN, mic="MTAA", sessione=SessioneVuota())
