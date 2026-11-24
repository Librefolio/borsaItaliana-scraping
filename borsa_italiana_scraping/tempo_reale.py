"""Funzioni per prezzo corrente e dati intraday."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from .eccezioni import DatiNonDisponibili
from .sessione import Sessione
from .tipi import IntradayRisultato, PrezzoCorrente, PuntoIntraday

# Risoluzioni ammesse
_RISOLUZIONI_VALIDE = {"1MN", "5MN", "15MN", "30MN", "1H"}

# URL base API intraday
_URL_INTRADAY = "https://grafici.borsaitaliana.it/api/instruments/{isin},XMIL,ISIN/intraday"

# URL base API storico (per prezzo corrente via ultimo punto)
_URL_STORICO = "https://grafici.borsaitaliana.it/api/instruments/{isin},XMIL,ISIN/history/period"


def _dec(valore: float | None) -> Decimal:
    """Converte un numero JSON in Decimal."""
    if valore is None:
        return Decimal(0)
    return Decimal(str(valore))


def _parsa_orario(time_str: str) -> datetime:
    """Converte ``YYYYMMDD-HH:MM:SS`` in datetime."""
    return datetime.strptime(time_str, "%Y%m%d-%H:%M:%S")


def _parsa_punto_intraday(raw: dict) -> PuntoIntraday:
    """Trasforma un elemento intradayPoint in PuntoIntraday."""
    chiusura_prec = raw.get("previousClosingPx")
    return PuntoIntraday(
        orario=_parsa_orario(raw["time"]),
        apertura=_dec(raw.get("beginPx")),
        chiusura=_dec(raw.get("endPx")),
        massimo=_dec(raw.get("highPx")),
        minimo=_dec(raw.get("lowPx")),
        volume=int(raw.get("vol", 0)),
        numero_contratti=int(raw.get("nbTrade", 0)),
        controvalore=_dec(raw.get("amt")),
        chiusura_precedente=_dec(chiusura_prec) if chiusura_prec is not None else None,
    )


def ottieni_intraday(
    isin: str,
    risoluzione: str = "1MN",
    sessione: Sessione | None = None,
) -> IntradayRisultato:
    """Scarica i dati intraday della giornata corrente.

    Args:
        isin: codice ISIN dello strumento.
        risoluzione: granularità — ``1MN``, ``5MN``, ``15MN``, ``30MN``, ``1H``.
        sessione: sessione HTTP riutilizzabile.

    Returns:
        ``IntradayRisultato`` con la lista di ``PuntoIntraday``.
    """
    risoluzione = risoluzione.upper()
    if risoluzione not in _RISOLUZIONI_VALIDE:
        raise ValueError(f"Risoluzione '{risoluzione}' non valida. Usa: {', '.join(sorted(_RISOLUZIONI_VALIDE))}")

    isin = isin.strip().upper()

    sessione_locale = sessione is None
    if sessione_locale:
        sessione = Sessione()

    try:
        url = _URL_INTRADAY.format(isin=isin)
        dati = sessione.get_json(url, params={"resolution": risoluzione})

        punti_raw = dati.get("intradayPoint", [])
        if not punti_raw:
            raise DatiNonDisponibili(f"Nessun dato intraday per '{isin}' (mercato chiuso?)")

        punti = [_parsa_punto_intraday(p) for p in punti_raw]
        return IntradayRisultato(isin=isin, punti=punti)

    finally:
        if sessione_locale:
            sessione.chiudi()


def ottieni_prezzo_corrente(
    isin: str,
    sessione: Sessione | None = None,
    exchange: str | None = None,
    mic: str | None = None,
    platform: str | None = None,
) -> PrezzoCorrente:
    """Ottiene il prezzo corrente (o più recente) di uno strumento.

    Strategia: usa l'endpoint storico con periodo ``1M`` e prende
    l'ultimo punto. In caso di fallimento, fa scraping della pagina scheda.

    Args:
        isin: codice ISIN dello strumento.
        sessione: sessione HTTP riutilizzabile.
        exchange: codice exchange della grafici API (es. ``"ETLX"``);
            ``None`` → XMIL con auto-discovery (vedi :func:`ottieni_storico`).
        mic: codice MIC per il fallback scraping della pagina scheda.
        platform: piattaforma per il fallback scraping (es. ``"TLX"``).

    Returns:
        ``PrezzoCorrente`` con prezzo, data, valuta e fonte.
    """
    isin = isin.strip().upper()

    sessione_locale = sessione is None
    if sessione_locale:
        sessione = Sessione()

    try:
        return _prezzo_da_api(isin, sessione, exchange=exchange)
    except Exception:
        # Fallback: scraping pagina scheda
        return _prezzo_da_scraping(isin, sessione, mic=mic, platform=platform)
    finally:
        if sessione_locale:
            sessione.chiudi()


def _prezzo_da_api(isin: str, sessione: Sessione, exchange: str | None = None) -> PrezzoCorrente:
    """Estrae il prezzo dall'ultimo punto dello storico 1M."""
    from .storico import ottieni_storico

    risultato = ottieni_storico(isin, periodo="1M", sessione=sessione, exchange=exchange)
    if not risultato.punti:
        raise DatiNonDisponibili(f"Nessun punto storico per '{isin}'")

    ultimo = risultato.punti[-1]
    # Variazione % rispetto alla chiusura del giorno prima
    variazione: Decimal | None = None
    if len(risultato.punti) >= 2:
        precedente = risultato.punti[-2].chiusura
        if precedente and precedente != 0:
            variazione = ((ultimo.chiusura - precedente) / precedente * 100).quantize(Decimal("0.01"))

    return PrezzoCorrente(
        isin=isin,
        prezzo=ultimo.ultimo,
        variazione_percentuale=variazione,
        data=ultimo.data,
        valuta=risultato.valuta or "EUR",
        fonte="api",
    )


def _prezzo_da_scraping(
    isin: str,
    sessione: Sessione,
    mic: str | None = None,
    platform: str | None = None,
) -> PrezzoCorrente:
    """Estrae il prezzo dalla pagina scheda (fallback)."""
    from .scheda import ottieni_scheda

    scheda = ottieni_scheda(isin, sessione=sessione, mic=mic, platform=platform)
    return PrezzoCorrente(
        isin=scheda.isin,
        prezzo=scheda.prezzo,
        variazione_percentuale=scheda.variazione_percentuale,
        data=date.today(),
        valuta=scheda.valuta,
        fonte="scraping",
    )
