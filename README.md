# 📈 borsa-italiana-scraping

Libreria Python per ottenere dati finanziari dal sito ufficiale di [Borsa Italiana](https://www.borsaitaliana.it) (Euronext Milan).

Supporta **azioni**, **obbligazioni** (BTP, BOT, CCT, CTZ, corporate) e qualsiasi strumento quotato su MOT/MTA/ETFplus.

## ✨ Funzionalità

- 📊 **Dati storici OHLCV** — periodi da 1 mese a MAX
- ⏱️ **Dati intraday** — risoluzioni da 1 minuto a 1 ora
- 💰 **Prezzo corrente** — con fallback automatico API → scraping
- 🔍 **Ricerca strumenti** — per nome, ISIN, ticker
- 📋 **Scheda strumento** — metadati ricchi (rendimento, cedola, scadenza, settore…)
- 📋 **Profilo società** — metadati ricchi per le società (descrizione società, azionariato, contatti, dirigenza, )
- 📃 **Lista strumenti** — tutti i BTP quotati sul MOT
- 🍪 **Gestione automatica WAF** — warmup cookie Imperva trasparente

## 📦 Installazione

### Come dipendenza in un altro progetto

```bash
# Con pipenv (consigliato)
pipenv install git+https://github.com/Alfystar/borsaItaliana-scraping.git#egg=borsa-italiana-scraping

# Con pip
pip install git+https://github.com/Alfystar/borsaItaliana-scraping.git
```

In un `Pipfile` la dipendenza si dichiara così:

```toml
[packages]
borsa-italiana-scraping = {git = "https://github.com/Alfystar/borsaItaliana-scraping.git", ref = "main"}
```

Oppure in `pyproject.toml` / `requirements.txt`:

```
# requirements.txt
borsa-italiana-scraping @ git+https://github.com/Alfystar/borsaItaliana-scraping.git@main
```

### Sviluppo locale

```bash
git clone https://github.com/Alfystar/borsaItaliana-scraping.git
cd borsaItaliana-scraping
pipenv install --dev
pipenv run pip install -e .   # installa il pacchetto in modalità editabile
```

## 🚀 Quickstart

### Storico OHLCV

```python
from borsa_italiana_scraping import ottieni_storico, Sessione

with Sessione() as sess:
    storico = ottieni_storico("IT0003128367", periodo="1Y", sessione=sess)
    for p in storico.punti[-3:]:
        print(f"{p.data}: C={p.chiusura} V={p.volume}")
```

### Prezzo corrente

```python
from borsa_italiana_scraping import ottieni_prezzo_corrente

prezzo = ottieni_prezzo_corrente("IT0003128367")
print(f"{prezzo.prezzo} {prezzo.valuta} ({prezzo.fonte})")
```

### Ricerca strumenti

```python
from borsa_italiana_scraping import cerca

risultati = cerca("ENEL", lingua="it")
for r in risultati[:5]:
    print(f"{r.isin} — {r.nome} ({r.tipo})")
```

## 📖 API Reference

### Funzioni

| Funzione                                            | Descrizione                     | Ritorno                    |
| --------------------------------------------------- | ------------------------------- | -------------------------- |
| `ottieni_storico(isin, periodo, ...)`             | Dati storici OHLCV              | `StoricoRisultato`       |
| `ottieni_intraday(isin, risoluzione, ...)`        | Dati intraday giornata corrente | `IntradayRisultato`      |
| `ottieni_prezzo_corrente(isin, ...)`              | Prezzo più recente             | `PrezzoCorrente`         |
| `cerca(query, lingua, ...)`                       | Ricerca strumenti               | `list[RisultatoRicerca]` |
| `ottieni_scheda(isin, mic, lingua, ...)`          | Metadati dalla pagina scheda    | `SchedaStrumento`        |
| `ottieni_profilo_societa(isin, mic, lingua, ...)` | Metadati dalla pagina scheda    | `Profilo Società`       |
| `lista_btp(lingua, ...)`                          | Lista completa BTP su MOT       | `list[StrumentoLista]`   |

### Parametri comuni

| Parametro       | Tipo                | Descrizione                                             |
| --------------- | ------------------- | ------------------------------------------------------- |
| `isin`        | `str`             | Codice ISIN dello strumento                             |
| `periodo`     | `str`             | `1M`, `3M`, `6M`, `1Y`, `3Y`, `5Y`, `MAX` |
| `risoluzione` | `str`             | `1MN`, `5MN`, `15MN`, `30MN`, `1H`            |
| `lingua`      | `str`             | `"it"` o `"en"`                                     |
| `sessione`    | `Sessione \| None` | Sessione HTTP riutilizzabile (opzionale)                |

### Classe `Sessione`

```python
sessione = Sessione(
    timeout=30.0,  # timeout per richiesta (secondi)
    max_tentativi=3,  # retry in caso di errore
    pausa_minima=0.5,  # secondi tra richieste consecutive
)
```

Supporta il context manager (`with Sessione() as sess: ...`).

## 📊 Metodi di accesso

| Funzione                      | Metodo                       | Endpoint                                                        |
| ----------------------------- | ---------------------------- | --------------------------------------------------------------- |
| `ottieni_storico()`         | JSON API                     | `grafici.borsaitaliana.it/api/instruments/.../history/period` |
| `ottieni_intraday()`        | JSON API                     | `grafici.borsaitaliana.it/api/instruments/.../intraday`       |
| `ottieni_prezzo_corrente()` | JSON API + fallback scraping | API storico 1M → ultimo punto, fallback → pagina scheda       |
| `cerca()`                   | JSON API (XHR)               | `www.borsaitaliana.it/borsa/searchengine/search.html`         |
| `ottieni_scheda()`          | Scraping HTML                | Pagina scheda strumento                                         |
| `ottieni_profilo_societa()` | Scraping HTML                | Pagina Profilo Società                                         |
| `lista_btp()`               | Scraping HTML                | Pagina lista BTP                                                |

## ⚠️ Note tecniche

### WAF Imperva e autenticazione JWT

L'API `grafici.borsaitaliana.it` è protetta da un Web Application Firewall (Imperva) e richiede un token JWT per l'accesso.

La classe `Sessione` gestisce tutto **automaticamente**: alla prima richiesta visita la pagina `interactive-chart` del sito, estrae il JWT token (anonimo, lunga durata) e i cookie Imperva, che vengono poi riutilizzati per tutte le chiamate successive.

**Consiglio**: riutilizzare un'unica `Sessione` per tutte le chiamate per evitare warmup multipli.

### Rate limiting

La libreria implementa una pausa minima tra richieste consecutive (default: 0.5s) e retry con backoff esponenziale in caso di errore 429.

### Formati numerici

- Pagine in **inglese** (`lang=en`): numeri nel formato `1,234.56`
- Pagine in **italiano** (`lang=it`): numeri nel formato `1.234,56`

La libreria gestisce entrambi i formati automaticamente in base al parametro `lingua`.

### Tipi numerici

Tutti i prezzi e valori numerici sono restituiti come `Decimal` (mai `float`) per garantire la precisione finanziaria.

## 🧪 Test

I test sono di integrazione (richieste reali al sito):

```bash
# Tutti i test
pipenv run pytest test/ -v -m integration

# Solo un modulo
pipenv run pytest test/test_storico.py -v
```

## 📂 Struttura progetto

```
borsa-italiana-scraping/
├── borsa_italiana_scraping/
│   ├── __init__.py        # API pubblica
│   ├── storico.py         # Dati storici (JSON API)
│   ├── tempo_reale.py     # Intraday e prezzo corrente
│   ├── ricerca.py         # Ricerca strumenti (JSON XHR)
│   ├── scheda.py          # Scraping pagina scheda e profilo società
│   ├── lista.py           # Scraping liste strumenti
│   ├── tipi.py            # Dataclass per i risultati
│   ├── sessione.py        # Gestione sessione HTTP
│   └── eccezioni.py       # Eccezioni personalizzate
├── esempi/                # Script di esempio
├── test/                  # Test di integrazione
├── Pipfile                # Dipendenze (Pipenv)
├── pyproject.toml         # Metadata pacchetto
└── README.md
```

## 📝 Licenza

LGPL-3.0-or-later — vedi [LICENSE](LICENSE) e [LICENSE.GPL-3.0](LICENSE.GPL-3.0).

Puoi usare questa libreria come dipendenza in qualsiasi progetto (anche closed-source). Se modifichi il codice **della libreria stessa**, le modifiche devono restare open.
