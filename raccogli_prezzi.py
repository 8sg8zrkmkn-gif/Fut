#!/usr/bin/env python3
"""Raccoglie i prezzi da FUTBIN e scrive prezzi.json per l’app.

Preparazione:  pip install requests
Uso:           python raccogli_prezzi.py   (poi ogni 10 minuti con GitHub Actions, cron o Utilità di pianificazione)

giocatori.txt può contenere due tipi di righe:
  id,nome,valutazione,slug     un giocatore (es. 23987,Fermín López,86,fermin-lopez-marin)
  https://www.futbin.com/...   una pagina FUTBIN con un elenco di carte: lo script ne ricava da solo gli ID
id e slug sono nell’indirizzo FUTBIN del giocatore: futbin.com/27/player/ID/SLUG

Ad ogni esecuzione salva il prezzo in storico.json. Da lì calcola:
  ref = prezzo mediano delle ultime 6 ore (il BIN "normale" di poco fa)
  avg = prezzo medio degli ultimi 7 giorni
I giocatori compaiono in prezzi.json quando hanno abbastanza letture (circa 1 ora a 10 minuti di intervallo).
"""
import json
import re
import statistics
import time
from pathlib import Path

import requests

ANNO = 27                       # numero negli indirizzi FUTBIN (futbin.com/27/...)
PIATTAFORMA = "ps"              # "ps" oppure "pc"
PAUSA = 3                       # secondi tra due richieste: non scendere sotto, rischi il blocco
MAX_GIOCATORI = 120             # tetto per tenere breve ogni esecuzione
ORE_REF = 6
GIORNI_MEDIA = 7
MIN_LETTURE = 6
FUORI_FASCIA = (40000, 1300000) # chi sta fuori viene ricontrollato solo ogni ORE_FUORI ore
ORE_FUORI = 6

STORICO = Path("storico.json")
FRASE_PREZZO = re.compile(r"price on FUT is ([\d,.]+) on PlayStation, ([\d,.]+) on Xbox, and ([\d,.]+) on PC")


def scarica(sessione, url):
    r = sessione.get(url, timeout=20)
    r.raise_for_status()
    return r.text


def leggi_prezzo(sessione, pid, slug=""):
    # FUTBIN scrive nella pagina: "current price on FUT is X on PlayStation, Y on Xbox, and Z on PC".
    testo = scarica(sessione, f"https://www.futbin.com/{ANNO}/player/{pid}" + (f"/{slug}" if slug else ""))
    m = FRASE_PREZZO.search(testo)
    if not m:
        raise ValueError("prezzo non trovato nella pagina (blocco di FUTBIN o pagina cambiata)")
    valore = m.group(3) if PIATTAFORMA == "pc" else m.group(1)
    return int(re.sub(r"\D", "", valore) or 0)


def scopri(sessione, url):
    trovati = {}
    for pid, slug in re.findall(rf"/{ANNO}/player/(\d+)/([a-z0-9-]+)", scarica(sessione, url)):
        trovati.setdefault(pid, slug)
    return trovati


def main():
    storico = json.loads(STORICO.read_text()) if STORICO.exists() else {}
    righe = [r.strip() for r in Path("giocatori.txt").read_text(encoding="utf-8").splitlines()]
    righe = [r for r in righe if r and not r.startswith("#")]
    adesso = time.time()

    giocatori, liste = {}, []
    for riga in righe:
        if riga.startswith("http"):
            liste.append(riga)
            continue
        p = [x.strip() for x in riga.split(",")]
        val = int(p[2]) if len(p) > 2 and p[2].isdigit() else None
        giocatori[p[0]] = (p[1] if len(p) > 1 else p[0], val, p[3] if len(p) > 3 else "")

    risultato = []
    with requests.Session() as s:
        s.headers.update({"User-Agent": "Mozilla/5.0"})
        for url in liste:
            try:
                for pid, slug in scopri(s, url).items():
                    giocatori.setdefault(pid, (slug.replace("-", " ").title(), None, slug))
            except Exception as e:
                print(f"{url}: {e}")
            time.sleep(PAUSA)

        for pid, (nome, valutazione, slug) in list(giocatori.items())[:MAX_GIOCATORI]:
            letture = [x for x in storico.get(pid, []) if adesso - x[0] < GIORNI_MEDIA * 86400]
            if letture:
                ts, ultimo = letture[-1]
                if not FUORI_FASCIA[0] <= ultimo <= FUORI_FASCIA[1] and adesso - ts < ORE_FUORI * 3600:
                    continue
            try:
                prezzo = leggi_prezzo(s, pid, slug)
            except Exception as e:
                print(f"{pid} {nome}: {e}")
                time.sleep(PAUSA)
                continue
            if prezzo > 0:
                recenti = [x[1] for x in letture if adesso - x[0] < ORE_REF * 3600]
                if len(letture) >= MIN_LETTURE and len(recenti) >= 3:
                    risultato.append({
                        "name": nome, "rating": valutazione, "price": prezzo,
                        "ref": round(statistics.median(recenti)),
                        "avg": round(statistics.mean(x[1] for x in letture)),
                        "url": f"https://www.futbin.com/{ANNO}/player/{pid}" + (f"/{slug}" if slug else ""),
                    })
                letture.append([adesso, prezzo])
                storico[pid] = letture
            time.sleep(PAUSA)

    STORICO.write_text(json.dumps(storico))
    Path("prezzi.json").write_text(json.dumps(risultato, ensure_ascii=False))
    print(f"Fatto: {len(risultato)} giocatori in prezzi.json su {len(giocatori)} nella lista")


if __name__ == "__main__":
    main()
