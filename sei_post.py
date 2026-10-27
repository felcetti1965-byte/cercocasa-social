#!/usr/bin/env python3
"""Ogni mattina 6 post: vendita, affitto e asta, a Terni e a Perugia.

Grafica: il post Cercocasa (cartella grafica/) con le foto dell'annuncio che cambiano a ogni frase.
Voce e frasi: come il sistema di prima (cercocasa_social): l'agenzia presenta l'annuncio, poi
frasi brevi con i dati dell'annuncio ("80 metri quadrati", "2 camere da letto", "Con camino"...),
ognuna scritta sulla sua foto. Apertura breve, chiusura con i contatti.
Facebook: video 4:5 con copertina = il post. Instagram: Reel 9:16 con copertina sul post.

  python sei_post.py              crea e pubblica i post di oggi
  python sei_post.py --prova      crea video e testi, non pubblica
  python sei_post.py --quanti 1   solo il primo
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

import cercocasa_social as cs

QUI = Path(__file__).resolve().parent
GRAFICA = QUI / "grafica"
FPS, W, H = 30, 1080, 1350
COPERTINA_MS = 2600          # da qui il post è completo (serve per la copertina di Instagram)
MAX_FOTO = 9                 # foto dell'annuncio scaricate
MIN_FOTO = 3                 # sotto questo numero l'annuncio viene saltato
MAX_FRASI = 8                # frasi dette dalla voce (una foto per frase)
APERTURA_VELOCITA = 2.5      # la sigla di apertura (8 s) dura circa 3 s
CANDIDATI = 6                # annunci di riserva per ogni tipo

SLOT = [  # (nome, tipo, città, pagina del sito)
    ("vendita-terni", "vendita", "terni", "/case-vendita/terni/"),
    ("vendita-perugia", "vendita", "perugia", "/case-vendita/perugia/"),
    ("affitto-terni", "affitto", "terni", "/case-affitto/terni/"),
    ("affitto-perugia", "affitto", "perugia", "/case-affitto/perugia/"),
    ("asta-terni", "asta", "terni", "/aste-immobiliari/terni/"),
    ("asta-perugia", "asta", "perugia", "/aste-immobiliari/perugia/"),
]
SFONDO = {"vendita": "#DB9C12", "affitto": "#F4F2ED", "asta": "#262626"}   # colore dei bordi nel 9:16
GENERICI = {"residenziale", "commerciale", "immobile", ""}
NON_CASE = re.compile(r"negozio|ufficio|locale|capannone|laboratorio|magazzino|garage|box|posto auto|"
                      r"cantina|terreno|stanza|camera per|commercial|industrial|albergo|hotel", re.I)


# ---------------------------------------------------------------- scelta degli annunci
def id_annuncio(href):
    m = re.search(r"-(\d+)/?$", href or "") or re.search(r"id=(\d+)", href or "")
    return int(m.group(1)) if m else None


def prezzo_num(t):
    d = re.sub(r"[^\d]", "", t or "")
    return int(d) if d else 0


def voci_scheda(p):
    trovati = {}
    for parte in [x.strip() for x in (p or "").split("·") if x.strip()]:
        low = parte.lower()
        if "m²" in low or "mq" in low:
            trovati.setdefault("area", parte)
        elif "camer" in low:
            trovati.setdefault("camere", parte)
        elif "bagn" in low:
            trovati.setdefault("bagni", parte)
        elif "local" in low:
            trovati.setdefault("locali", parte)
    out = []
    if "area" in trovati:
        out.append(["area", trovati["area"]])
    if "camere" in trovati or "locali" in trovati:
        out.append(["bed", trovati.get("camere") or trovati["locali"]])
    if "bagni" in trovati:
        out.append(["bath", trovati["bagni"]])
    return out


def leggi_elenco(tipo, pagina):
    zuppa = BeautifulSoup(cs.scarica_testo(cs.SITO + pagina), "html.parser")
    schede = []
    if tipo in ("vendita", "affitto"):
        for a in zuppa.select("a[href]"):
            img, corpo = a.select_one(".seo-card-photo img"), a.select_one(".seo-card-body")
            if not img or not corpo:
                continue
            small = corpo.select_one("small").get_text(" ", strip=True) if corpo.select_one("small") else ""
            tipo_imm, _, zona = small.partition("·")
            schede.append({
                "id": id_annuncio(a["href"]), "url": urljoin(cs.SITO + "/", a["href"]),
                "foto": urljoin(cs.SITO + "/", img.get("src", "")),
                "tipo_imm": tipo_imm.strip(), "zona": zona.strip(),
                "titolo": corpo.select_one("h3").get_text(" ", strip=True) if corpo.select_one("h3") else "",
                "prezzo": prezzo_num(corpo.select_one("b").get_text() if corpo.select_one("b") else ""),
                "voci": voci_scheda(corpo.select_one("p").get_text(" ", strip=True) if corpo.select_one("p") else ""),
            })
    else:
        for art in zuppa.select("article"):
            a, info = art.select_one("a.auction-image"), art.select_one(".auction-info")
            if not a or not info:
                continue
            img = a.select_one("img")
            small = info.select_one("small").get_text(" ", strip=True) if info.select_one("small") else ""
            tipo_imm, _, luogo = small.partition("·")
            meta = {}
            for s in info.select(".auction-meta span"):
                b = s.select_one("b")
                if b:
                    k = b.get_text(strip=True)
                    meta[k] = s.get_text(" ", strip=True).replace(k, "", 1).strip()
            alt = img.get("alt", "") if img else ""
            mq = re.search(r"(\d[\d.]*)\s*m²", alt)
            schede.append({
                "id": id_annuncio(a["href"]), "url": urljoin(cs.SITO + "/", a["href"]),
                "foto": urljoin(cs.SITO + "/", img.get("src", "")) if img else "",
                "tipo_imm": re.sub(r"\s*all[’']asta", "", tipo_imm).strip(),
                "zona": re.sub(r"\s*\([A-Z]{2}\)\s*$", "", luogo).strip(),
                "titolo": info.select_one("h2").get_text(" ", strip=True) if info.select_one("h2") else "",
                "prezzo": prezzo_num(info.select_one("strong").get_text() if info.select_one("strong") else ""),
                "data_asta": meta.get("Data asta", ""), "tribunale": meta.get("Tribunale", ""),
                "mq": (mq.group(1) + " m²") if mq else "",
            })
    return schede


def scheda_valida(tipo, s, usati):
    if not s["id"] or s["id"] in usati or not s["foto"] or s["prezzo"] <= 0 or "mappa" in s["foto"].lower():
        return False
    if tipo == "asta" and s.get("data_asta"):
        try:
            if datetime.strptime(s["data_asta"], "%d/%m/%Y").date() <= date.today() + timedelta(days=2):
                return False
        except ValueError:
            s["data_asta"] = ""
    return True


def candidati(stato):
    """per ogni tipo e città: (nome, tipo, città, schede in ordine di preferenza, prima le case)"""
    usati = {p.get("id") for p in stato["pubblicati"]}
    out = []
    for nome, tipo, citta, pagina in SLOT:
        try:
            schede = [x for x in leggi_elenco(tipo, pagina) if scheda_valida(tipo, x, usati)]
        except Exception as e:
            cs.log("  elenco non leggibile", pagina, e)
            schede = []
        case = [x for x in schede if not NON_CASE.search(x["tipo_imm"] + " " + x["titolo"])]
        ordine, visti = [], set()
        for x in [x for x in case if tipo != "asta" or x.get("data_asta")] + case + schede:
            if x["id"] not in visti:
                visti.add(x["id"])
                ordine.append(x)
        out.append((nome, tipo, citta, ordine[:CANDIDATI]))
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
    """a fine video: come arrivare all'annuncio (QR sullo schermo o codice da cercare sul sito)"""
    return "Tutte le foto e i contatti: apri il link nella bio."


