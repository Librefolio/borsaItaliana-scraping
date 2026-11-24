"""Gestione sessione HTTP verso Borsa Italiana.

Mantiene i cookie Imperva WAF, estrae il JWT token dalla pagina
interactive-chart ed esegue warmup automatico.
Rispetta i rate-limit con pausa tra richieste.
"""

from __future__ import annotations

import re
import time
from typing import Self

import httpx
from bs4 import BeautifulSoup

from .eccezioni import ErroreConnessione, RateLimitRaggiunto

# User-Agent realistico (Chrome su macOS)
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

# URL per estrarre il JWT token (il token è uguale per qualsiasi ISIN)
_URL_CHART_TOKEN = "https://grafici.borsaitaliana.it/interactive-chart/IT0003128367-XMIL?lang=it"

# Regex per estrarre il token dalla pagina
_RE_TOKEN = re.compile(r'token="([^"]+)"')


class Sessione:
    """Sessione HTTP riutilizzabile verso Borsa Italiana.

    - Estrae il JWT token dalla pagina interactive-chart (necessario per le API)
    - Mantiene i cookie Imperva tra le richieste
    - Rispetta i rate-limit con pausa minima tra richieste
    """

    def __init__(
        self,
        timeout: float = 30.0,
        max_tentativi: int = 3,
        pausa_minima: float = 0.5,
    ):
        self._timeout = timeout
        self._max_tentativi = max_tentativi
        self._pausa_minima = pausa_minima
        self._warmup_eseguito = False
        self._token: str | None = None
        self._ultimo_accesso: float = 0.0

        self._client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={
                "User-Agent": _USER_AGENT,
                "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
            },
        )

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        self.chiudi()

    # ------------------------------------------------------------------
    # Warmup: estrae JWT token + cookie Imperva
    # ------------------------------------------------------------------

    def warmup(self) -> None:
        """Visita la pagina interactive-chart per ottenere il JWT token
        e i cookie Imperva WAF.

        Il token è anonimo (sub=-1) con scadenza ~100 anni, uguale
        per qualsiasi ISIN. Viene estratto una sola volta e riutilizzato.
        """
        if self._warmup_eseguito:
            return
        try:
            self._rispetta_pausa()
            risposta = self._client.get(_URL_CHART_TOKEN)
            self._ultimo_accesso = time.monotonic()

            # Estrai il token JWT dalla pagina
            match = _RE_TOKEN.search(risposta.text)
            if match:
                self._token = match.group(1)
            else:
                raise ErroreConnessione(
                    "Impossibile estrarre il JWT token dalla pagina interactive-chart di Borsa Italiana"
                )

            self._warmup_eseguito = True
        except ErroreConnessione:
            raise
        except httpx.HTTPError as err:
            raise ErroreConnessione(f"Errore durante il warmup: {err}") from err

    def _assicura_warmup(self) -> None:
        """Se il warmup non è stato ancora eseguito, lo fa ora."""
        if not self._warmup_eseguito:
            self.warmup()

    # ------------------------------------------------------------------
    # Pausa rate-limit
    # ------------------------------------------------------------------

    def _rispetta_pausa(self) -> None:
        """Aspetta la pausa minima dal precedente accesso."""
        if self._ultimo_accesso:
            trascorso = time.monotonic() - self._ultimo_accesso
            if trascorso < self._pausa_minima:
                time.sleep(self._pausa_minima - trascorso)

    # ------------------------------------------------------------------
    # Richieste HTTP
    # ------------------------------------------------------------------

    def _esegui_get(
        self,
        url: str,
        params: dict | None = None,
        headers: dict | None = None,
    ) -> httpx.Response:
        """GET con retry e gestione errori.

        Aggiunge automaticamente il JWT token per le API ``grafici.*``.
        """
        self._assicura_warmup()

        # Aggiungi Bearer token per le API grafici
        req_headers = dict(headers) if headers else {}
        if "grafici.borsaitaliana.it/api/" in url and self._token:
            req_headers.setdefault("Authorization", f"Bearer {self._token}")

        ultimo_errore: Exception | None = None
        for tentativo in range(1, self._max_tentativi + 1):
            try:
                self._rispetta_pausa()
                risposta = self._client.get(url, params=params, headers=req_headers)
                self._ultimo_accesso = time.monotonic()

                if risposta.status_code == 429:
                    attesa = 2**tentativo
                    time.sleep(attesa)
                    ultimo_errore = RateLimitRaggiunto(f"HTTP 429 — tentativo {tentativo}/{self._max_tentativi}")
                    continue

                if risposta.status_code == 403:
                    raise RateLimitRaggiunto(f"HTTP 403 — accesso bloccato dal WAF (url={url})")

                risposta.raise_for_status()
                return risposta

            except RateLimitRaggiunto:
                raise
            except httpx.TimeoutException as err:
                ultimo_errore = ErroreConnessione(f"Timeout alla richiesta {url}: {err}")
            except httpx.HTTPStatusError as err:
                ultimo_errore = ErroreConnessione(f"HTTP {err.response.status_code} per {url}: {err}")
            except httpx.HTTPError as err:
                ultimo_errore = ErroreConnessione(f"Errore di rete per {url}: {err}")

        # Tutti i tentativi esauriti
        raise ultimo_errore  # type: ignore[misc]

    def get_json(self, url: str, params: dict | None = None) -> dict:
        """Esegue una GET e restituisce il JSON decodificato."""
        risposta = self._esegui_get(url, params=params)
        try:
            return risposta.json()
        except Exception as err:
            raise ErroreConnessione(f"Risposta non JSON da {url}: {risposta.text[:200]}") from err

    def get_html(self, url: str, params: dict | None = None) -> BeautifulSoup:
        """Esegue una GET e restituisce il DOM parsato con lxml."""
        risposta = self._esegui_get(url, params=params)
        return BeautifulSoup(risposta.text, "lxml")

    def get_html_con_url(self, url: str, params: dict | None = None) -> tuple[BeautifulSoup, str]:
        """Esegue una GET e restituisce (DOM, URL finale dopo redirect)."""
        risposta = self._esegui_get(url, params=params)
        return BeautifulSoup(risposta.text, "lxml"), str(risposta.url)

    def get_json_xhr(
        self,
        url: str,
        params: dict | None = None,
    ) -> dict:
        """GET con header XHR (necessari per l'endpoint di ricerca)."""
        headers = {
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json",
        }
        risposta = self._esegui_get(url, params=params, headers=headers)
        try:
            return risposta.json()
        except Exception as err:
            raise ErroreConnessione(f"Risposta non JSON (XHR) da {url}: {risposta.text[:200]}") from err

    # ------------------------------------------------------------------
    # Chiusura
    # ------------------------------------------------------------------

    def chiudi(self) -> None:
        """Chiude la sessione HTTP sottostante."""
        self._client.close()
