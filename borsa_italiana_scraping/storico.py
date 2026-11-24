"""Funzioni per dati storici OHLCV (JSON API grafici.borsaitaliana.it)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from .eccezioni import DatiNonDisponibili, ErroreConnessione, StrumentoNonTrovato
from .sessione import Sessione
from .tipi import PuntoStorico, StoricoRisultato

# Periodi ammessi
_PERIODI_VALIDI = {"1M", "3M", "6M", "1Y", "3Y", "5Y", "MAX"}

# URL base API storico
_URL_STORICO = "https://grafici.borsaitaliana.it/api/instruments/{isin},{exchange},ISIN/history/period"


def _parsa_data(dt_str: str) -> date:
    """Converte una stringa YYYYMMDD in date."""
    return datetime.strptime(dt_str, "%Y%m%d").date()


def _dec(valore: float | None) -> Decimal:
    """Converte un numero JSON in Decimal."""
    if valore is None:
        return Decimal(0)
    return Decimal(str(valore))


def _parsa_punto(raw: dict) -> PuntoStorico:
    """Trasforma un elemento historyDt in PuntoStorico."""
    # numero_contratti e controvalore possono mancare nell'ultimo punto
    numero_contratti = raw.get("volNbTrade")
    controvalore = raw.get("volCap")

    return PuntoStorico(
        data=_parsa_data(raw["dt"]),
        apertura=_dec(raw.get("openPx")),
        chiusura=_dec(raw.get("closePx")),
        massimo=_dec(raw.get("highPx")),
        minimo=_dec(raw.get("lowPx")),
        ultimo=_dec(raw.get("lastPx")),
        volume=int(raw.get("qty", 0)),
        numero_contratti=int(numero_contratti) if numero_contratti is not None else None,
        controvalore=_dec(controvalore) if controvalore is not None else None,
    )


def _scarica_storico(
    isin: str,
    periodo: str,
    exchange: str,
    aggiustato: bool,
    includi_ultimo: bool,
    sessione: Sessione,
) -> StoricoRisultato:
    """Singola chiamata alla grafici API per un exchange specifico.

    Raises:
        StrumentoNonTrovato: l'exchange non conosce lo strumento
            (risposta senza ``transco``).
        DatiNonDisponibili: strumento riconosciuto ma finestra senza dati.
    """
    url = _URL_STORICO.format(isin=isin, exchange=exchange)
    parametri: dict[str, str] = {"period": periodo}
    if aggiustato:
        parametri["adjustment"] = "true"
    if includi_ultimo:
        parametri["add-last-price"] = "true"

    dati = sessione.get_json(url, params=parametri)

    # Verifica presenza dati
    transco = dati.get("transco", {})
    history = dati.get("history") or {}
    punti_raw = history.get("historyDt")

    if not transco or not transco.get("code"):
        raise StrumentoNonTrovato(f"ISIN '{isin}' non riconosciuto dall'API di Borsa Italiana (exchange {exchange})")

    if punti_raw is None or len(punti_raw) == 0:
        raise DatiNonDisponibili(f"Nessun dato storico disponibile per '{isin}' nel periodo '{periodo}'")

    codice_borsa = transco.get("exchCode", exchange)
    punti = [_parsa_punto(p) for p in punti_raw]

    return StoricoRisultato(
        isin=transco.get("code", isin),
        codice_borsa=codice_borsa,
        punti=punti,
        valuta=history.get("currency") or "EUR",
    )


def _mic_da_ricerca(isin: str, sessione: Sessione) -> list[str]:
    """Scopre i MIC di uno strumento via site-search (fallback, solo su miss).

    Restituisce i MIC distinti delle quote il cui simbolo è esattamente
    l'ISIN cercato (la search per ISIN può includere listing duplicati su
    altre borse, es. lo stesso ETF su ETFP e XAMS).
    """
    from .ricerca import cerca

    try:
        risultati = cerca(isin, sessione=sessione)
    except Exception:
        return []

    mics: list[str] = []
    for r in risultati:
        if r.isin.upper() != isin:
            continue
        mic = (r.mic or "").strip().upper()
        if mic and mic != "XMIL" and mic not in mics:
            mics.append(mic)
    return mics


def ottieni_storico(
    isin: str,
    periodo: str = "1Y",
    aggiustato: bool = True,
    includi_ultimo: bool = True,
    sessione: Sessione | None = None,
    exchange: str | None = None,
) -> StoricoRisultato:
    """Scarica i dati storici OHLCV per un titolo identificato da ISIN.

    Args:
        isin: codice ISIN dello strumento (es. ``"IT0003128367"``).
        periodo: finestra temporale — ``1M``, ``3M``, ``6M``, ``1Y``, ``3Y``, ``5Y``, ``MAX``.
        aggiustato: se ``True`` applica l'aggiustamento corporate-action.
        includi_ultimo: se ``True`` aggiunge l'ultimo prezzo disponibile.
        sessione: sessione HTTP riutilizzabile (ne viene creata una se ``None``).
        exchange: codice exchange della grafici API (es. ``"ETLX"`` per EuroTLX).
            Se ``None`` si prova ``XMIL`` e, su strumento non riconosciuto, si
            scoprono i MIC via site-search e si riprova (auto-discovery).

    Returns:
        ``StoricoRisultato`` con la lista di ``PuntoStorico``.

    Raises:
        ValueError: se il periodo non è valido.
        StrumentoNonTrovato: se l'ISIN non è riconosciuto su nessun exchange.
        DatiNonDisponibili: strumento riconosciuto ma finestra senza dati
            (es. titolo illiquido nel periodo richiesto).
    """
    periodo = periodo.upper()
    if periodo not in _PERIODI_VALIDI:
        raise ValueError(f"Periodo '{periodo}' non valido. Usa uno tra: {', '.join(sorted(_PERIODI_VALIDI))}")

    isin = isin.strip().upper()

    sessione_locale = sessione is None
    if sessione_locale:
        sessione = Sessione()

    try:
        # Exchange esplicito: nessuna auto-discovery, l'errore risale com'è.
        if exchange:
            return _scarica_storico(isin, periodo, exchange.upper(), aggiustato, includi_ultimo, sessione)

        try:
            return _scarica_storico(isin, periodo, "XMIL", aggiustato, includi_ultimo, sessione)
        except StrumentoNonTrovato:
            pass  # auto-discovery sotto

        # Auto-discovery: la grafici API conosce alcuni mercati (es. EuroTLX)
        # solo sotto il proprio exchCode. La site-search rivela i MIC dell'ISIN.
        for mic in _mic_da_ricerca(isin, sessione):
            try:
                return _scarica_storico(isin, periodo, mic, aggiustato, includi_ultimo, sessione)
            except (ErroreConnessione, StrumentoNonTrovato):
                continue

        # Nessun exchange alternativo ha dati: distinguiamo "strumento noto ma
        # finestra vuota" (es. ExtraMOT illiquido su 1M) da "sconosciuto" con
        # una sonda MAX su XMIL (transco presente ⇒ strumento riconosciuto).
        try:
            _scarica_storico(isin, "MAX", "XMIL", aggiustato, False, sessione)
        except (StrumentoNonTrovato, ErroreConnessione):
            raise StrumentoNonTrovato(f"ISIN '{isin}' non riconosciuto dall'API di Borsa Italiana") from None
        except DatiNonDisponibili:
            pass  # noto a XMIL, senza serie MAX: comunque riconosciuto
        raise DatiNonDisponibili(f"Nessun dato storico disponibile per '{isin}' nel periodo '{periodo}'")

    finally:
        if sessione_locale:
            sessione.chiudi()