cs.voce_apertura, cs.voce_finale = voce_apertura, voce_finale


# ---------------------------------------------------------------- grafica e video
def euro(n):
    return "€ " + f"{n:,}".replace(",", ".")


def tipo_bello(t):
    t = (t or "").strip()
    return "Immobile" if t.lower() in GENERICI else t[0].upper() + t[1:]


def dati_post(s, foto):
    tipo = tipo_bello(s["tipo_imm"])
    if s["tipo"] == "asta":
        dove = s["zona"] or s["citta"].title()
        voci = []
        if s.get("data_asta"):
            voci.append(["cal", "Asta il " + s["data_asta"]])
        if s.get("mq"):
            voci.append(["area", s["mq"]])
        if s.get("tribunale"):
            voci.append(["court", "Trib. " + s["tribunale"]])
        if len(voci) < 2:
            voci.insert(0, ["pin", dove])
        return {"theme": "asta", "badge": "ASTA GIUDIZIARIA", "city": dove.upper(), "pre": "da",
                "price": euro(s["prezzo"]), "title": ((s.get("dettaglio") or {}).get("titolo") or f"{tipo} a {dove}"), "specs": voci, "photos": foto,
                "cta": "Perizia e avviso<br>link in bio"}
    zona = s["zona"] or s["citta"].title()
    d = {"theme": s["tipo"], "badge": "IN VENDITA" if s["tipo"] == "vendita" else "IN AFFITTO",
         "city": s["citta"].upper(), "price": euro(s["prezzo"]), "title": f"{tipo} · {zona}",
         "specs": s["voci"], "photos": foto,
         "cta": "Dettagli e foto<br>link in bio" if s["tipo"] == "vendita" else "Scrivici per<br>una visita"}
    if s["tipo"] == "affitto":
        d["suf"] = "al mese"
    return d


