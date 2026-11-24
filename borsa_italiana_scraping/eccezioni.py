"""Eccezioni personalizzate per borsa-italiana-scraping."""


class BorsaItalianaErrore(Exception):
    """Errore base della libreria."""


class StrumentoNonTrovato(BorsaItalianaErrore):
    """Lo strumento con l'ISIN specificato non è stato trovato."""


class StrumentoNonRisolto(StrumentoNonTrovato):
    """La pagina universale non ha rediretto a una scheda strumento.

    Sollevata quando ``search/scheda.html?code=…`` non redirige alla pagina di
    mercato: lo strumento può non esistere, oppure servono ``mic``/``platform``
    corretti, oppure il mercato non è gestito. Sottoclasse di
    ``StrumentoNonTrovato`` per compatibilità con i ``except`` esistenti.
    """


class DatiNonDisponibili(BorsaItalianaErrore):
    """I dati richiesti non sono disponibili (periodo non supportato, mercato chiuso, ecc.)."""


class ErroreConnessione(BorsaItalianaErrore):
    """Errore di rete o timeout."""


class RateLimitRaggiunto(BorsaItalianaErrore):
    """Troppe richieste — il WAF ha bloccato la connessione."""


class RicercaNonDisponibile(BorsaItalianaErrore):
    """La ricerca JSON non è disponibile (Cloudflare block). Suggerisce di usare lista_btp() ecc."""
