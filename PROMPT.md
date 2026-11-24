# Prompt: Creazione libreria Python `borsa-italiana-scraping`

## Obiettivo

Creare una libreria Python standalone chiamata **`borsa-italiana-scraping`** (package: `borsa_italiana_scraping`) che espone funzioni per ottenere dati finanziari dal sito [borsaitaliana.it](https://www.borsaitaliana.it) — il portale ufficiale di Borsa Italiana (Euronext Milan).

La libreria copre: **azioni**, **obbligazioni** (BTP, BOT, CCT, CTZ, corporate, ecc.) e potenzialmente qualsiasi strumento quotato sul MOT/MTA/ETFplus.

**Lingua**: tutto in italiano — codice, commenti, docstring, documentazione, variabili. Solo le chiavi tecniche (nomi di campo JSON, HTTP header) restano in inglese.

---

## Setup progetto

- **Package manager**: Pipenv (`Pipfile` + `Pipfile.lock`)
- **Struttura**:

```
borsa-italiana-scraping/
├── Pipfile
├── Pipfile.lock
├── pyproject.toml              # metadata pacchetto (setuptools o hatchling)
├── README.md                   # Documentazione in italiano
├── LICENSE                     # MIT
├── borsa_italiana_scraping/
│   ├── __init__.py             # Esporta API pubblica
│   ├── storico.py              # Funzioni per dati storici (history API)
│   ├── tempo_reale.py          # Funzioni per prezzo corrente e intraday
│   ├── ricerca.py              # Funzione di ricerca strumenti
│   ├── scheda.py               # Scraping pagina scheda (metadati ricchi)
│   ├── lista.py                # Scraping liste strumenti (BTP, azioni, ecc.)
│   ├── tipi.py                 # Dataclass/TypedDict per i risultati
│   ├── sessione.py             # Gestione sessione HTTP (cookie warmup, rate limit)
│   └── eccezioni.py            # Eccezioni personalizzate
├── esempi/
│   ├── esempio_storico.py      # Esempio: scarica storico ENEL 1Y
│   ├── esempio_obbligazione.py # Esempio: storico + metadati BTP
│   ├── esempio_ricerca.py      # Esempio: cerca "BTP" e "ENEL"
│   └── esempio_completo.py     # Esempio end-to-end
└── test/
    ├── test_storico.py
    ├── test_tempo_reale.py
    ├── test_ricerca.py
    ├── test_scheda.py
    └── test_sessione.py
```

- **Dipendenze runtime**: `httpx`, `beautifulsoup4`, `lxml` (parser veloce)
- **Dipendenze dev**: `pytest`, `pytest-asyncio` (se serve), `black`, `ruff`

---

## API da esporre

### 1. `storico.py` — Dati storici (JSON API)

**Endpoint**: `GET https://grafici.borsaitaliana.it/api/instruments/{ISIN},XMIL,ISIN/history/period`

**Query params**:
- `period`: `1M`, `3M`, `6M`, `1Y`, `3Y`, `5Y`, `MAX`
- `adjustment`: `true` (opzionale, consigliato)
- `add-last-price`: `true` (opzionale, aggiunge punto corrente)

**Risposta JSON**:
```json
{
  "transco": {"code": "IT0003128367", "codification": "ISIN", "exchCode": "XMIL"},
  "history": {
    "historyDt": [
      {
        "dt": "20210512",
        "openPx": 8.063,
        "closePx": 7.992,
        "highPx": 8.135,
        "lowPx": 7.992,
        "lastPx": 7.992,
        "qty": 24350542.0,
        "volNbTrade": 17978.0,
        "volCap": 195640475.918,
        "setPx": 8.034384,
        "vwap": 8.034338
      }
    ]
  }
}
```

**Funzione da esporre**:
```python
def ottieni_storico(
    isin: str,
    periodo: str = "1Y",  # 1M, 3M, 6M, 1Y, 3Y, 5Y, MAX
    aggiustato: bool = True,
    includi_ultimo: bool = True,
    sessione: Sessione | None = None,
) -> StoricoRisultato:
    """
    Scarica i dati storici OHLCV per un titolo identificato da ISIN.

    Ritorna un oggetto StoricoRisultato con:
    - isin: str
    - codice_borsa: str (es. "XMIL")
    - punti: list[PuntoStorico]

    Ogni PuntoStorico ha:
    - data: date
    - apertura: Decimal
    - chiusura: Decimal
    - massimo: Decimal
    - minimo: Decimal
    - ultimo: Decimal
    - volume: int
    - numero_contratti: int | None
    - controvalore: Decimal | None
    """
```

**NOTE IMPORTANTI per l'implementazione**:
- L'API grafici richiede un "cookie warmup" per molti periodi. Il primo accesso senza cookie funziona solo per certi periodi (es. 1Y). Per sbloccare tutti i periodi, bisogna prima fare una GET alla pagina dei grafici sul sito principale (`https://www.borsaitaliana.it/borsa/obbligazioni/mot/btp/grafico.html?isin={ISIN}&lang=it` oppure qualsiasi pagina grafici) per ottenere il cookie Imperva, e poi usare quel cookie per le chiamate all'API grafici.
- Questo warmup è gestito dalla classe `Sessione` (vedi sotto).
- Il campo `dt` è in formato `YYYYMMDD`, da parsare a `datetime.date`.
- L'ultimo punto (giornata corrente/in corso) potrebbe non avere tutti i campi (`volNbTrade`, `volCap`, `setPx` possono mancare).

### 2. `tempo_reale.py` — Prezzo corrente e Intraday (JSON API)

**Endpoint intraday**: `GET https://grafici.borsaitaliana.it/api/instruments/{ISIN},XMIL,ISIN/intraday`

**Query params**:
- `resolution`: `1MN` (1 minuto), `5MN`, `15MN`, `30MN`, `1H`

**Risposta JSON (intraday)**:
```json
{
  "intradayPoint": [
    {
      "time": "20260512-09:00:00",
      "nbTrade": 527,
      "beginPx": 9.821,
      "endPx": 9.768,
      "highPx": 9.833,
      "lowPx": 9.755,
      "vol": 662963.0,
      "amt": 6499403.001,
      "previousClosingPx": 9.883,
      "previousClosingDt": "20260511"
    }
  ]
}
```

**Funzioni da esporre**:
```python
def ottieni_intraday(
    isin: str,
    risoluzione: str = "1MN",  # 1MN, 5MN, 15MN, 30MN, 1H
    sessione: Sessione | None = None,
) -> IntradayRisultato:
    """Scarica i dati intraday della giornata corrente."""


def ottieni_prezzo_corrente(
    isin: str,
    sessione: Sessione | None = None,
) -> PrezzoCorrente:
    """
    Ottiene il prezzo corrente di un titolo.

    Strategia: usa l'endpoint storico con periodo 1M e prende l'ultimo punto.
    Fallback: scraping della pagina scheda.

    Ritorna PrezzoCorrente con:
    - isin: str
    - prezzo: Decimal
    - variazione_percentuale: Decimal | None
    - data: date
    - valuta: str (letta dai metadati, default "EUR")
    - fonte: str ("api" o "scraping")
    """
```

### 3. `ricerca.py` — Ricerca strumenti

**Endpoint**: `GET https://www.borsaitaliana.it/borsa/searchengine/search.html`

**Query params**:
- `lang`: `it` o `en`
- `q`: query di ricerca

**ATTENZIONE**: questo endpoint richiede headers XHR (`X-Requested-With: XMLHttpRequest`, `Accept: application/json`) e tipicamente un cookie Cloudflare valido. In caso di fallimento (risposta HTML anziché JSON, o 403), la funzione deve fare fallback al scraping delle liste HTML.

**Risposta JSON (quando funziona)**:
```json
{
  "quotes": [
    {
      "symbol": "IT0005547408",
      "mic": "MOTX",
      "title": "Btp Valore Gn27 Eur",
      "typeLabel": "Obbligazione",
      "mercato": "MOT",
      "subcomparto": "BTP",
      "comparto": "TITOLOSTATO"
    }
  ],
  "news": [...],
  "pages": [...],
  "documents": [...],
  "terms": [...]
}
```

**Funzione da esporre**:
```python
def cerca(
    query: str,
    lingua: str = "it",  # "it" o "en"
    solo_strumenti: bool = True,  # filtra solo quotes[], ignora news/pages/docs
    sessione: Sessione | None = None,
) -> list[RisultatoRicerca]:
    """
    Cerca strumenti finanziari su Borsa Italiana.

    Ogni RisultatoRicerca ha:
    - isin: str (dal campo 'symbol')
    - mic: str (es. "MOTX", "MTAA")
    - nome: str (dal campo 'title')
    - tipo: str (dal campo 'typeLabel', es. "Obbligazione", "Azione")
    - mercato: str (es. "MOT", "MTA")
    - comparto: str | None (es. "TITOLOSTATO")
    - sotto_comparto: str | None (es. "BTP")

    In caso di errore con l'API JSON (Cloudflare block),
    solleva RicercaNonDisponibile con messaggio esplicativo.
    """
```

### 4. `scheda.py` — Scraping pagina strumento (HTML)

**URL pattern**: 
- Obbligazioni: `https://www.borsaitaliana.it/borsa/obbligazioni/mot/btp/scheda/{ISIN}-{MIC}.html?lang=en`
- Azioni: `https://www.borsaitaliana.it/borsa/azioni/scheda/{ISIN}.html?lang=it`
- URL universale (redirect): `https://www.borsaitaliana.it/borsa/search/scheda.html?code={ISIN}&mic={MIC}&lang=en`
- Dati completi: `/borsa/obbligazioni/mot/btp/dati-completi.html?isin={ISIN}&mic={MIC}&lang=en`

**Dati estraibili dalla pagina scheda/dati-completi** (HTML scraping con BeautifulSoup):

Per **azioni**:
- Prezzo, variazione %
- Apertura, Min/Max oggi, Min/Max anno
- Super Sector
- Codice alfanumerico (ticker)
- Mercato/Segmento
- Market Cap
- Lotto minimo
- Performance 1m, 6m, 1y
- Valuta di negoziazione

Per **obbligazioni**:
- Prezzo, variazione %
- Prezzo ufficiale, prezzo di riferimento
- Rendimento a scadenza lordo e netto
- Rateo lordo e netto
- Duration modificata
- Cedola periodale e annua
- Scadenza
- Emittente
- Tipo bond (Step Coupon, Zero Coupon, Fixed Rate, ecc.)
- Lotto minimo
- Ammontare emesso
- Subordinazione
- Data godimento
- Valuta di negoziazione/liquidazione
- Descrizione payout

**Funzione da esporre**:
```python
def ottieni_scheda(
    isin: str,
    mic: str | None = None,  # Se None, usa l'URL universale con redirect
    lingua: str = "en",
    sessione: Sessione | None = None,
) -> SchedaStrumento:
    """
    Scraping della pagina scheda di uno strumento.

    Ritorna SchedaStrumento con:
    - isin: str
    - nome: str
    - prezzo: Decimal
    - variazione_percentuale: Decimal | None
    - valuta: str (letta dalla pagina, es. "EUR")
    - tipo: str ("azione", "obbligazione", "etf", "altro")
    - mercato: str

    # Campi specifici obbligazioni (None per azioni):
    - rendimento_lordo: Decimal | None
    - rendimento_netto: Decimal | None
    - rateo_lordo: Decimal | None
    - rateo_netto: Decimal | None
    - duration_modificata: Decimal | None
    - cedola_annua: Decimal | None
    - cedola_periodale: Decimal | None
    - scadenza: date | None
    - emittente: str | None
    - tipo_bond: str | None
    - lotto_minimo: int | None
    - descrizione_payout: str | None

    # Campi specifici azioni (None per obbligazioni):
    - settore: str | None
    - capitalizzazione: Decimal | None
    - ticker: str | None
    - performance_1m: Decimal | None
    - performance_6m: Decimal | None
    - performance_1y: Decimal | None
    """
```

La **lingua preferita per lo scraping è `en`** (inglese) perché le label sono più stabili e parsabili. Ma la funzione accetta anche `it`.

**Note sullo scraping**:
- Le pagine usano un layout a coppie chiave-valore. Le label (es. "Negotiation currency", "Annual Coupon Rate") precedono il valore.
- I numeri per la versione EN usano il formato `1,234.56` (punto decimale, virgola migliaia).
- I numeri per la versione IT usano il formato `1.234,56` (virgola decimale, punto migliaia).
- Gestire entrambi i formati in base alla `lingua`.
- La valuta si legge dal campo "Negotiation Currency" / "Valuta di Negoziazione" nella pagina. Se non trovata, default a "EUR".

### 5. `lista.py` — Liste strumenti (HTML scraping)

**URL pattern**:
- Lista BTP: `https://www.borsaitaliana.it/borsa/obbligazioni/mot/btp/lista.html?lang=en`
- (analoghe per BOT, CCT, ecc.)

La pagina contiene una tabella HTML con tutti gli strumenti del tipo, inclusi ISIN, nome, ultimo prezzo, cedola, scadenza.

```python
def lista_btp(
    lingua: str = "en",
    sessione: Sessione | None = None,
) -> list[StrumentoLista]:
    """
    Ottiene la lista completa dei BTP quotati sul MOT.
    
    Ogni StrumentoLista ha:
    - isin: str
    - nome: str
    - ultimo_prezzo: Decimal | None
    - cedola: Decimal | None
    - scadenza: date | None
    - mic: str
    """
```

### 6. `sessione.py` — Gestione sessione HTTP

```python
class Sessione:
    """
    Gestisce la sessione HTTP verso Borsa Italiana.

    - Mantiene i cookie tra le richieste (fondamentale per il WAF Imperva)
    - Esegue il "cookie warmup" automatico al primo utilizzo
    - Rispetta i rate limit con backoff esponenziale
    - Riutilizzabile per multiple chiamate
    """

    def __init__(
        self,
        timeout: float = 30.0,
        max_tentativi: int = 3,
        pausa_minima: float = 0.5,  # secondi tra richieste
    ): ...

    def warmup(self) -> None:
        """
        Esegue il warmup dei cookie visitando una pagina del sito.
        Chiamato automaticamente alla prima richiesta se non già fatto.
        """
        ...

    def get_json(self, url: str, params: dict | None = None) -> dict:
        """GET con parsing JSON automatico."""
        ...

    def get_html(self, url: str, params: dict | None = None) -> BeautifulSoup:
        """GET con parsing HTML automatico (BeautifulSoup + lxml)."""
        ...

    def chiudi(self) -> None:
        """Chiude la sessione HTTP."""
        ...
```

**Logica di warmup**:
1. Prima di qualsiasi richiesta a `grafici.borsaitaliana.it`, controlla se i cookie Imperva sono presenti
2. Se no, fa una GET a `https://www.borsaitaliana.it/borsa/obbligazioni/mot/btp/grafico.html?isin=IT0005634800&lang=it` (o qualsiasi pagina grafici)
3. I cookie ottenuti (`visid_incap_*`, `incap_ses_*`) vengono mantenuti e riutilizzati
4. Implementa pausa minima tra richieste consecutive per evitare rate limiting

### 7. `tipi.py` — Tipi di dati

Definisci le seguenti dataclass (usando `@dataclass` standard o `TypedDict`):

```python
@dataclass
class PuntoStorico:
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
    isin: str
    codice_borsa: str       # es. "XMIL"
    punti: list[PuntoStorico]

@dataclass
class PuntoIntraday:
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
    isin: str
    punti: list[PuntoIntraday]

@dataclass
class PrezzoCorrente:
    isin: str
    prezzo: Decimal
    variazione_percentuale: Decimal | None
    data: date
    valuta: str
    fonte: str              # "api" o "scraping"

@dataclass
class RisultatoRicerca:
    isin: str
    mic: str
    nome: str
    tipo: str               # "Obbligazione", "Azione", ecc.
    mercato: str
    comparto: str | None = None
    sotto_comparto: str | None = None

@dataclass  
class SchedaStrumento:
    # ... (come descritto sopra in scheda.py)

@dataclass
class StrumentoLista:
    isin: str
    nome: str
    ultimo_prezzo: Decimal | None
    cedola: Decimal | None
    scadenza: date | None
    mic: str
```

### 8. `eccezioni.py` — Eccezioni

```python
class BorsaItalianaErrore(Exception):
    """Errore base della libreria."""

    pass


class StrumentoNonTrovato(BorsaItalianaErrore):
    """Lo strumento con l'ISIN specificato non è stato trovato."""

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
```

---

## Esempi (`esempi/`)

### `esempio_storico.py`
```python
"""Esempio: scarica lo storico di ENEL (IT0003128367) per 1 anno."""

from borsa_italiana_scraping import ottieni_storico, Sessione

sessione = Sessione()
risultato = ottieni_storico("IT0003128367", periodo="1Y", sessione=sessione)

print(f"ISIN: {risultato.isin}")
print(f"Borsa: {risultato.codice_borsa}")
print(f"Punti: {len(risultato.punti)}")
for p in risultato.punti[-5:]:
    print(f"  {p.data}: O={p.apertura} H={p.massimo} L={p.minimo} C={p.chiusura} V={p.volume}")

sessione.chiudi()
```

### `esempio_obbligazione.py`
```python
"""Esempio: storico + metadati del BTP Più (IT0005634800)."""

from borsa_italiana_scraping import ottieni_storico, ottieni_scheda, Sessione

sessione = Sessione()

# Storico
storico = ottieni_storico("IT0005634800", periodo="MAX", sessione=sessione)
print(f"Storico BTP Più: {len(storico.punti)} punti")

# Metadati (scraping pagina scheda)
scheda = ottieni_scheda("IT0005634800", sessione=sessione)
print(f"Nome: {scheda.nome}")
print(f"Prezzo: {scheda.prezzo} {scheda.valuta}")
print(f"Rendimento lordo: {scheda.rendimento_lordo}%")
print(f"Rendimento netto: {scheda.rendimento_netto}%")
print(f"Duration modificata: {scheda.duration_modificata}")
print(f"Cedola annua: {scheda.cedola_annua}%")
print(f"Scadenza: {scheda.scadenza}")

sessione.chiudi()
```

---

## Test (`test/`)

I test devono essere **integrazione reale** (non mock) — fanno richieste vere al sito. Questo è accettabile perché:
1. I test sono lenti e vanno eseguiti manualmente (`pytest test/ -v`)
2. Servono per verificare che il sito non abbia cambiato formato
3. Usare marker `@pytest.mark.integration` per poterli filtrare

**ISIN di test consigliati**:
- Azione: `IT0003128367` (ENEL)
- BTP classico: `IT0005634800` (BTP Più Feb 2033)
- Un BTP semplice a tasso fisso: `IT0005560948` (BTP 15/02/2031)

Ogni test verifica:
- Il tipo di ritorno è corretto (dataclass giusta)
- I campi obbligatori non sono None
- I numeri sono Decimal positivi dove atteso
- Le date sono parsate correttamente

---

## Documentazione (`README.md`)

Scrivi un README.md in italiano che includa:

1. **Titolo e descrizione** — cos'è la libreria
2. **Installazione** — `pipenv install borsa-italiana-scraping` (o da git)
3. **Quickstart** — 3 esempi minimali (storico, prezzo corrente, ricerca)
4. **API Reference** — tabella con tutte le funzioni esportate, parametri, e tipo di ritorno
5. **Tabella "Quando fa scraping vs quando legge JSON"**:

| Funzione | Metodo | Endpoint |
|----------|--------|----------|
| `ottieni_storico()` | JSON API | `grafici.borsaitaliana.it/api/instruments/.../history/period` |
| `ottieni_intraday()` | JSON API | `grafici.borsaitaliana.it/api/instruments/.../intraday` |
| `ottieni_prezzo_corrente()` | JSON API + fallback scraping | API history 1M → ultimo punto, fallback → pagina scheda |
| `cerca()` | JSON API (XHR) | `www.borsaitaliana.it/borsa/searchengine/search.html` |
| `ottieni_scheda()` | Scraping HTML | Pagina scheda strumento |
| `lista_btp()` | Scraping HTML | Pagina lista BTP |

6. **Note tecniche** — WAF Imperva, cookie warmup, rate limiting, formati numerici IT/EN
7. **Licenza** — MIT

---

## Regole di implementazione

1. **Sincrono** — tutte le funzioni sono sincrone (usano `httpx` sincrono, non async). Chi le chiama in async le wrappa con `asyncio.to_thread()`.
2. **Decimal** — tutti i prezzi/valori numerici sono `Decimal`, mai `float`.
3. **Gestione errori** — ogni funzione cattura eccezioni di rete e le converte nelle eccezioni personalizzate (`ErroreConnessione`, `RateLimitRaggiunto`, ecc.)
4. **Sessione opzionale** — se non passata, ogni funzione crea una sessione temporanea e la chiude. Passare una `Sessione` condivisa è più efficiente (riutilizzo cookie).
5. **Niente dipendenze pesanti** — no pandas, no numpy. Solo `httpx`, `beautifulsoup4`, `lxml`.
6. **User-Agent realistico** — la `Sessione` deve usare un User-Agent browser-like per evitare blocchi.
7. **Formato numeri** — gestire sia formato EN (`1,234.56`) che IT (`1.234,56`) nel parsing.
8. **pyproject.toml** — configurare il pacchetto con metadata (nome, versione, autore, dipendenze).