def parlato(frase):
    """la frase come la dice la voce (date per esteso, niente sigle)"""
    f = re.sub(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b",
               lambda m: f"{int(m.group(1))} {cs.MESI_LUNGHI[int(m.group(2)) - 1]} {m.group(3)}"
               if 1 <= int(m.group(2)) <= 12 else m.group(0), frase)
    return f if f.endswith((".", "!", "?")) else f + "."


def scene_e_voce(s, foto, cartella):
    """come i video di prima: l'agenzia presenta l'annuncio sulla foto principale, poi una frase breve
    per ogni foto (dati e caratteristiche dell'annuncio), poi si torna alla foto principale (= copertina)"""
    a = s["dettaglio"]
    frasi = cs.frasi_video(a)[:min(MAX_FRASI, len(foto) - 1)]
    pezzi = [(foto[0], "", cs.voce_apertura(a))]
    for i, f in enumerate(frasi):
        pezzi.append((foto[1 + i], f, parlato(f)))
    pezzi.append((foto[0], "", cs.voce_finale(a)))

    scene, didascalie, audio, t = [], [], [], 0
    for k, (fp, scritta, detto) in enumerate(pezzi):
        mp3 = cartella / f"voce{k}.mp3"
        d = cs.crea_voce(detto, mp3)            # stessa voce dei video di prima
        minimo = 3600 if k == 0 else (3400 if k == len(pezzi) - 1 else 2800)
        dur = max(minimo, int((d or 0) * 1000) + 800)
        scene.append({"photo": "file://" + str(fp), "start": t, "dur": dur})
        if scritta:
            didascalie.append({"text": scritta, "start": t, "dur": dur})
        if d:
            audio.append((mp3, t + 300))
        t += dur
    cs.log(f"  voce: {len(audio)} frasi, {len(scene)} foto, {t / 1000:.1f} s")
    return scene, didascalie, audio, t


