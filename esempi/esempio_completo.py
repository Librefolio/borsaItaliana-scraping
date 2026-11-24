"""Esempio end-to-end: storico, intraday, prezzo corrente, scheda, lista."""

from borsa_italiana_scraping import (
    DatiNonDisponibili,
    Sessione,
    lista_btp,
    ottieni_intraday,
    ottieni_prezzo_corrente,
    ottieni_scheda,
    ottieni_storico,
)

ISIN_ENEL = "IT0003128367"
ISIN_BTP = "IT0005634800"


def main() -> None:
    sessione = Sessione()

    try:
        # 1. Storico ENEL (1 anno)
        print("=" * 60)
        print("1. STORICO ENEL — 1Y")
        print("=" * 60)
        storico = ottieni_storico(ISIN_ENEL, periodo="1Y", sessione=sessione)
        print(f"   Punti: {len(storico.punti)}")
        if storico.punti:
            p = storico.punti[-1]
            print(f"   Ultimo: {p.data} C={p.chiusura} V={p.volume}")
        print()

        # 2. Intraday ENEL (5 minuti)
        print("=" * 60)
        print("2. INTRADAY ENEL — 5MN")
        print("=" * 60)
        try:
            intraday = ottieni_intraday(ISIN_ENEL, risoluzione="5MN", sessione=sessione)
            print(f"   Punti: {len(intraday.punti)}")
            if intraday.punti:
                p = intraday.punti[-1]
                print(f"   Ultimo: {p.orario} C={p.chiusura}")
        except DatiNonDisponibili:
            print("   ⚠ Dati intraday non disponibili (mercato chiuso?)")
        print()

        # 3. Prezzo corrente BTP
        print("=" * 60)
        print("3. PREZZO CORRENTE BTP Più")
        print("=" * 60)
        prezzo = ottieni_prezzo_corrente(ISIN_BTP, sessione=sessione)
        print(f"   Prezzo: {prezzo.prezzo} {prezzo.valuta}")
        print(f"   Data: {prezzo.data}")
        print(f"   Fonte: {prezzo.fonte}")
        print()

        # 4. Scheda BTP
        print("=" * 60)
        print("4. SCHEDA BTP Più")
        print("=" * 60)
        scheda = ottieni_scheda(ISIN_BTP, lingua="en", sessione=sessione)
        print(f"   Nome: {scheda.nome}")
        print(f"   Prezzo: {scheda.prezzo} {scheda.valuta}")
        print(f"   Tipo: {scheda.tipo}")
        print(f"   Rendimento lordo: {scheda.rendimento_lordo}")
        print(f"   Cedola annua: {scheda.cedola_annua}")
        print(f"   Scadenza: {scheda.scadenza}")
        print()

        # 5. Lista BTP
        print("=" * 60)
        print("5. LISTA BTP (primi 5)")
        print("=" * 60)
        btp_lista = lista_btp(lingua="en", sessione=sessione)
        print(f"   Totale BTP: {len(btp_lista)}")
        for b in btp_lista[:5]:
            print(f"   - {b.isin} | {b.nome} | {b.ultimo_prezzo} | scad={b.scadenza}")

    finally:
        sessione.chiudi()


if __name__ == "__main__":
    main()
