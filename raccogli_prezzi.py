#!/usr/bin/env python3
"""Raccoglie i prezzi da FUTBIN e scrive prezzi.json per fut-sniper.html.

Preparazione:  pip install requests
Uso:           python raccogli_prezzi.py   (poi ripetilo ogni 10 minuti con cron o Utilità di pianificazione)
giocatori.txt: una riga per giocatore ->  id,nome,valutazione   (es. 12345,Nome Cognome,91)
               gli ID li trovi nell’indirizzo della pagina FUTBIN del giocatore.

Ad ogni esecuzione salva il prezzo in storico.json. Da lì calcola:
  ref = prezzo mediano delle ultime 6 ore (il BIN "normale" di poco fa)
  avg = prezzo medio degli ultimi 7 giorni
I giocatori compaiono in prezzi.json quando hanno abbastanza letture (circa 1 ora a 10 minuti di intervallo).
"""
import json
import statistics
import time
from pathlib import Path

import requests

ANNO = 27             # numero negli indirizzi FUTBIN (futbin.com/27/...)
PIATTAFORMA = "ps"    # "ps" oppure "pc"
PAUSA = 3             # secondi tra due richieste: non scendere sotto, rischi il blocco
ORE_REF = 6
GIORNI_MEDIA = 7
MIN_LETTURE = 6

STORICO = Path("storico.json")


def leggi_prezzo(sessione, pid):
    # Indirizzo non ufficiale: se FUTBIN lo cambia o lo blocca, va adattato qui.
    r = sessione.get(f"https://www.futbin.com/{ANNO}/playerPrices", params={"player": pid}, timeout=20)
    r.raise_for_status()
    grezzo = r.json()[str(pid)]["prices"][PIATTAFORMA]["LCPrice"]
    return int(str(grezzo).replace(",", "").replace(".", "") or 0)


def main():
    storico = json.loads(STORICO.read_text()) if STORICO.exists() else {}
    righe = [r.strip() for r in Path("giocatori.txt").read_text(encoding="utf-8").splitlines()]
    righe = [r for r in righe if r and not r.startswith("#")]
    adesso = time.time()
    risultato = []

    with requests.Session() as s:
        s.headers.update({"User-Agent": "Mozilla/5.0"})
        for riga in righe:
            parti = [x.strip() for x in riga.split(",")]
            pid = parti[0]
            nome = parti[1] if len(parti) > 1 else pid
            valutazione = int(parti[2]) if len(parti) > 2 and parti[2].isdigit() else None
            try:
                prezzo = leggi_prezzo(s, pid)
            except Exception as e:
                print(f"{pid} {nome}: {e}")
                time.sleep(PAUSA)
                continue
            if prezzo > 0:
                letture = [x for x in storico.get(pid, []) if adesso - x[0] < GIORNI_MEDIA * 86400]
                recenti = [x[1] for x in letture if adesso - x[0] < ORE_REF * 3600]
                if len(letture) >= MIN_LETTURE and len(recenti) >= 3:
                    risultato.append({
                        "name": nome, "rating": valutazione, "price": prezzo,
                        "ref": round(statistics.median(recenti)),
                        "avg": round(statistics.mean(x[1] for x in letture)),
                        "url": f"https://www.futbin.com/{ANNO}/player/{pid}",
                    })
                letture.append([adesso, prezzo])
                storico[pid] = letture
            time.sleep(PAUSA)

    STORICO.write_text(json.dumps(storico))
    Path("prezzi.json").write_text(json.dumps(risultato, ensure_ascii=False))
    print(f"Fatto: {len(risultato)} giocatori in prezzi.json su {len(righe)} controllati")


if __name__ == "__main__":
    main()