def foto_annuncio(s, cartella):
    """foto principale della scheda + le altre foto dell'annuncio (senza planimetrie e mappe), in jpg"""
    a = s["dettaglio"]
    indirizzi = [urljoin(cs.SITO + "/", s["foto"])] if s.get("foto") else []
    for u in a.get("foto", []):
        if u not in indirizzi and not re.search(r"mappa|planimetr|piantin", u, re.I):
            indirizzi.append(u)
    file = []
    for u in indirizzi:
        if len(file) >= MAX_FOTO:
            break
        try:
            r = cs.HTTP.get(u, timeout=60)
            r.raise_for_status()
            i = len(file)
            grezzo = cartella / f"originale{i}{Path(u).suffix or '.jpg'}"
            grezzo.write_bytes(r.content)
            jpg = cartella / f"f{i}.jpg"
            cs.ff("-i", grezzo, "-vf", "scale='min(1600,iw)':-2", "-q:v", "3", jpg)
            file.append(jpg)
        except Exception as e:
            cs.log("  foto saltata", u, e)
    return file


FORMATI = {"reel": (1920, {"vertical": True}), "quadrato": (1080, {"square": True})}


def render(browser, dati, totale, cartella, formato):
    """fotogrammi della grafica -> video muto + copertina (ultimo fotogramma = foto principale).
    formato: 'reel' 1080x1920 (Instagram, TikTok) oppure 'quadrato' 1080x1080 (Facebook)"""
    alto, opzioni = FORMATI[formato]
    fotogrammi = cartella / f"fotogrammi-{formato}"
    fotogrammi.mkdir()
    pagina = browser.new_page(viewport={"width": W, "height": alto})
    pagina.add_init_script("window.POST = " + json.dumps(dict(dati, **opzioni)) + ";")
    pagina.goto("file://" + str(GRAFICA / "post.html"))
    pagina.evaluate("document.fonts.ready")
    pagina.wait_for_function("[...document.images].every(i => i.complete)", timeout=30000)
    for i in range(totale * FPS // 1000):
        pagina.evaluate(f"window.seek({i * 1000 / FPS})")
        pagina.screenshot(path=str(fotogrammi / f"{i:04d}.jpg"), type="jpeg", quality=92)
    pagina.close()
    video = cartella / f"{formato}.mp4"
    cs.ff("-framerate", str(FPS), "-i", fotogrammi / "%04d.jpg", "-c:v", "libx264", "-preset", "veryfast",
          "-crf", "18", "-pix_fmt", "yuv420p", video)
    copertina = cartella / f"copertina-{formato}.jpg"
    cs.ff("-i", sorted(fotogrammi.iterdir())[-1], "-q:v", "2", copertina)
    shutil.rmtree(fotogrammi, ignore_errors=True)
    return video, copertina


def video_post(browser, s, cartella, foto, con_facebook=True):
    """stesse scene, voce e musica: 9:16 per Instagram e TikTok, 1080x1080 per Facebook (solo se serve)"""
    scene, didascalie, voci, totale = scene_e_voce(s, foto, cartella)
    dati = dati_post(s, [x["photo"] for x in scene])
    dati.update(scenes=scene, captions=didascalie, total=totale)
    # ultima scena: QR che apre direttamente l'annuncio + codice da cercare sul sito
    import qrcode
    qr = cartella / "qr.png"
    qrcode.make(f"{cs.SITO}/immobile.php?id={s['id']}", box_size=12, border=2).save(qr)
    dati["qr"] = {"img": "file://" + str(qr), "code": str(s["id"]), "start": scene[-1]["start"]}
    reel, cop_reel = render(browser, dati, totale, cartella, "reel")
    quad, cop_quad = (render(browser, dati, totale, cartella, "quadrato") if con_facebook else (None, cop_reel))
    audio = audio_post(voci, totale, cartella)
    return quad, reel, audio, cop_quad, cop_reel


def musica():
    brani = sorted(QUI.glob("*.mp3")) + sorted((QUI / "musica").glob("*.mp3"))
    if not brani:
        return None
    n = len(json.loads(cs.STATO.read_text()).get("pubblicati", [])) if cs.STATO.exists() else 0
    return brani[(n + date.today().toordinal()) % len(brani)]


def audio_post(voci, totale_ms, cartella):
    """musica bassa sotto la voce, ogni frase all'inizio della sua scena"""
    dur = totale_ms / 1000
    brano = musica()
    ingressi = (["-stream_loop", "-1", "-ss", "3", "-i", brano] if brano
                else ["-f", "lavfi", "-t", str(dur), "-i", "anullsrc=r=48000:cl=stereo"])
    vol = 0.16 if voci else 0.6
    filtro = (f"[0:a]atrim=0:{dur},asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo,"
              f"volume={vol},afade=t=in:d=0.5,afade=t=out:st={max(0, dur - 1.2):.2f}:d=1.2[m]")
    pezzi = []
    for k, (mp3, ms) in enumerate(voci):
        ingressi += ["-i", mp3]
        filtro += f";[{k + 1}:a]aformat=sample_rates=48000:channel_layouts=stereo,adelay={ms}|{ms},volume=1.6[p{k}]"
        pezzi.append(f"[p{k}]")
    filtro += (f";[m]{''.join(pezzi)}amix=inputs={len(pezzi) + 1}:duration=first:normalize=0[a]" if pezzi
               else ";[m]anull[a]")
    out = cartella / "audio.m4a"
    cs.ff(*ingressi, "-filter_complex", filtro, "-map", "[a]", "-t", f"{dur:.2f}",
          "-c:a", "aac", "-b:a", "160k", "-ar", "48000", out)
    return out


def apertura_breve():
    """la sigla di apertura accelerata (circa 3 secondi), creata una volta sola"""
    out = cs.USCITA / "apertura-breve.mp4"
    if not out.exists():
        v = 1 / APERTURA_VELOCITA
        cs.ff("-i", cs.SIGLE / "apertura.mp4", "-filter_complex",
              f"[0:v]setpts={v:.4f}*PTS[v];[0:a]atempo=2,atempo={APERTURA_VELOCITA / 2:.4f}[a]",
              "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
              "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "48000", out)
    return out


def monta(post, audio, s, destinazione, verticale):
    """apertura breve + annuncio (voce e musica) + chiusura con i contatti:
    9:16 (Instagram, TikTok) oppure quadrato 1080x1080 (Facebook), mai deformato"""
    stereo = "aresample=48000,aformat=sample_rates=48000:channel_layouts=stereo"
    fine = f"setsar=1,fps={FPS},format=yuv420p"
    if verticale:
        apertura = f"scale={W}:1920,{fine}"
        corpo = f"scale={W}:1920,{fine}"
        chiusura = f"[3:v]scale={W}:1920,{fine}[v2]"
    else:
        # come il video quadrato di prima: apertura ritagliata al centro, chiusura rimpicciolita sul fondo
        apertura = f"scale={W}:1920,crop={W}:{W}:0:420,{fine}"
        corpo = f"scale={W}:{W},{fine}"
        chiusura = (f"[3:v]scale={W}:1920,split[ca][cb];[ca]crop={W}:{W}:0:300[cbg];"
                    f"[cb]scale=918:1632,crop=918:{W}:0:270[cfg];[cbg][cfg]overlay=81:0,{fine}[v2]")
    filtro = (f"[0:v]{apertura}[v0];[1:v]{corpo}[v1];{chiusura};"
              f"[0:a]{stereo}[a0];[2:a]{stereo}[a1];[3:a]{stereo}[a2];"
              f"[v0][a0][v1][a1][v2][a2]concat=n=3:v=1:a=1[v][a]")
    cs.ff("-i", apertura_breve(), "-i", post, "-i", audio, "-i", cs.SIGLE / "chiusura.mp4",
          "-filter_complex", filtro, "-map", "[v]", "-map", "[a]",
          "-c:v", "libx264", "-profile:v", "main", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
          "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2", "-movflags", "+faststart", destinazione)
    return destinazione


def durata(f):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(f)],
                       capture_output=True, text=True)
    return float(r.stdout.strip() or 0)


