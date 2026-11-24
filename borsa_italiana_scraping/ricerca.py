"""Ricerca strumenti su Borsa Italiana (endpoint JSON interno).

L'endpoint ``/borsa/searchengine/all/json/search.html`` restituisce
JSON puro senza protezione WAF — non servono header XHR né JWT.
"""

from __future__ import annotations

from .eccezioni import RicercaNonDisponibile
from .sessione import Sessione
from .tipi import RisultatoRicerca

# URL endpoint JSON (scoperto dal JS ``bb.search.js`` → ``bit.init.search``)
_URL_RICERCA = "https://www.borsaitaliana.it/borsa/searchengine/all/json/search.html"


def cerca(
    query: str,
    lingua: str = "it",
    solo_strumenti: bool = True,
    sessione: Sessione | None = None,
) -> list[RisultatoRicerca]:
    """Cerca strumenti finanziari su Borsa Italiana.

    Usa l'endpoint JSON interno del motore di ricerca del sito.

    Args:
        query: testo di ricerca (es. ``"BTP"``, ``"ENEL"``).
        lingua: ``"it"`` o ``"en"``.
        solo_strumenti: se ``True`` restituisce solo le quotes,
            ignorando news/pages/documents.
        sessione: sessione HTTP riutilizzabile.

    Returns:
        Lista di ``RisultatoRicerca``.

    Raises:
        RicercaNonDisponibile: se l'endpoint JSON non risponde.
    """
    lingua = lingua.lower()
    if lingua not in ("it", "en"):
        raise ValueError("La lingua deve essere 'it' o 'en'")

    sessione_locale = sessione is None
    if sessione_locale:
        sessione = Sessione()

    try:
        risultati = _cerca_una(query, lingua, sessione)

        # Ripiego per i fondi (e nomi lunghi): la site-search di BI fa match
        # per PREFISSO su ogni parola, quindi un nome-report esteso
        # ("...DIVERSIFICATO 40 P") non combacia col nome abbreviato di BI
        # ("...Divers. 40 P"). Si riprova accorciando/scartando le parole lunghe.
        if not risultati:
            for variante in _varianti_query(query):
                risultati = _cerca_una(variante, lingua, sessione)
                if risultati:
                    break

        # Soft-block WAF (rate-limit silenzioso per IP): l'endpoint risponde 200
        # ma con OGNI sezione vuota per QUALSIASI query — osservato in produzione
        # il 2026-09-05 dopo una sessione intensiva di test. Indistinguibile da un
        # onesto "nessun risultato" guardando solo la query corrente, quindi si
        # sonda con una query onnipresente: se anche quella è tutta vuota, è blocco.
        if not risultati and _sonda_soft_block(sessione, lingua):
            raise RicercaNonDisponibile(
                "La ricerca risponde con payload vuoti a qualsiasi query: "
                "probabile rate-limit del WAF verso questo IP (troppi test/ricerche "
                "ravvicinate). Riprova più tardi o da un'altra rete."
            )

        return risultati

    finally:
        if sessione_locale:
            sessione.chiudi()


def _sonda_soft_block(sessione: Sessione, lingua: str) -> bool:
    """True se l'endpoint svuota OGNI sezione anche per una query onnipresente.

    Un "nessun risultato" legittimo ha le quotes vuote ma news/pagine piene
    (es. ``XYZNONEXISTENT``); il soft-block WAF invece azzera tutte le sezioni
    insieme. Se la sonda stessa fallisce in rete, si risponde False: il chiamante
    mantiene il comportamento "nessun risultato".
    """
    try:
        dati = sessione.get_json(_URL_RICERCA, params={"lang": lingua, "q": "ENEL"})
    except Exception:  # noqa: BLE001 - probe failure means "not a soft-block", see docstring
        return False
    return all(not dati.get(k) for k in ("quotes", "news", "pages", "terms", "documents"))


def _cerca_una(query: str, lingua: str, sessione: Sessione) -> list[RisultatoRicerca]:
    """Esegue una singola query alla site-search e mappa le quotes.

    Nota: per azioni/obbligazioni ``symbol`` è l'ISIN; per i **fondi** ``symbol``
    è il **codice interno** di Borsa Italiana (es. ``2FADB602822``) e ``link``
    punta a ``scheda.html?code={codice}`` — l'ISIN non è presente nella quote.
    """
    parametri = {"lang": lingua, "q": query}

    try:
        dati = sessione.get_json(_URL_RICERCA, params=parametri)
    except Exception as err:
        raise RicercaNonDisponibile(
            "La ricerca JSON non è disponibile. "
            "Alternativa: usa lista_btp() per ottenere la lista dei BTP "
            f"oppure ottieni_scheda() con un ISIN noto. Errore: {err}"
        ) from err

    quotes = dati.get("quotes", [])

    # exactSymbolMatch → redirect diretto nel browser, per noi è il match esatto
    exact = dati.get("exactSymbolMatch")
    if exact and isinstance(exact, list):
        quotes = exact + quotes

    risultati: list[RisultatoRicerca] = []
    simboli_visti: set[str] = set()

    for q in quotes:
        simbolo = q.get("symbol", "")
        if not simbolo or simbolo in simboli_visti:
            continue
        simboli_visti.add(simbolo)
        risultati.append(
            RisultatoRicerca(
                isin=simbolo,
                mic=q.get("mic", ""),
                nome=q.get("title", ""),
                tipo=q.get("typeLabel", ""),
                mercato=q.get("mercato", ""),
                comparto=q.get("comparto") or None,
                sotto_comparto=q.get("subcomparto") or None,
                dettaglio_mercato=q.get("marketDetail") or None,
                sotto_tipo=q.get("subtype") or None,
                link=q.get("link") or None,
            )
        )

    return risultati


def _varianti_query(query: str) -> list[str]:
    """Genera varianti progressive di una query per il match per-prefisso di BI.

    1. Accorcia ogni parola lunga (>7 caratteri) a un prefisso di 6 caratteri
       (es. ``DIVERSIFICATO`` → ``Divers``, prefisso valido di ``Divers.``).
    2. Rimuove progressivamente le parole più lunghe (≥8 caratteri), spesso
       quelle che non combaciano con il nome abbreviato di Borsa Italiana.
    """
    tokens = query.split()
    if not tokens:
        return []

    varianti: list[str] = []

    def _aggiungi(nuovi: list[str]) -> None:
        testo = " ".join(nuovi).strip()
        if testo and testo.lower() != query.lower() and testo not in varianti:
            varianti.append(testo)

    # 1) Prefisso a 6 caratteri per le parole alfabetiche lunghe.
    stemmed = [t[:6] if len(t) > 7 and t.isalpha() else t for t in tokens]
    if stemmed != tokens:
        _aggiungi(stemmed)

    # 2) Rimozione progressiva delle parole più lunghe (≥8 caratteri).
    ordine_lunghezza = sorted(range(len(tokens)), key=lambda i: len(tokens[i]), reverse=True)
    rimossi: set[int] = set()
    for idx in ordine_lunghezza:
        if len(tokens[idx]) < 8:
            break
        rimossi.add(idx)
        residui = [t for i, t in enumerate(tokens) if i not in rimossi]
        if len(residui) >= 2:
            _aggiungi(residui)

    return varianti
