"""borsa-italiana-scraping — Libreria Python per dati finanziari da Borsa Italiana.

Esporta tutte le funzioni e i tipi dell'API pubblica.
"""

from .eccezioni import (
    BorsaItalianaErrore,
    DatiNonDisponibili,
    ErroreConnessione,
    RateLimitRaggiunto,
    RicercaNonDisponibile,
    StrumentoNonRisolto,
    StrumentoNonTrovato,
)
from .fondi import (
    DatiFondo,
    estrai_codice_da_url,
    ottieni_dati_fondo,
    ottieni_dati_fondo_da_url,
)
from .lista import (
    lista_bot,
    lista_btp,
    lista_cct,
    lista_ctz,
    lista_domestic_mot,
    lista_euro_mot,
    lista_green_and_social,
)
from .ricerca import cerca
from .scheda import ottieni_profilo_societa, ottieni_scheda
from .sessione import Sessione
from .storico import ottieni_storico
from .tempo_reale import ottieni_intraday, ottieni_prezzo_corrente
from .tipi import (
    Azionista,
    ContattiSocieta,
    DatoSocietario,
    Dirigente,
    IndirizzoSocieta,
    IntradayRisultato,
    PrezzoCorrente,
    ProfiloSocieta,
    PuntoIntraday,
    PuntoStorico,
    RisultatoRicerca,
    SchedaStrumento,
    StoricoRisultato,
    StrumentoGreenSocial,
    StrumentoLista,
)

__version__ = "0.3.5"

__all__ = [
    "Azionista",
    "BorsaItalianaErrore",
    "ContattiSocieta",
    "DatiFondo",
    "DatiNonDisponibili",
    "DatoSocietario",
    "Dirigente",
    "ErroreConnessione",
    "IndirizzoSocieta",
    "IntradayRisultato",
    "PrezzoCorrente",
    "ProfiloSocieta",
    "PuntoIntraday",
    "PuntoStorico",
    "RateLimitRaggiunto",
    "RicercaNonDisponibile",
    "RisultatoRicerca",
    "SchedaStrumento",
    "Sessione",
    "StoricoRisultato",
    "StrumentoGreenSocial",
    "StrumentoLista",
    "StrumentoNonRisolto",
    "StrumentoNonTrovato",
    "cerca",
    "estrai_codice_da_url",
    "lista_bot",
    "lista_btp",
    "lista_cct",
    "lista_ctz",
    "lista_domestic_mot",
    "lista_euro_mot",
    "lista_green_and_social",
    "ottieni_dati_fondo",
    "ottieni_dati_fondo_da_url",
    "ottieni_intraday",
    "ottieni_prezzo_corrente",
    "ottieni_profilo_societa",
    "ottieni_scheda",
    "ottieni_storico",
]
