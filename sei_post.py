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
FPS, W, H = 30, 1080, 1350
COPERTINA_MS = 2600          # da qui il post è completo (serve per la copertina di Instagram)
MAX_FOTO = 8                 # foto dell'annuncio usate nelle scene
MAX_FRASI = 5                # frasi della descrizione raccontate dalla voce
APERTURA_VELOCITA = 2.5      # la sigla di apertura (8 s) dura circa 3 s
# voce più naturale per prima; le altre solo se la prima non funziona (variabile VOCI per cambiarle)
VOCI = ["it-IT-GiuseppeMultilingualNeural", "it-IT-IsabellaNeural", "it-IT-DiegoNeural"]

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
    """foto principale della scheda + le altre foto della pagina dell'annuncio, convertite in jpg"""
    indirizzi = [s["foto"]]
    try:
        a = cs.leggi_annuncio(s["id"])
        s["dettaglio"] = a
        for u in a.get("foto", []):
            if u not in indirizzi and not re.search(r"mappa|planimetr|piantin", u, re.I):
                indirizzi.append(u)
    except Exception as e:
        cs.log("  pagina annuncio non letta:", e)
    file = []
    for i, u in enumerate(indirizzi[:MAX_FOTO]):
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


def dati_voce(s):
    """dati per frasi e voce: quelli completi della pagina annuncio, altrimenti quelli della scheda"""
    a = dict(s.get("dettaglio") or {})
    a.setdefault("titolo", s["titolo"])
    a.setdefault("citta", s["zona"] if s["tipo"] == "asta" else s["citta"].title())
    if not a.get("citta"):
        a["citta"] = s["citta"].title()
    a.setdefault("operazione", {"vendita": "IN VENDITA", "affitto": "IN AFFITTO", "asta": "ALL'ASTA"}[s["tipo"]])
    a.setdefault("prezzo", euro(s["prezzo"]))
    a.setdefault("agenzia", "")
    if not s.get("dettaglio"):
        for k, v in s.get("voci", []):
            n = re.match(r"\d+", v)
            if n and k == "area":
                a["mq"] = n.group(0)
            elif n and "camer" in v:
                a["camere"] = n.group(0)
            elif n and k == "bath":
                a["bagni"] = n.group(0)
    return a


MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
        "settembre", "ottobre", "novembre", "dicembre"]
STANZE = r"ingresso|soggiorno|salone|sala|cucin|camer|bagn|balcon|terrazz|giardin|cantin|garage|box|" \
         r"taverna|mansard|soffitta|ripostigl|studio|corte|piscina|vista|esterno|facciata|veranda|scala"
RIFERIMENTO = re.compile(r"^(rif\w*|riferimento|codice)\s*[:.]?\s*[\w/-]+\s*", re.I)
SCARTA_VOCE = re.compile(r"€|\biva\b|buona fede|telefon|contatt|www|@|codice|agenzia|mediazione|provvigion|"
                         r"appuntamento|chiama|whatsapp|informazion|classe energetica|\bape\b|perizia|procedura|"
                         r"lotto|prezzo|offerta minima|catast", re.I)


def data_a_parole(m):
    g, me, an = int(m.group(1)), int(m.group(2)), m.group(3)
    return f"{g} {MESI[me - 1]} {an}" if 1 <= me <= 12 else m.group(0)