# ---------------------------------------------------------------- testi
def testo(s, social):
    a = s.get("dettaglio")
    if a:
        try:
            return cs.testo_post(a, social)
        except Exception as e:
            cs.log("  testo standard non riuscito, uso quello semplice:", e)
    citta, tipo = s["citta"].title(), tipo_bello(s["tipo_imm"]).lower()
    if s["tipo"] == "asta":
        righe = [f"All'asta a {s['zona'] or citta}: {tipo}.",
                 f"Offerta minima {euro(s['prezzo'])}" + (f", asta il {s['data_asta']}" if s.get("data_asta") else "") + ".",
                 f"Perizia e avviso di vendita: {s['url']}"]
    else:
        verbo = "In vendita" if s["tipo"] == "vendita" else "In affitto"
        voci = ", ".join(v[1] for v in s.get("voci", []))
        righe = [f"{verbo} a {citta}: {tipo}" + (f" di {voci}." if voci else "."),
                 f"Prezzo {euro(s['prezzo'])}" + (" al mese." if s["tipo"] == "affitto" else "."),
                 f"Foto e dettagli: {s['url']}"]
    righe += ["Info: 349 125 9601", f"#{s['citta']} #umbria #cercocasaumbria"]
    return "\n".join(righe)


# ---------------------------------------------------------------- pubblicazione
def pubblica_instagram_reel(video, testo_ig):
    """come cs.pubblica_instagram, ma con la copertina sul post (non sul primo fotogramma della sigla)"""
    offset = int((durata(apertura_breve()) * 1000) + COPERTINA_MS + 400)
    originale = cs.HTTP.post

    def post_con_copertina(url, *a, **kw):
        dati = kw.get("data")
        if isinstance(dati, dict) and dati.get("media_type") == "REELS":
            dati["thumb_offset"] = str(offset)
        return originale(url, *a, **kw)

    cs.HTTP.post = post_con_copertina
    try:
        return cs.pubblica_instagram(video, testo_ig)
    finally:
        cs.HTTP.post = originale


