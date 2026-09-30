"""Tipi di dati (dataclass) per i risultati della libreria."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal


# ---------------------------------------------------------------------------
# Storico
# ---------------------------------------------------------------------------

@dataclass
class PuntoStorico:
    """Singolo punto OHLCV giornaliero."""
    data: date
    apertura: Decimal
    chiusura: Decimal
    massimo: Decimal
    minimo: Decimal
    ultimo: Decimal
    volume: int
    numero_contratti: int | None = None
    controvalore: Decimal | None = None


@dataclass
class StoricoRisultato:
    """Risultato della query storica per uno strumento."""
    isin: str
    codice_borsa: str  # es. "XMIL"
    punti: list[PuntoStorico] = field(default_factory=list)
    valuta: str = "EUR"  # da ``history.currency`` della grafici API (es. "USD")


# ---------------------------------------------------------------------------
# Intraday / prezzo corrente
# ---------------------------------------------------------------------------

@dataclass
class PuntoIntraday:
    """Singola candela intraday."""
    orario: datetime
    apertura: Decimal
    chiusura: Decimal
    massimo: Decimal
    minimo: Decimal
    volume: int
    numero_contratti: int
    controvalore: Decimal
    chiusura_precedente: Decimal | None = None


@dataclass
class IntradayRisultato:
    """Risultato della query intraday."""
    isin: str
    punti: list[PuntoIntraday] = field(default_factory=list)


@dataclass
class PrezzoCorrente:
    """Prezzo corrente (o più recente) di uno strumento."""
    isin: str
    prezzo: Decimal
    variazione_percentuale: Decimal | None
    data: date
    valuta: str
    fonte: str  # "api" o "scraping"


# ---------------------------------------------------------------------------
# Ricerca
# ---------------------------------------------------------------------------

@dataclass
class RisultatoRicerca:
    """Singolo risultato dalla ricerca strumenti."""
    isin: str
    mic: str
    nome: str
    tipo: str  # "Obbligazione", "Azione", "ETF", "ETC/ETN", ecc.
    mercato: str
    comparto: str | None = None
    sotto_comparto: str | None = None
    dettaglio_mercato: str | None = None   # es. "Euronext Milan", "ETF"
    sotto_tipo: str | None = None          # es. "MTA", "MOT", "ETF"
    link: str | None = None                # URL alla pagina scheda


# ---------------------------------------------------------------------------
# Scheda strumento
# ---------------------------------------------------------------------------

@dataclass
class SchedaStrumento:
    """Dati estratti dalla pagina scheda di uno strumento."""
    isin: str
    nome: str
    prezzo: Decimal
    variazione_percentuale: Decimal | None
    valuta: str
    tipo: str  # "azione", "obbligazione", "etf", "altro"
    mercato: str

    # --- Campi comuni ---
    descrizione: str | None = None            # meta description della pagina
    url_pagina: str | None = None             # URL canonico della scheda
    valuta_liquidazione: str | None = None     # Settlement currency (se diversa)
    valuta_denominazione: str | None = None    # Valuta di denominazione (ETF/ETC); non è la valuta di negoziazione
    minimo_anno: Decimal | None = None         # Year Low
    massimo_anno: Decimal | None = None        # Year High
    apertura: Decimal | None = None            # Opening price
    minimo_giorno: Decimal | None = None       # Day Low
    massimo_giorno: Decimal | None = None      # Day High

    # --- Campi specifici obbligazioni (None per azioni) ---
    rendimento_lordo: Decimal | None = None
    rendimento_netto: Decimal | None = None
    rateo_lordo: Decimal | None = None
    rateo_netto: Decimal | None = None
    duration_modificata: Decimal | None = None
    cedola_annua: Decimal | None = None
    cedola_periodale: Decimal | None = None
    scadenza: date | None = None
    emittente: str | None = None
    tipo_bond: str | None = None
    lotto_minimo: int | None = None
    descrizione_payout: str | None = None
    frequenza_cedola: str | None = None        # Quarterly, Semiannual, Annual...
    convenzione_giorni: str | None = None      # ACT/ACT (ICMA), 30/360, ...
    struttura_bond: str | None = None          # Fixed Rate, Structured Interest Rate...
    outstanding: Decimal | None = None         # Ammontare in circolazione
    tipologia: str | None = None               # Italian Government Bonds, Corporate, ...
    prezzo_riferimento: Decimal | None = None   # Reference price
    data_prezzo_riferimento: date | None = None # Reference price date
    data_primo_giorno: date | None = None       # First Day of Trading

    # --- Campi specifici azioni (None per obbligazioni) ---
    settore: str | None = None
    capitalizzazione: Decimal | None = None
    ticker: str | None = None
    performance_1m: Decimal | None = None
    performance_6m: Decimal | None = None
    performance_1y: Decimal | None = None
    indici: list[str] | None = None            # FTSE MIB, FTSE All-Share, ...


# ---------------------------------------------------------------------------
# Lista strumenti
# ---------------------------------------------------------------------------

@dataclass
class StrumentoLista:
    """Strumento da una lista HTML (es. lista BTP)."""
    isin: str
    nome: str
    ultimo_prezzo: Decimal | None
    cedola: Decimal | None
    scadenza: date | None
    mic: str