def parlato(frase):
    """la frase come deve leggerla la voce"""
    f = re.sub(r"\([^)]*\)", "", frase)                              # niente sigle tra parentesi
    f = re.sub(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", data_a_parole, f)
    f = re.sub(r"€\s*([\d.]+)", r"\1 euro", f)
    f = re.sub(r"(\d)\s*(mq|m²|m2|metri quadri)\b", r"\1 metri quadrati", f, flags=re.I)
    f = re.sub(r"\bmq\b", "metri quadrati", f, flags=re.I)
    f = re.sub(r"\bloc\.\s*", "località ", f, flags=re.I)
    f = re.sub(r"\bfraz\.\s*", "frazione ", f, flags=re.I)
    f = re.sub(r"\bsnc\b|\bs\.n\.c\.", "", f, flags=re.I)
    f = re.sub(r"\bp\.\s*", "piano ", f)
    f = re.sub(r"\s+([,.;:])", r"\1", re.sub(r"\s{2,}", " ", f)).strip(" ,;")
    return f if f.endswith((".", "!", "?")) else f + "."


def frasi_descrizione(a, massimo=135):
    """la descrizione dell'agenzia in frasi intere, nell'ordine in cui è scritta (= giro della casa)"""
    testo = re.sub(r"\s+", " ", a.get("descrizione") or "")
    out = []
    for f in re.split(r"(?<=[.!?;])\s+", testo):
        f = RIFERIMENTO.sub("", f.strip()).strip()
        f = cs.APERTURE.sub("", f).strip(" .,;:-–")
        if len(f) < 20 or SCARTA_VOCE.search(f) or sum(ch.isdigit() for ch in f) > 10 or f.isupper():
            continue
        f = f[0].upper() + f[1:]
        if len(f) <= massimo:
            out.append(f)
            continue
        # frase lunga: la divido alle virgole in pezzi che si leggono bene
        pezzo = ""
        for p in re.split(r",\s+", f):
            if pezzo and len(pezzo) + len(p) + 2 > massimo:
                out.append(pezzo)
                pezzo = p
            else:
                pezzo = f"{pezzo}, {p}" if pezzo else p
        if pezzo:
            out.append(pezzo)
    return [x[0].upper() + x[1:] for x in out if len(x) >= 20]


def didascalia(frase, massimo=46):
    """scritta breve sulla foto: la parte della frase che parla di una stanza o di un punto di forza"""
    parti = [re.sub(r"^(ma|e|ed|che|con|di cui)\s+", "", p.strip(" .,;:"), flags=re.I)
             for p in re.split(r",\s+|\s+e\s+(?=\w+\s)|;\s*|:\s*", frase) if p.strip(" .,;:")]
    for p in parti:
        if re.search(STANZE, p, re.I) and 6 <= len(p) <= massimo:
            p = cs.ARTICOLO.sub("", p) if len(p) > 20 else p
            return p[0].upper() + p[1:]
    corte = [p for p in parti if 6 <= len(p) <= massimo]
    if corte:
        return corte[0][0].upper() + corte[0][1:]
    return cs.accorcia(frase, massimo)[0] if cs.accorcia(frase, massimo) else ""


def dati_principali(a, s):
    """una frase con superficie, camere e bagni (se la descrizione non li dice già)"""
    parti = []
    if a.get("mq"):
        parti.append(f"{a['mq']} metri quadrati")
    if a.get("camere"):
        parti.append("una camera da letto" if a["camere"] == "1" else f"{a['camere']} camere da letto")
    elif a.get("locali"):
        parti.append(f"{a['locali']} locali")
    if a.get("bagni"):
        parti.append("un bagno" if a["bagni"] == "1" else f"{a['bagni']} bagni")
    if not parti:
        return None
    testo = parti[0] if len(parti) == 1 else ", ".join(parti[:-1]) + " e " + parti[-1]
    return testo[0].upper() + testo[1:]


def nome_agenzia(nome):
    """'RM L'AGENZIA IMMOBILIARE' -> "RM L'Agenzia Immobiliare" (le sigle restano maiuscole)"""
    nome = re.sub(r"\b(s\.?r\.?l\.?s?|s\.?a\.?s\.?|s\.?n\.?c\.?|s\.?p\.?a\.?)\b", "", nome or "", flags=re.I)
    nome = re.sub(r"^affiliato\s+", "", nome, flags=re.I).replace(":", "").strip(" ,.-")
    parole = []
    for w in nome.split():
        if w.isupper() and w.isalpha() and not re.search(r"[AEIOU]", w):   # sigle come RM, GB
            parole.append(w)
        else:
            parole.append("'".join(x[:1].upper() + x[1:].lower() for x in w.split("'")))
    return " ".join(parole)


def voce_scelta():
    voci = [v.strip() for v in os.environ.get("VOCI", ",".join(VOCI)).split(",") if v.strip()]
    return voci


def crea_voce(testo, mp3):
    """prova le voci in ordine (la prima è la più naturale); None se nessuna funziona"""
    for v in voce_scelta():
        d = cs.crea_voce(testo, mp3, v)
        if d:
            return d, v
    return None, None


def scene_e_voce(s, foto, cartella):
    """La voce racconta l'annuncio con le frasi della descrizione, in ordine, mentre scorrono le foto.
    Ogni frase ha la sua scritta sullo schermo; una frase lunga copre più foto.
    Inizio e fine sulla foto principale (= copertina)."""
    a = dati_voce(s)
    tipo = cs.tipo_parola(a).capitalize()
    dove = a.get("citta") or s["citta"].title()
    if s["tipo"] == "asta":
        apertura = f"{tipo} all'asta a {dove}. Offerta minima {cs.prezzo_voce(a) or euro(s['prezzo'])}."
    else:
        apertura = cs.voce_apertura(a)
    racconto = []                              # (scritta, testo detto)
    if s["tipo"] == "asta" and (s.get("data_asta") or s.get("tribunale")):
        frase = "L'asta si terrà" + (f" il {s['data_asta']}" if s.get("data_asta") else "") + \
                (f" presso il Tribunale di {s['tribunale']}" if s.get("tribunale") else "")
        racconto.append(((f"Asta il {s['data_asta']}" if s.get("data_asta") else f"Tribunale di {s['tribunale']}"), frase))
    principali = dati_principali(a, s)
    descr = frasi_descrizione(a)
    if principali and not any(re.search(r"metri|mq|m²", d, re.I) for d in descr[:3]):
        racconto.append((principali, principali))
    for d in descr[:MAX_FRASI]:
        racconto.append((didascalia(d), d))
    if len(racconto) < 3:                       # descrizione povera: uso i punti di forza
        for f in cs.frasi_video(a):
            if len(racconto) >= 5:
                break
            if not (f.startswith("Zona ") and re.search(r"\d|\bvia\b|\bsnc\b|\bloc\.|,", f, re.I)):
                racconto.append((f, f))
    ag = nome_agenzia(a.get("agenzia") or "")
    if ag:   # "RM L'Agenzia Immobiliare presenta: appartamento in vendita a Terni..."
        apertura = f"{ag} presenta: {apertura[0].lower()}{apertura[1:]}"
    finale = "Tutte le foto e i contatti su Cerco Casa Umbria. Link in bio."

    pezzi = [("", apertura, "apertura")] + [(sc, dt, "racconto") for sc, dt in racconto] + [("", finale, "finale")]
    altre = foto[1:] or foto[:1]
    n_foto, foto_scene, didascalie, audio, t, voce_usata = 0, [], [], [], 0, None
    for k, (scritta, detto, ruolo) in enumerate(pezzi):
        mp3 = cartella / f"voce{k}.mp3"
        d, v = crea_voce(parlato(detto), mp3)
        voce_usata = voce_usata or v
        dur = max(3200 if ruolo != "racconto" else 3000, int((d or 0) * 1000) + 650)
        if ruolo == "apertura":
            foto_scene.append({"photo": "file://" + str(foto[0]), "start": t})
        elif ruolo == "finale":
            foto_scene.append({"photo": "file://" + str(foto[0]), "start": t})
        else:
            # una foto ogni ~3,8 secondi di voce, nell'ordine dell'agenzia
            quante = max(1, round(dur / 3800))
            for j in range(quante):
                foto_scene.append({"photo": "file://" + str(altre[n_foto % len(altre)]), "start": t + j * dur // quante})
                n_foto += 1
            didascalie.append({"text": scritta, "start": t, "dur": dur})
        if d:
            audio.append((mp3, t + 250))
        t += dur
    cs.log(f"  voce {str(voce_usata).replace('it-IT-', '')}: {len(audio)} frasi, {len(foto_scene)} foto, {t / 1000:.1f} s")
    return foto_scene, didascalie, audio, t


def video_post(browser, s, cartella):
    foto = foto_annuncio(s, cartella)
    if not foto:
        raise RuntimeError("nessuna foto scaricata")
    scene, didascalie, voci, totale = scene_e_voce(s, foto, cartella)
    dati = dati_post(s, [x["photo"] for x in scene])
    dati.update(scenes=scene, captions=didascalie, total=totale)
    fotogrammi = cartella / "fotogrammi"
    fotogrammi.mkdir()
    pagina = browser.new_page(viewport={"width": W, "height": H})
    pagina.add_init_script("window.POST = " + json.dumps(dati) + ";")
    pagina.goto("file://" + str(GRAFICA / "post.html"))
    pagina.evaluate("document.fonts.ready")
    pagina.wait_for_function("[...document.images].every(i => i.complete)", timeout=30000)
    for i in range(totale * FPS // 1000):
        pagina.evaluate(f"window.seek({i * 1000 / FPS})")
        pagina.screenshot(path=str(fotogrammi / f"{i:04d}.jpg"), type="jpeg", quality=92)
    pagina.close()
    post = cartella / "post.mp4"
    cs.ff("-framerate", str(FPS), "-i", fotogrammi / "%04d.jpg", "-c:v", "libx264", "-preset", "veryfast",
          "-crf", "18", "-pix_fmt", "yuv420p", post)
    copertina = cartella / "copertina.jpg"
    cs.ff("-i", sorted(fotogrammi.iterdir())[-1], "-q:v", "2", copertina)
    shutil.rmtree(fotogrammi, ignore_errors=True)
    audio = audio_post(voci, totale, cartella)
    return post, audio, copertina


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
    """apertura breve + annuncio (voce e musica) + chiusura con i contatti, in 4:5 oppure 9:16"""
    sfondo = SFONDO[s["tipo"]]
    alto = 1920 if verticale else H
    sigla = f"scale={W}:1920,crop={W}:{alto},setsar=1,fps={FPS},format=yuv420p"
    corpo = (f"pad={W}:{alto}:0:(oh-ih)/2:color={sfondo},setsar=1,fps={FPS},format=yuv420p" if verticale
             else f"setsar=1,fps={FPS},format=yuv420p")
    stereo = "aresample=48000,aformat=sample_rates=48000:channel_layouts=stereo"
    filtro = (f"[0:v]{sigla}[v0];[1:v]{corpo}[v1];[3:v]{sigla}[v2];"
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


def produci(s, social):
    """crea i due video, la copertina e i testi di un annuncio (gira in un processo a parte)"""
    from playwright.sync_api import sync_playwright
    cartella = Path(tempfile.mkdtemp())
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            post, audio, copertina = video_post(browser, s, cartella)
        finally:
            browser.close()
    v45 = monta(post, audio, s, cs.USCITA / f"{s['slot']}.mp4", verticale=False)
    v916 = monta(post, audio, s, cs.USCITA / f"{s['slot']}-reel.mp4", verticale=True)
    cop = cs.USCITA / f"{s['slot']}.jpg"
    shutil.copy(copertina, cop)
    for nome in social:
        (cs.USCITA / f"{s['slot']}-{nome}.txt").write_text(testo(s, nome), encoding="utf-8")
    shutil.rmtree(cartella, ignore_errors=True)
    cs.log("Video pronto:", v45.name, f"({durata(v45):.1f} s)")
    return s, v45, v916, cop


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

    # i video si creano 3 alla volta (il runner di GitHub ha 4 processori)
    apertura_breve()
    pronti = []
    from concurrent.futures import ProcessPoolExecutor
    with ProcessPoolExecutor(max_workers=int(os.environ.get("VIDEO_IN_PARALLELO", "3") or 3)) as pool:
        lavori = [pool.submit(produci, s, social) for s in scelte]
        for s, lavoro in zip(scelte, lavori):
            try:
                pronti.append(lavoro.result())
            except Exception as e:
                cs.log("ERRORE video", s["slot"], e)

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
