"""Esempio: cerca 'BTP' e 'ENEL' su Borsa Italiana."""

from borsa_italiana_scraping import RicercaNonDisponibile, Sessione, cerca

sessione = Sessione()

try:
    for query in ("BTP", "ENEL"):
        print(f"=== Ricerca: '{query}' ===")
        try:
            risultati = cerca(query, lingua="it", sessione=sessione)
            print(f"  Trovati: {len(risultati)} risultati")
            for r in risultati[:5]:
                print(f"  - {r.isin} | {r.nome} | {r.tipo} | {r.mercato}")
        except RicercaNonDisponibile as err:
            print(f"  ⚠ Ricerca non disponibile: {err}")
        print()
finally:
    sessione.chiudi()
