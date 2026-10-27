#!/usr/bin/env python3
"""Ogni mattina 6 post: vendita, affitto e asta, a Terni e a Perugia.

Per ogni annuncio crea:
  - il video 4:5 (1080x1350) per Facebook: apertura + post animato con le foto + chiusura,
    pubblicato con la copertina = il post;
  - il Reel 9:16 (1080x1920) per Instagram, con la copertina sul post.
Usa le funzioni di lettura e pubblicazione di cercocasa_social.py.

  python sei_post.py              crea e pubblica i 6 post
  python sei_post.py --prova      crea video e testi, non pubblica
  python sei_post.py --quanti 1   solo il primo (per una prova pubblicata)
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
FPS, W, H, POST_MS = 30, 1080, 1350, 9000
COPERTINA_MS = 2600          # da qui il post è completo (serve per la copertina di Instagram)

SLOT = [  # (nome, tipo, città, pagina del sito)
    ("vendita-terni", "vendita", "terni", "/case-vendita/terni/"),
    ("vendita-perugia", "vendita", "perugia", "/case-vendita/perugia/"),
    ("affitto-terni", "affitto", "terni", "/case-affitto/terni/"),
    ("affitto-perugia", "affitto", "perugia", "/case-affitto/perugia/"),
    ("asta-terni", "asta", "terni", "/aste-immobiliari/terni/"),
    ("asta-perugia", "asta", "perugia", "/aste-immobiliari/perugia/"),
]
SFONDO = {"vendita": "#DB9C12", "affitto": "#F4F2ED", "asta": "#262626"}   # colore dei bordi nel 9:16
NON_CASE = re.compile(r"negozio|ufficio|locale|capannone|laboratorio|magazzino|garage|box|posto auto|"
                      r"cantina|terreno|stanza|camera per|commercial|industrial|albergo|hotel", re.I)
GENERICI = {"residenziale", "commerciale", "immobile", ""}


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


def scegli(stato):
    usati = {p.get("id") for p in stato["pubblicati"]}
    scelte = []
    for nome, tipo, citta, pagina in SLOT:
        try:
            schede = [s for s in leggi_elenco(tipo, pagina) if scheda_valida(tipo, s, usati)]
        except Exception as e:
            cs.log("  elenco non leggibile", pagina, e)
            continue
        casa = [s for s in schede if not NON_CASE.search(s["tipo_imm"] + " " + s["titolo"])]
        ordine = ([s for s in casa if tipo != "asta" or s.get("data_asta")] + casa + schede)
        if not ordine:
            cs.log("Nessun annuncio nuovo per", nome)
            continue
        s = dict(ordine[0], slot=nome, tipo=tipo, citta=citta)
        usati.add(s["id"])
        scelte.append(s)
        cs.log("Scelto", nome, s["id"], s["titolo"][:70])
    return scelte


# ---------------------------------------------------------------- grafica
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
                "price": euro(s["prezzo"]), "title": f"{tipo} a {dove}", "specs": voci, "photos": foto,
                "cta": "Perizia e avviso<br>link in bio"}
    zona = s["zona"] or s["citta"].title()
    d = {"theme": s["tipo"], "badge": "IN VENDITA" if s["tipo"] == "vendita" else "IN AFFITTO",
         "city": s["citta"].upper(), "price": euro(s["prezzo"]), "title": f"{tipo} · {zona}",
         "specs": s["voci"], "photos": foto,
         "cta": "Dettagli e foto<br>link in bio" if s["tipo"] == "vendita" else "Scrivici per<br>una visita"}
    if s["tipo"] == "affitto":
        d["suf"] = "al mese"
    return d


def foto_annuncio(s, cartella):
    """foto principale della scheda + fino a 2 foto in più dalla pagina dell'annuncio, convertite in jpg"""
    indirizzi = [s["foto"]]
    try:
        a = cs.leggi_annuncio(s["id"])
        s["dettaglio"] = a
        for u in a.get("foto", []):
            if u not in indirizzi and "mappa" not in u.lower():
                indirizzi.append(u)
    except Exception as e:
        cs.log("  pagina annuncio non letta:", e)
    file = []
    for i, u in enumerate(indirizzi[:3]):
        try:
            r = cs.HTTP.get(u, timeout=60)
            r.raise_for_status()
            grezzo = cartella / f"originale{i}{Path(u).suffix or '.jpg'}"
            grezzo.write_bytes(r.content)
            jpg = cartella / f"f{i}.jpg"
            cs.ff("-i", grezzo, "-vf", "scale='min(1600,iw)':-2", "-q:v", "3", jpg)
            file.append(jpg)
        except Exception as e:
            cs.log("  foto saltata", u, e)
    return file


