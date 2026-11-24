"""Esempio: scarica lo storico di ENEL (IT0003128367) per 1 anno."""

from borsa_italiana_scraping import ottieni_storico, Sessione

sessione = Sessione()

try:
    risultato = ottieni_storico("IT0003128367", periodo="1Y", sessione=sessione)

    print(f"ISIN: {risultato.isin}")
    print(f"Borsa: {risultato.codice_borsa}")
    print(f"Punti totali: {len(risultato.punti)}")
    print()
    print("Ultimi 5 giorni:")
    for p in risultato.punti[-5:]:
        print(f"  {p.data}: O={p.apertura} H={p.massimo} L={p.minimo} C={p.chiusura} V={p.volume}")
finally:
    sessione.chiudi()
