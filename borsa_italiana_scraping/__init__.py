"""borsa-italiana-scraping — Libreria Python per dati finanziari da Borsa Italiana.

Esporta tutte le funzioni e i tipi dell'API pubblica.
"""

# Sessione HTTP
from .sessione import Sessione

# Eccezioni
from .eccezioni import (
    BorsaItalianaErrore,
    DatiNonDisponibili,
    ErroreConnessione,
    RateLimitRaggiunto,
    RicercaNonDisponibile,
    StrumentoNonRisolto,
    StrumentoNonTrovato,
)

# Tipi di dati
from .tipi import (
    IntradayRisultato,
    PrezzoCorrente,
    PuntoIntraday,
    PuntoStorico,
    RisultatoRicerca,
    SchedaStrumento,
    StoricoRisultato,
    StrumentoLista,
)

# Funzioni
from .storico import ottieni_storico
from .tempo_reale import ottieni_intraday, ottieni_prezzo_corrente
from .ricerca import cerca
from .scheda import ottieni_scheda
from .fondi import (
    DatiFondo,
    estrai_codice_da_url,
    ottieni_dati_fondo,
    ottieni_dati_fondo_da_url,
)
from .lista import lista_btp

__version__ = "0.3.2"

__all__ = [
    # Sessione
    "Sessione",
    # Eccezioni
    "BorsaItalianaErrore",
    "DatiNonDisponibili",
    "ErroreConnessione",
    "RateLimitRaggiunto",
    "RicercaNonDisponibile",
    "StrumentoNonRisolto",
    "StrumentoNonTrovato",
    # Tipi
    "IntradayRisultato",
    "PrezzoCorrente",
    "PuntoIntraday",
    "PuntoStorico",
    "RisultatoRicerca",
    "SchedaStrumento",
    "StoricoRisultato",
    "StrumentoLista",
    "DatiFondo",
    # Funzioni
    "ottieni_storico",
    "ottieni_intraday",
    "ottieni_prezzo_corrente",
    "cerca",
    "ottieni_scheda",
    "ottieni_dati_fondo",
    "ottieni_dati_fondo_da_url",
    "estrai_codice_da_url",
    "lista_btp",
]
