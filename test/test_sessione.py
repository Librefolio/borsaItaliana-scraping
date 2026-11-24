"""Test di integrazione per sessione.py — verifica warmup e gestione cookie."""

import pytest

from borsa_italiana_scraping.sessione import Sessione


@pytest.mark.integration
class TestSessione:
    """Test della classe Sessione con richieste reali."""

    def test_warmup_imposta_cookie(self) -> None:
        """Il warmup deve ottenere il JWT token."""
        sessione = Sessione()
        try:
            sessione.warmup()
            assert sessione._warmup_eseguito is True
            assert sessione._token is not None
            assert len(sessione._token) > 50  # JWT ha >100 chars
        finally:
            sessione.chiudi()

    def test_context_manager(self) -> None:
        """La sessione funziona come context manager."""
        with Sessione() as sess:
            sess.warmup()
            assert sess._warmup_eseguito

    def test_get_json(self) -> None:
        """get_json deve restituire un dizionario valido."""
        with Sessione() as sess:
            url = "https://grafici.borsaitaliana.it/api/instruments/IT0003128367,XMIL,ISIN/history/period"
            dati = sess.get_json(url, params={"period": "1M"})
            assert isinstance(dati, dict)
            assert "transco" in dati

    def test_get_html(self) -> None:
        """get_html deve restituire un oggetto BeautifulSoup."""
        from bs4 import BeautifulSoup

        with Sessione() as sess:
            soup = sess.get_html(
                "https://www.borsaitaliana.it/borsa/obbligazioni/mot/btp/lista.html",
                params={"lang": "en"},
            )
            assert isinstance(soup, BeautifulSoup)
            # La pagina deve contenere una tabella
            assert soup.find("table") is not None