def produci(nome, tipo, citta, schede, social):
    """prova gli annunci in ordine finché uno ha almeno 3 foto; crea i due video, copertina e testi"""
    from playwright.sync_api import sync_playwright
    for scheda in schede:
        cartella = Path(tempfile.mkdtemp())
        try:
            s = dict(scheda, slot=nome, tipo=tipo, citta=citta)
            s["dettaglio"] = cs.leggi_annuncio(s["id"])
            foto = foto_annuncio(s, cartella)
            if len(foto) < MIN_FOTO:
                cs.log(f"  {nome}: annuncio {s['id']} con {len(foto)} foto, passo al successivo")
                continue
            a = s["dettaglio"]
            cs.log(f"{nome}: {s['id']} – {a['titolo']} – {a['prezzo']} – {a['agenzia']}")
            with sync_playwright() as p:
                browser = p.chromium.launch()
                try:
                    post45, post916, audio, copertina, cop916 = video_post(browser, s, cartella, foto,
                                                                           con_facebook="facebook" in social)
                finally:
                    browser.close()
            v45 = monta(post45, audio, s, cs.USCITA / f"{nome}.mp4", verticale=False) if post45 else None
            v916 = monta(post916, audio, s, cs.USCITA / f"{nome}-reel.mp4", verticale=True)
            shutil.copy(cop916, cs.USCITA / f"{nome}-reel.jpg")
            cop = cs.USCITA / f"{nome}.jpg"
            shutil.copy(copertina, cop)
            for soc in social:
                (cs.USCITA / f"{nome}-{soc}.txt").write_text(cs.testo_post(a, soc), encoding="utf-8")
            cs.log("Video pronto:", v916.name, f"({durata(v916):.1f} s)")
            return s, v45, v916, cop
        except Exception as e:
            cs.log(f"  {nome}: annuncio {scheda.get('id')} non riuscito:", e)
        finally:
            shutil.rmtree(cartella, ignore_errors=True)
    cs.log(f"Nessun annuncio utilizzabile per {nome}")
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prova", action="store_true", help="crea video e testi senza pubblicare")
    ap.add_argument("--quanti", type=int, default=int(os.environ.get("QUANTI_POST", "6") or 6))
    ap.add_argument("--slot", default="", help="un post in più di questo tipo, es. vendita-perugia (prova a mano)")
    args = ap.parse_args()

    social = [x.strip() for x in os.environ.get("SOCIAL_SEI", "instagram,tiktok").split(",") if x.strip()]
    pausa = int(os.environ.get("PAUSA_MINUTI", "3") or 3) * 60
    stato = cs.carica_stato()
    cs.USCITA.mkdir(exist_ok=True)
    oggi = date.today().isoformat()
    fatti_oggi = [p for p in stato["pubblicati"] if p.get("sei") and str(p.get("data", "")).startswith(oggi)]
    if args.slot:      # un post in più del tipo scelto (annuncio mai pubblicato)
        lista = [x for x in candidati(stato) if x[0] == args.slot and x[3]][:1]
    else:
        da_fare = max(0, args.quanti - (0 if args.prova else len(fatti_oggi)))
        if not da_fare:
            cs.log("I post di oggi sono già stati pubblicati.")
            return
        gia = {p.get("sei") for p in fatti_oggi}
        lista = [x for x in candidati(stato) if x[3] and (args.prova or x[0] not in gia)][:da_fare]

    apertura_breve()
    pronti = []
    from concurrent.futures import ProcessPoolExecutor
    with ProcessPoolExecutor(max_workers=int(os.environ.get("VIDEO_IN_PARALLELO", "3") or 3)) as pool:
        lavori = [pool.submit(produci, n, t, c, schede, social) for n, t, c, schede in lista]
        for (n, *_), lavoro in zip(lista, lavori):
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
    for k, (s, v45, v916, copertina) in enumerate(pronti):
        if k:
            time.sleep(pausa)
        a = s["dettaglio"]
        voce = {"id": s["id"], "sei": s["slot"], "social": [], "data": datetime.now().isoformat(timespec="minutes"),
                # per la pagina "link nella bio" (cercocasaumbria.it/oggi.php)
                "titolo": a.get("titolo", ""), "prezzo": a.get("prezzo", ""), "comune": a.get("citta", ""),
                "foto": urljoin(cs.SITO + "/", s.get("foto", "")), "url": a.get("url", "")}
        for nome in social:
            try:
                if nome == "facebook":
                    ris = cs.pubblica_facebook_quadrato(v45, cs.testo_post(a, nome), copertina)
                elif nome == "instagram":
                    ris = pubblica_instagram_reel(v916, cs.testo_post(a, nome))
                else:
                    ris = cs.PUBBLICA[nome](v916, cs.testo_post(a, nome))
                if ris is not None:
                    voce["social"].append(nome)
                    voce[f"{nome}_id"] = str(ris)
            except Exception as e:
                errori += 1
                cs.log(f"{nome}: ERRORE", s["slot"], e, (getattr(getattr(e, "response", None), "text", "") or "")[:500])
        if voce["social"]:
            stato["pubblicati"].append(voce)
            cs.STATO.write_text(json.dumps(stato, ensure_ascii=False, indent=1))
        cs.log("Pubblicato", s["slot"], "su:", ", ".join(voce["social"]) or "nessuno")
    if pronti and errori >= len(pronti) * len(social):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
