#!/usr/bin/env python3
"""Ogni mattina 6 post: vendita, affitto e asta, a Terni e a Perugia.

I video sono fatti esattamente come quelli del sistema di prima (cercocasa_social.crea_video):
copertina con il prezzo, sigla di apertura, foto a tutto schermo con le frasi dell'annuncio
lette dalla voce, scheda finale e sigla di chiusura con i contatti.
Qui cambia solo la scelta degli annunci: uno per ogni tipo e città.

  python sei_post.py              crea e pubblica i post di oggi
  python sei_post.py --prova      crea video e testi, non pubblica
  python sei_post.py --quanti 1   solo il primo
"""
import argparse
import json
import os
import re
import tempfile
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

import cercocasa_social as cs

SLOT = [  # (nome, tipo, città, pagina del sito)
    ("vendita-terni", "vendita", "terni", "/case-vendita/terni/"),
    ("vendita-perugia", "vendita", "perugia", "/case-vendita/perugia/"),
    ("affitto-terni", "affitto", "terni", "/case-affitto/terni/"),
    ("affitto-perugia", "affitto", "perugia", "/case-affitto/perugia/"),
    ("asta-terni", "asta", "terni", "/aste-immobiliari/terni/"),
    ("asta-perugia", "asta", "perugia", "/aste-immobiliari/perugia/"),
]
NON_CASE = re.compile(r"negozio|ufficio|locale|capannone|laboratorio|magazzino|garage|box|posto auto|"
                      r"cantina|terreno|stanza|camera per|commercial|industrial|albergo|hotel", re.I)
CANDIDATI = 6        # annunci di riserva per ogni tipo (se uno ha meno di 3 foto si passa al successivo)


# ---------------------------------------------------------------- scelta degli annunci
def id_annuncio(href):
    m = re.search(r"-(\d+)/?$", href or "") or re.search(r"id=(\d+)", href or "")
    return int(m.group(1)) if m else None


def prezzo_num(t):
    d = re.sub(r"[^\d]", "", t or "")
    return int(d) if d else 0


def leggi_elenco(tipo, pagina):
    """schede della pagina elenco: id, tipo di immobile, titolo, prezzo, foto (e data per le aste)"""
    zuppa = BeautifulSoup(cs.scarica_testo(cs.SITO + pagina), "html.parser")
    schede = []
    if tipo in ("vendita", "affitto"):
        for a in zuppa.select("a[href]"):
            img, corpo = a.select_one(".seo-card-photo img"), a.select_one(".seo-card-body")
            if not img or not corpo:
                continue
            small = corpo.select_one("small").get_text(" ", strip=True) if corpo.select_one("small") else ""
            schede.append({
                "id": id_annuncio(a["href"]), "foto": img.get("src", ""),
                "tipo_imm": small.partition("·")[0].strip(),
                "titolo": corpo.select_one("h3").get_text(" ", strip=True) if corpo.select_one("h3") else "",
                "prezzo": prezzo_num(corpo.select_one("b").get_text() if corpo.select_one("b") else ""),
            })
    else:
        for art in zuppa.select("article"):
            a, info = art.select_one("a.auction-image"), art.select_one(".auction-info")
            if not a or not info:
                continue
            img = a.select_one("img")
            small = info.select_one("small").get_text(" ", strip=True) if info.select_one("small") else ""
            meta = {}
            for s in info.select(".auction-meta span"):
                b = s.select_one("b")
                if b:
                    k = b.get_text(strip=True)
                    meta[k] = s.get_text(" ", strip=True).replace(k, "", 1).strip()
            schede.append({
                "id": id_annuncio(a["href"]), "foto": img.get("src", "") if img else "",
                "tipo_imm": small.partition("·")[0].strip(),
                "titolo": info.select_one("h2").get_text(" ", strip=True) if info.select_one("h2") else "",
                "prezzo": prezzo_num(info.select_one("strong").get_text() if info.select_one("strong") else ""),
                "data_asta": meta.get("Data asta", ""),
            })
    return schede


def scheda_valida(tipo, s, usati):
    if not s["id"] or s["id"] in usati or not s["foto"] or s["prezzo"] <= 0 or "mappa" in s["foto"].lower():
        return False
    if tipo == "asta" and s.get("data_asta"):
        try:
            if datetime.strptime(s["data_asta"], "%d/%m/%Y").date() <= date.today() + timedelta(days=2):
                return False      # asta passata o troppo vicina
        except ValueError:
            s["data_asta"] = ""
    return True


def candidati(stato):
    """per ogni tipo e città, gli annunci nuovi in ordine di preferenza (prima le case)"""
    usati = {p.get("id") for p in stato["pubblicati"]}
    out = []
    for nome, tipo, citta, pagina in SLOT:
        try:
            schede = [s for s in leggi_elenco(tipo, pagina) if scheda_valida(tipo, s, usati)]
        except Exception as e:
            cs.log("  elenco non leggibile", pagina, e)
            schede = []
        case = [s for s in schede if not NON_CASE.search(s["tipo_imm"] + " " + s["titolo"])]
        ordine, visti = [], set()
        for s in ([s for s in case if tipo != "asta" or s.get("data_asta")] + case + schede):
            if s["id"] not in visti:
                visti.add(s["id"])
                ordine.append(s["id"])
        out.append((nome, ordine[:CANDIDATI]))
        usati.update(ordine[:1])
    return out


