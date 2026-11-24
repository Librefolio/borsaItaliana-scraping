"""Eccezioni personalizzate per borsa-italiana-scraping."""


class BorsaItalianaErrore(Exception):
    """Errore base della libreria."""

    pass


class StrumentoNonTrovato(BorsaItalianaErrore):
    """Lo strumento con l'ISIN specificato non è stato trovato."""

    pass


class StrumentoNonRisolto(StrumentoNonTrovato):
    """La pagina universale non ha rediretto a una scheda strumento.

    Sollevata quando ``search/scheda.html?code=…`` non redirige alla pagina di
    mercato: lo strumento può non esistere, oppure servono ``mic``/``platform``
    corretti, oppure il mercato non è gestito. Sottoclasse di
    ``StrumentoNonTrovato`` per compatibilità con i ``except`` esistenti.
    """

    pass


class DatiNonDisponibili(BorsaItalianaErrore):
    """I dati richiesti non sono disponibili (periodo non supportato, mercato chiuso, ecc.)."""

    pass


class ErroreConnessione(BorsaItalianaErrore):
    """Errore di rete o timeout."""

    pass


class RateLimitRaggiunto(BorsaItalianaErrore):
    """Troppe richieste — il WAF ha bloccato la connessione."""

    pass


class RicercaNonDisponibile(BorsaItalianaErrore):
    """La ricerca JSON non è disponibile (Cloudflare block). Suggerisce di usare lista_btp() ecc."""

    pass
