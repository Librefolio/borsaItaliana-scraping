"""Esempio: storico + metadati del BTP Più (IT0005634800)."""

from borsa_italiana_scraping import Sessione, ottieni_scheda, ottieni_storico

sessione = Sessione()

try:
    # Storico
    storico = ottieni_storico("IT0005634800", periodo="MAX", sessione=sessione)
    print(f"Storico BTP Più: {len(storico.punti)} punti")
    if storico.punti:
        ultimo = storico.punti[-1]
        print(f"  Ultimo: {ultimo.data} → {ultimo.ultimo}")
    print()

    # Metadati (scraping pagina scheda)
    scheda = ottieni_scheda("IT0005634800", sessione=sessione)
    print(f"Nome: {scheda.nome}")
    print(f"Prezzo: {scheda.prezzo} {scheda.valuta}")
    print(f"Rendimento lordo: {scheda.rendimento_lordo}")
    print(f"Rendimento netto: {scheda.rendimento_netto}")
    print(f"Duration modificata: {scheda.duration_modificata}")
    print(f"Cedola annua: {scheda.cedola_annua}")
    print(f"Scadenza: {scheda.scadenza}")
finally:
    sessione.chiudi()