def video_post(browser, s, cartella):
    foto = foto_annuncio(s, cartella)
    if not foto:
        raise RuntimeError("nessuna foto scaricata")
    dati = dati_post(s, ["file://" + str(f) for f in foto])
    fotogrammi = cartella / "fotogrammi"
    fotogrammi.mkdir()
    pagina = browser.new_page(viewport={"width": W, "height": H})
    pagina.add_init_script("window.POST = " + json.dumps(dati) + ";")
    pagina.goto("file://" + str(GRAFICA / "post.html"))
    pagina.evaluate("document.fonts.ready")
    pagina.wait_for_function("[...document.images].every(i => i.complete)", timeout=30000)
    for i in range(POST_MS * FPS // 1000):
        pagina.evaluate(f"window.seek({i * 1000 / FPS})")
        pagina.screenshot(path=str(fotogrammi / f"{i:04d}.png"))
    pagina.close()
    post = cartella / "post.mp4"
    cs.ff("-framerate", str(FPS), "-i", fotogrammi / "%04d.png", "-c:v", "libx264", "-preset", "veryfast",
          "-crf", "18", "-pix_fmt", "yuv420p", post)
    copertina = cartella / "copertina.jpg"
    cs.ff("-i", sorted(fotogrammi.iterdir())[-1], "-q:v", "2", copertina)
    shutil.rmtree(fotogrammi, ignore_errors=True)
    return post, copertina


def musica():
    brani = sorted(QUI.glob("*.mp3")) + sorted((QUI / "musica").glob("*.mp3"))
    if not brani:
        return None
    n = len(json.loads(cs.STATO.read_text()).get("pubblicati", [])) if cs.STATO.exists() else 0
    return brani[(n + date.today().toordinal()) % len(brani)]


def monta(post, s, destinazione, verticale):
    """apertura + post (con musica) + chiusura, in 4:5 oppure 9:16"""
    sfondo = SFONDO[s["tipo"]]
    alto = 1920 if verticale else H
    sigla = (f"scale={W}:1920,crop={W}:{alto},setsar=1,fps={FPS},format=yuv420p")
    corpo = (f"pad={W}:{alto}:0:(oh-ih)/2:color={sfondo},setsar=1,fps={FPS},format=yuv420p" if verticale
             else f"setsar=1,fps={FPS},format=yuv420p")
    ingressi = ["-i", cs.SIGLE / "apertura.mp4", "-i", post, "-i", cs.SIGLE / "chiusura.mp4"]
    brano = musica()
    dur = POST_MS / 1000
    if brano:
        ingressi += ["-ss", "3", "-t", str(dur), "-i", brano]
        audio_post = f"[3:a]atrim=0:{dur},asetpts=PTS-STARTPTS,volume=0.6,afade=t=in:d=0.6,afade=t=out:st={dur - 1}:d=1,aresample=48000,aformat=channel_layouts=stereo[ap]"
    else:
        ingressi += ["-f", "lavfi", "-t", str(dur), "-i", "anullsrc=r=48000:cl=stereo"]
        audio_post = "[3:a]anull[ap]"
    filtro = (f"[0:v]{sigla}[v0];[1:v]{corpo}[v1];[2:v]{sigla}[v2];"
              f"[0:a]aresample=48000,aformat=channel_layouts=stereo[a0];{audio_post};"
              f"[2:a]aresample=48000,aformat=channel_layouts=stereo[a2];"
              f"[v0][a0][v1][ap][v2][a2]concat=n=3:v=1:a=1[v][a]")
    cs.ff(*ingressi, "-filter_complex", filtro, "-map", "[v]", "-map", "[a]",
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
    offset = int((durata(cs.SIGLE / "apertura.mp4") * 1000) + COPERTINA_MS + 400)
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
    gia_slot = {p.get("sei") for p in fatti_oggi}
    scelte = [s for s in scegli(stato) if args.prova or s["slot"] not in gia_slot][:da_fare]

    from playwright.sync_api import sync_playwright
    pronti = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for s in scelte:
            cartella = Path(tempfile.mkdtemp())
            try:
                post, copertina = video_post(browser, s, cartella)
                v45 = monta(post, s, cs.USCITA / f"{s['slot']}.mp4", verticale=False)
                v916 = monta(post, s, cs.USCITA / f"{s['slot']}-reel.mp4", verticale=True)
                shutil.copy(copertina, cs.USCITA / f"{s['slot']}.jpg")
                for nome in social:
                    (cs.USCITA / f"{s['slot']}-{nome}.txt").write_text(testo(s, nome), encoding="utf-8")
                pronti.append((s, v45, v916, cs.USCITA / f"{s['slot']}.jpg"))
                cs.log("Video pronto:", v45.name, f"({durata(v45):.1f} s)")
            except Exception as e:
                cs.log("ERRORE video", s["slot"], e)
        browser.close()

    if args.prova:
        cs.log(f"Prova: {len(pronti)} video nella cartella video/ (nessuna pubblicazione)")
        return

    errori = 0
    for n, (s, v45, v916, copertina) in enumerate(pronti):
        if n:
            time.sleep(pausa)
        voce = {"id": s["id"], "sei": s["slot"], "social": [], "data": datetime.now().isoformat(timespec="minutes")}
        for nome in social:
            try:
                if nome == "facebook":
                    ris = cs.pubblica_facebook_quadrato(v45, testo(s, nome), copertina)
                elif nome == "instagram":
                    ris = pubblica_instagram_reel(v916, testo(s, nome))
                else:
                    ris = cs.PUBBLICA[nome](v916, testo(s, nome))
                if ris is not None:
                    voce["social"].append(nome)
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