# ---------------------------------------------------------------- voce: l'agenzia presenta l'annuncio
def nome_agenzia(nome):
    """'RM L'AGENZIA IMMOBILIARE' -> "RM L'Agenzia Immobiliare" (le sigle senza vocali restano maiuscole)"""
    nome = re.sub(r"\b(s\.?r\.?l\.?s?|s\.?a\.?s\.?|s\.?n\.?c\.?|s\.?p\.?a\.?)(?=\s|$)", "", nome or "", flags=re.I)
    nome = re.sub(r"^affiliato\s+", "", nome, flags=re.I).replace(":", "").strip(" ,.-")
    parole = []
    for w in nome.split():
        if w.isupper() and w.isalpha() and not re.search(r"[AEIOU]", w):
            parole.append(w)
        else:
            parole.append("'".join(x[:1].upper() + x[1:].lower() for x in w.split("'")))
    return " ".join(parole)


_apertura, _finale = cs.voce_apertura, cs.voce_finale


def voce_apertura(a):
    """'RM L'Agenzia Immobiliare presenta: appartamento in vendita a Terni, a 58.000 euro.'"""
    frase = _apertura(a)
    ag = nome_agenzia(a.get("agenzia"))
    return f"{ag} presenta: {frase[0].lower()}{frase[1:]}" if ag else frase


def voce_finale(a):
    return "Tutte le foto e i contatti su Cerco Casa Umbria."


cs.voce_apertura, cs.voce_finale = voce_apertura, voce_finale


# ---------------------------------------------------------------- creazione (come il sistema di prima)
def produci(nome, ids, social):
    """prova gli annunci in ordine finché uno ha abbastanza foto; crea il Reel verticale,
    il video quadrato per Facebook (con copertina) e i testi"""
    for id_ in ids:
        try:
            a = cs.leggi_annuncio(id_)
            foto = cs.scarica_foto(a, Path(tempfile.mkdtemp()))
            if len(foto) < 3:
                cs.log(f"  {nome}: annuncio {id_} con meno di 3 foto, passo al successivo")
                continue
            cs.log(f"{nome}: {id_} – {a['titolo']} – {a['prezzo']} – {a['agenzia']}")
            video = cs.USCITA / f"{nome}.mp4"
            durata = cs.crea_video(a, foto, video)
            quadrato = cs.USCITA / f"{nome}-quadrato.mp4"
            try:
                cs.crea_video_quadrato(a, foto, quadrato)
            except Exception as e:
                cs.log("  video quadrato non creato:", e)
                quadrato = None
            for s in social:
                (cs.USCITA / f"{nome}-{s}.txt").write_text(cs.testo_post(a, s), encoding="utf-8")
            cs.log(f"Video pronto: {video.name} ({durata:.1f} s)")
            return {"slot": nome, "a": a, "video": str(video), "quadrato": str(quadrato) if quadrato else None}
        except Exception as e:
            cs.log(f"  {nome}: annuncio {id_} non riuscito:", e)
    cs.log(f"Nessun annuncio utilizzabile per {nome}")
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prova", action="store_true", help="crea video e testi senza pubblicare")
    ap.add_argument("--quanti", type=int, default=int(os.environ.get("QUANTI_POST", "6") or 6))
    args = ap.parse_args()

    social = [x.strip() for x in os.environ.get("SOCIAL_SEI", "facebook,instagram").split(",") if x.strip()]
    pausa = int(os.environ.get("PAUSA_MINUTI", "3") or 3) * 60
    stato = cs.carica_stato()
    cs.USCITA.mkdir(exist_ok=True)
    oggi = date.today().isoformat()
    fatti_oggi = [p for p in stato["pubblicati"] if p.get("sei") and str(p.get("data", "")).startswith(oggi)]
    da_fare = max(0, args.quanti - (0 if args.prova else len(fatti_oggi)))
    if not da_fare:
        cs.log("I post di oggi sono già stati pubblicati.")
        return
    gia = {p.get("sei") for p in fatti_oggi}
    lista = [(n, ids) for n, ids in candidati(stato) if ids and (args.prova or n not in gia)][:da_fare]

    from concurrent.futures import ProcessPoolExecutor
    with ProcessPoolExecutor(max_workers=int(os.environ.get("VIDEO_IN_PARALLELO", "3") or 3)) as pool:
        lavori = [pool.submit(produci, n, ids, social) for n, ids in lista]
        pronti = []
        for (n, _), lavoro in zip(lista, lavori):
            try:
                r = lavoro.result()
                if r:
                    pronti.append(r)
            except Exception as e:
                cs.log("ERRORE video", n, e)

    if args.prova:
        cs.log(f"Prova: {len(pronti)} video nella cartella video/ (nessuna pubblicazione)")
        return

    errori = 0
    for k, r in enumerate(pronti):
        if k:
            time.sleep(pausa)
        a, video, quadrato = r["a"], Path(r["video"]), r["quadrato"] and Path(r["quadrato"])
        voce = {"id": a["id"], "sei": r["slot"], "social": [], "data": datetime.now().isoformat(timespec="minutes")}
        for nome in social:
            try:
                ris = None
                if nome == "facebook" and quadrato:
                    ris = cs.pubblica_facebook_quadrato(quadrato, cs.testo_post(a, nome),
                                                        cs.USCITA / (quadrato.stem + "-copertina.jpg"))
                else:
                    ris = cs.PUBBLICA[nome](video, cs.testo_post(a, nome))
                if ris is not None:
                    voce["social"].append(nome)
                    voce[f"{nome}_id"] = str(ris)
            except Exception as e:
                errori += 1
                cs.log(f"{nome}: ERRORE", r["slot"], e, (getattr(getattr(e, "response", None), "text", "") or "")[:500])
        if voce["social"]:
            stato["pubblicati"].append(voce)
            cs.STATO.write_text(json.dumps(stato, ensure_ascii=False, indent=1))
        cs.log("Pubblicato", r["slot"], "su:", ", ".join(voce["social"]) or "nessuno")
    if pronti and errori >= len(pronti) * len(social):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
