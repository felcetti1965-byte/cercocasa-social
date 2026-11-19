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
import foto_stanze
import filigrana

QUI = Path(__file__).resolve().parent
GRAFICA = QUI / "grafica"
FPS, W, H = 30, 1080, 1350
COPERTINA_MS = 2600          # da qui il post è completo (serve per la copertina di Instagram)
MAX_FOTO = 9                 # foto dell'annuncio scaricate
MIN_FOTO = 3                 # sotto questo numero l'annuncio viene saltato
MAX_FRASI = 8                # frasi dette dalla voce (una foto per frase)
APERTURA_VELOCITA = 2.5      # la sigla di apertura (8 s) dura circa 3 s
CANDIDATI = 15               # annunci di riserva per ogni tipo

SLOT = [  # (nome, tipo, città, pagina del sito)
    ("vendita-terni", "vendita", "terni", "/case-vendita/terni/"),
    ("vendita-perugia", "vendita", "perugia", "/case-vendita/perugia/"),
    ("affitto-terni", "affitto", "terni", "/case-affitto/terni/"),
    ("affitto-perugia", "affitto", "perugia", "/case-affitto/perugia/"),
    ("asta-terni", "asta", "terni", "/aste-immobiliari/terni/"),
    ("asta-perugia", "asta", "perugia", "/aste-immobiliari/perugia/"),
    # secondo post nelle categorie con più annunci (10 al giorno: limite sicuro per TikTok)
    ("vendita-terni-2", "vendita", "terni", "/case-vendita/terni/"),
    ("vendita-perugia-2", "vendita", "perugia", "/case-vendita/perugia/"),
    ("affitto-perugia-2", "affitto", "perugia", "/case-affitto/perugia/"),
    ("asta-perugia-2", "asta", "perugia", "/aste-immobiliari/perugia/"),
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
    if tipo != "asta" and re.search(r"all.asta|\basta\b", s.get("titolo", ""), re.I):
        return False          # le aste stanno nel loro post, non tra vendita e affitto
    if tipo == "asta" and s.get("data_asta"):
        try:
            if datetime.strptime(s["data_asta"], "%d/%m/%Y").date() <= date.today() + timedelta(days=2):
                return False
        except ValueError:
            s["data_asta"] = ""
    return True


def candidati(stato, solo=None, usati=None):
    """per ogni tipo e città: (nome, tipo, città, schede in ordine di preferenza, prima le case).
    solo = {slot: id}: ripropone proprio quegli annunci (già pubblicati oggi, per un altro social)"""
    if usati is None:
        usati = {p.get("id") for p in stato["pubblicati"]} - set((solo or {}).values())
    out = []
    elenchi = {}
    stessa = {}                        # più post dalla stessa pagina: si dividono gli annunci a turno
    for nome, tipo, citta, pagina in SLOT:
        stessa.setdefault(pagina, []).append(nome)
    for nome, tipo, citta, pagina in SLOT:
        try:
            if solo is not None and nome not in solo:
                continue
            if pagina not in elenchi:
                elenchi[pagina] = leggi_elenco(tipo, pagina)
            schede = [x for x in elenchi[pagina] if scheda_valida(tipo, x, usati)]
            if solo is not None:
                schede = [x for x in schede if x["id"] == solo[nome]]
        except Exception as e:
            cs.log("  elenco non leggibile", pagina, e)
            schede = []
        case = [x for x in schede if not NON_CASE.search(x["tipo_imm"] + " " + x["titolo"])]
        ordine, visti = [], set()
        for x in [x for x in case if tipo != "asta" or x.get("data_asta")] + case + schede:
            if x["id"] not in visti:
                visti.add(x["id"])
                ordine.append(x)
        gruppo = stessa[pagina]
        if solo is None and len(gruppo) > 1:
            ordine = ordine[gruppo.index(nome)::len(gruppo)]
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


def colore_del_giorno(slot=None):
    """un colore diverso per ognuno dei 6 post del giorno (e diverso da un giorno all'altro), con il testo leggibile"""
    nomi = [x[0] for x in SLOT]
    passo = nomi.index(slot) if slot in nomi else 0
    r, g, b = cs.COLORI_GIORNO[(datetime.now().timetuple().tm_yday + passo) % len(cs.COLORI_GIORNO)]
    lum = lambda c: (c / 255 / 12.92) if c <= 10 else (((c / 255) + 0.055) / 1.055) ** 2.4
    L = 0.2126 * lum(r) + 0.7152 * lum(g) + 0.0722 * lum(b)
    sul_bianco = 1.05 / (L + 0.05)
    sul_scuro = (L + 0.05) / (0.0137 + 0.05)          # #1F1F1F
    return f"#{r:02X}{g:02X}{b:02X}", ("#FFFFFF" if sul_bianco >= sul_scuro else "#1F1F1F")


def titolo_breve_asta(titolo):
    """'Villa all'asta a Orvieto, Via Nettuno snc, loc. Canale – 7 locali' -> 'Villa all'asta a Orvieto – 7 locali'"""
    base = titolo.split(",")[0].split(" – ")[0].strip()
    coda = re.search(r"\s[–-]\s*([^–,]{2,24})$", titolo)
    if coda and coda.group(1).strip() not in base:
        return f"{base} – {coda.group(1).strip()}"
    return base


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
                "price": euro(s["prezzo"]), "title": ((s.get("dettaglio") or {}).get("titolo") or f"{tipo} a {dove}"),
                "titleShort": titolo_breve_asta((s.get("dettaglio") or {}).get("titolo") or f"{tipo} a {dove}"),
                "specs": voci, "photos": foto,
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
    frasi = cs.frasi_video(a)[:min(MAX_FRASI, max(len(foto) - 1, 4))]   # con poche foto le frasi usano copertina e pagina col logo
    # ogni frase sulla foto che mostra proprio quella cosa (bagno sul bagno, cucina sulla cucina...);
    # se l'annuncio non ha quella foto: pagina neutra con il logo, mai una foto che dice altro
    abbinate = foto_stanze.abbina(frasi, foto, cartella, colore_del_giorno(s.get("slot"))[0], log=cs.log)
    pezzi = [(foto[0], "", cs.voce_apertura(a))]
    for f, fp in zip(frasi, abbinate):
        pezzi.append((fp, f, parlato(f)))
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


def foto_annuncio(s, cartella, massimo=None):
    """foto principale della scheda + le altre foto dell'annuncio (senza planimetrie e mappe), in jpg"""
    massimo = massimo or MAX_FOTO
    a = s["dettaglio"]
    indirizzi = [urljoin(cs.SITO + "/", s["foto"])] if s.get("foto") else []
    for u in a.get("foto", []):
        if u not in indirizzi and not re.search(r"mappa|planimetr|piantin", u, re.I):
            indirizzi.append(u)
    file = []
    for u in indirizzi:
        if len(file) >= massimo:
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
    try:      # via la filigrana dell'agenzia (es. TEMPOCASA al centro delle foto): attiva solo con FILIGRANA=togli
        if os.environ.get("FILIGRANA", "") == "togli":
            filigrana.pulisci_foto(file, log=cs.log)
    except Exception as e:
        cs.log("  filigrana non tolta:", e)
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
    dati["accent"], dati["onAccent"] = colore_del_giorno(s.get("slot"))
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


# ---------------------------------------------------------------- TikTok: formato virale
# Regole dai video immobiliari con più visualizzazioni: gancio scritto sul primo fotogramma (domanda),
# niente sigla iniziale, 15-25 secondi, un cambio ogni ~2 s, scritte grandi al centro (zona sicura),
# prezzo svelato alla fine (fa restare fino in fondo), cartello finale breve con codice e link in bio.
# punto forte dell'annuncio, preso dalla descrizione (in ordine di forza)
PUNTI_FORTI = [
    (r"piscin", "con piscina"), (r"vista (panoramica|mozzafiato|lago|valle|colline)|panoramic", "con vista panoramica"),
    (r"attico", "attico"), (r"giardino", "con giardino"), (r"terrazz", "con terrazzo"),
    (r"centro storico", "nel centro storico"), (r"ristrutturat|rinnovat|nuov[ao] di zecca", "appena ristrutturato"),
    (r"nuova costruzione|classe a", "nuova costruzione"), (r"indipendente", "indipendente"),
    (r"camino", "con camino"), (r"garage|box auto", "con garage"), (r"arredat", "arredato"),
    (r"balcon", "con balcone"), (r"luminos", "luminosissimo"),
]
STANZE_IT = {"bagno": "Bagno", "cucina": "Cucina", "camera": "Camera da letto", "soggiorno": "Soggiorno",
             "camino": "Soggiorno con camino", "esterno": "Esterno", "giardino": "Giardino", "terrazzo": "Terrazzo",
             "garage": "Garage", "piscina": "Piscina", "vista": "Vista", "terreno": "Terreno", "mansarda": "Mansarda",
             "cantina": "Cantina"}
TIKTOK_MIN_FOTO, TIKTOK_FOTO_TOP, TIKTOK_MAX_FOTO = 10, 20, 20


def punto_forte(a):
    testo = " ".join([a.get("titolo", ""), a.get("descrizione", ""), " ".join(a.get("punti", []))]).lower()
    for rx, frase in PUNTI_FORTI:
        if re.search(rx, testo):
            return frase
    return ""


# frasi della descrizione da NON leggere (telefoni, agenzia, codici, link)
NON_LEGGERE = re.compile(r"www\.|@|https?:|\btel\b|telefon|cell\.?\s*\d|whatsapp|chiama|mediazione|provvigion|"
                         r"\brif\b|riferimento|codice|buona fede|\biva\b|\d{3}[\s.]?\d{3}[\s.]?\d{3,4}", re.I)
VOCE_MAX_CARATTERI = int(os.environ.get("VOCE_TIKTOK_MAX", "2600"))   # circa 3 minuti di voce


def s_agenzia(nome):
    return bool(re.search(r"agenzia|immobiliar|studio|real estate|group|tecnocasa|tempocasa|gabetti|remax|re/max", nome, re.I))


def frasi_annuncio(a):
    """titolo dell'annuncio + tutte le frasi della descrizione, come le legge la voce"""
    titolo = re.sub(r"\s+", " ", a.get("titolo", "")).strip(" .")
    pezzi = [(titolo.capitalize() if titolo.isupper() else titolo) + "."] if titolo else []
    agenzia = re.sub(r"\s+", " ", a.get("agenzia", "")).strip(" .")
    if agenzia:         # subito dopo il titolo: chi lo vende
        if agenzia.isupper():
            agenzia = agenzia.title()
        pezzi.append(f"Lo propone {agenzia}." if s_agenzia(agenzia) else f"Lo propone l'agenzia {agenzia}.")
    for f in re.split(r"(?<=[.!?;])\s+|\s*\n+\s*|\s*•\s*", a.get("descrizione", "")):
        f = re.sub(r"\s+", " ", f).strip(" -–*•")
        f = re.sub(r"\b(mq|m2)\b\.?|m²", "metri quadri", f, flags=re.I)
        if len(f.split()) < 2 or NON_LEGGERE.search(f):
            continue
        if f.isupper():
            f = f.capitalize()
        pezzi.append(f if f.endswith((".", "!", "?", ";", ":")) else f + ".")
    out, n = [], 0
    for p in pezzi:
        if n + len(p) > VOCE_MAX_CARATTERI:
            break
        out.append(p)
        n += len(p) + 1
    return out


TIKTOK_PARLATO_MAX_MS = int(os.environ.get("TIKTOK_PARLATO_MAX_MS", "46000"))   # + prezzo + chiusura = 1 minuto


def frasi_tiktok(a):
    """cosa dice la voce nel video TikTok: "<agenzia> propone <titolo>", poi solo i dati importanti
    (zona, metri quadri, camere, bagni, piano, giardino, garage...), una frase breve per volta"""
    titolo = re.sub(r"\s+", " ", a.get("titolo", "")).strip(" .")
    if titolo.isupper():
        titolo = titolo.capitalize()
    agenzia = re.sub(r"\s+", " ", a.get("agenzia", "")).strip(" .")
    if agenzia.isupper():
        agenzia = agenzia.title()
    frasi = [f"{agenzia} propone {titolo[:1].lower() + titolo[1:]}." if agenzia else titolo + "."]
    gia = titolo.lower()
    for f in cs.frasi_video(a):
        chiave = [w for w in re.findall(r"[a-zà-ù]{5,}", f.lower()) if w not in ("impianto", "metri", "quadrati")]
        if chiave and all(w[:-1] in gia for w in chiave):     # già detto nel titolo
            continue
        frasi.append(f + ".")
    if len(frasi) < 6:                                    # pochi dati: qualche frase breve della descrizione
        for f in frasi_annuncio(a)[1:]:
            if f.startswith(("Lo propone",)) or len(f) > 90 or re.match(r"(propon|vendes|offriam|in vendita)", f, re.I):
                continue
            frasi.append(f)
            if len(frasi) >= 8:
                break
    return frasi


def testo_annuncio(a):
    return " ".join(frasi_annuncio(a))


PAROLE_LEGATE = {"di", "e", "ed", "con", "a", "al", "alla", "il", "lo", "la", "le", "i", "gli", "un", "una", "in",
                 "da", "per", "su", "del", "della", "dei", "delle", "nel", "nella", "o", "che", "è"}


def spezza(frase, max_car=22, max_parole=4):
    """la frase in pezzi brevi da sottotitolo (3-4 parole), senza lasciare 'di', 'e', 'con' in fondo"""
    pezzi, cur = [], []
    for w in frase.rstrip(".;:").split():
        if cur and (len(" ".join(cur + [w])) > max_car or len(cur) >= max_parole):
            resto = []
            while len(cur) > 1 and cur[-1].lower().strip(",") in PAROLE_LEGATE:
                resto.insert(0, cur.pop())
            pezzi.append(" ".join(cur))
            cur = resto
        cur.append(w)
    if cur:
        pezzi.append(" ".join(cur))
    return [p.strip(" ,") for p in pezzi if p.strip(" ,")]


def sincronizza(d, s, cartella):
    """voce, sottotitoli e foto insieme: una voce per ogni frase (titolo + descrizione), i sottotitoli
    sono le parole dette in quel momento, e la foto cambia quando la voce parla di una stanza
    (cucina -> foto della cucina, bagni -> foto del bagno). Restituisce (dati del video, voci)."""
    vel = os.environ.get("VOCE_TIKTOK_VELOCITA", "+2%")
    tracce, t = [], 250
    for k, f in enumerate(frasi_tiktok(s["dettaglio"])):
        if t > TIKTOK_PARLATO_MAX_MS - 1500:
            break
        mp3 = cartella / f"voce-f{k}.mp3"
        dur = cs.crea_voce(parlato(f), mp3, voce="umana", velocita=vel)
        if dur and t + dur * 1000 > TIKTOK_PARLATO_MAX_MS and k > 0:
            break
        if dur:
            tracce.append((f, mp3, t, int(dur * 1000)))
            t += int(dur * 1000) + 160
    if len(tracce) < 2:
        return d, [(mp3, st) for _, mp3, st, _ in tracce]
    cat = d.get("_cat", {})
    giro = [sc["photo"] for sc in d["scenes"][1:]] or [d["scenes"][0]["photo"]]
    volte = {f: 0 for f in giro}
    copertina = d["scenes"][0]["photo"]
    fine_gancio = max(2600, tracce[0][2] + tracce[0][3] + 80)
    scene, caps = [{"photo": copertina, "start": 0, "end": fine_gancio, "chip": ""}], []
    stato = {"foto": None, "da": fine_gancio}

    def cambia(foto, quando):
        quando = max(int(quando), fine_gancio)
        if stato["foto"] is not None:
            if quando - stato["da"] < 600:          # foto rimasta troppo poco: la sostituisco
                scene[-1]["photo"] = foto
                stato["foto"] = foto
                volte[foto] = volte.get(foto, 0) + 1
                return
            scene[-1]["end"] = quando
        scene.append({"photo": foto, "start": quando, "end": quando, "chip": ""})
        stato["foto"], stato["da"] = foto, quando
        volte[foto] = volte.get(foto, 0) + 1

    def stanze_dette(p):
        """le stanze nominate in un pezzo di frase, in ordine (il camino, se non c'è la foto, è il soggiorno)"""
        out = [c for rx, c in foto_stanze.FRASI_FOTO if re.search(rx, p.lower()) and c != "nessuna"]
        if "camino" in out:
            out.append("soggiorno")
        return out

    tutte = " ".join(f for f, *_ in tracce[1:])
    nominate = set(stanze_dette(tutte))

    def preferenza(f):
        c = cat.get(f, "stanza")
        if c == "documento":
            return 999
        base = foto_stanze.GENERICHE_PREFERITE.index(c) if c in foto_stanze.GENERICHE_PREFERITE else 50
        return base + (100 if c in nominate else 0)     # le stanze nominate dalla voce le tengo per quando le nomina

    def della_stanza(c):
        cand = [f for f in giro if cat.get(f) == c]
        if not cand:
            return None
        if stato["foto"] in cand:
            return stato["foto"]
        return min(cand, key=lambda f: (volte.get(f, 0), giro.index(f)))

    def generica():
        prima = [f for f in giro if f != stato["foto"] and preferenza(f) < 999] or giro
        return min(prima, key=lambda f: (volte.get(f, 0), preferenza(f), giro.index(f)))

    for f, mp3, st, dur in tracce[1:]:
        pezzi = spezza(f)
        tot = sum(len(p) + 1 for p in pezzi)
        x = st
        stanze_frase = stanze_dette(f)
        for j, p in enumerate(pezzi):
            cd = dur * (len(p) + 1) / tot
            caps.append({"start": int(x), "end": int(x + cd), "text": p})
            voluta = next((v for v in map(della_stanza, stanze_dette(p) or (stanze_frase if j == 0 else [])) if v), None)
            if voluta and voluta != stato["foto"]:
                cambia(voluta, x)
            elif j == 0 and not voluta:                     # ogni frase nuova: foto nuova
                cambia(generica(), x)
            elif stato["foto"] is None:
                cambia(generica(), x)
            elif x - stato["da"] > 3200 and not voluta:
                # si parla ancora della stessa stanza: un'altra foto di quella stanza, se c'è; se no una generica
                altra = [g for g in giro if g != stato["foto"] and cat.get(g) == cat.get(stato["foto"])
                         and cat.get(g) in STANZE_IT and volte.get(g, 0) == 0]
                cambia(altra[0] if altra else generica(), x)
            x += cd
    fine_tour = tracce[-1][2] + tracce[-1][3] + 300
    scene[-1]["end"] = fine_tour
    voci = [(mp3, st) for _, mp3, st, _ in tracce]
    durata_prezzo = 4000
    testo_prezzo = d["voci"][-1][0] if d.get("voci") else ""
    if testo_prezzo:
        mp3 = cartella / "voce-prezzo.mp3"
        dp = cs.crea_voce(parlato(testo_prezzo), mp3, voce="umana", velocita=vel)
        if dp:
            voci.append((mp3, fine_tour + 200))
            durata_prezzo = max(4000, int(dp * 1000) + 700)
    d["scenes"], d["caps"] = scene, caps
    d["reveal"] = {"start": fine_tour, "end": fine_tour + durata_prezzo}
    d["total"] = fine_tour + durata_prezzo
    cs.log(f"  TikTok: {len(tracce)} frasi, {len(caps)} sottotitoli, {len(scene) - 1} foto, {d['total'] / 1000:.0f} s")
    return d, voci


def dati_tiktok(s, foto, cartella):
    """video "tour della casa" (il formato immobiliare con più visualizzazioni): gancio con il punto forte
    preso dalla descrizione, tutte le foto (fino a 20) con il nome della stanza o la caratteristica giusta,
    prezzo chiaro alla fine. Niente indovinelli."""
    a = s["dettaglio"]
    base = dati_post(s, foto)
    dove = (s.get("zona") or s["citta"]).title() if s["tipo"] != "asta" else base["city"].title()
    if len(dove) > 18:
        dove = s["citta"].title()
    tipo = tipo_bello(s["tipo_imm"])
    forte = punto_forte(a)
    if forte and (dove.lower() in forte or forte.split()[-1] in dove.lower()):
        dove = s["citta"].title()            # niente "nel centro storico a Centro Storico"
    giorno = datetime.now().timetuple().tm_yday + sum(map(ord, s.get("slot", "")))
    titolo = re.sub(r"\s+", " ", a.get("titolo", "")).strip(" .").upper()
    if titolo:          # all'inizio solo il titolo dell'annuncio (es. QUADRILOCALE VENDITA PERUGIA)
        righe, cur = [], ""
        for w in titolo.split():
            if cur and len(cur) + 1 + len(w) > 15:
                righe.append(cur)
                cur = w
            else:
                cur = (cur + " " + w).strip()
        righe.append(cur)
        hook = [{"t": r} for r in righe[:5]]
        hook[-1]["hl"] = True
    elif s["tipo"] == "asta":
        hook = [{"t": f"{tipo} all'asta"}, {"t": f"a {dove}"}, {"t": forte or "Tour completo", "hl": True}]
    elif giorno % 2:
        hook = [{"t": "POV: entri nella"}, {"t": "tua nuova casa"}, {"t": f"{forte or ''} a {dove}".strip(), "hl": True}]
    else:
        hook = [{"t": tipo}, {"t": forte or f"a {dove}"}, {"t": (f"a {dove}" if forte else "Tour completo"), "hl": True}]
    # ogni foto: la caratteristica giusta (foto della stanza giusta) o il nome della stanza; planimetrie escluse
    info = foto_stanze.classifica(foto)
    frasi = [f for f in cs.frasi_video(a) if len(f) <= 26]
    abbinate = foto_stanze.abbina(frasi, foto, cartella, colore_del_giorno(s.get("slot"))[0], log=cs.log)
    chip_di = {}
    for fr, fp in zip(frasi, abbinate):
        if Path(fp).name != "neutra.jpg" and str(fp) not in chip_di:
            chip_di[str(fp)] = fr
    dati_generici = [t for _, t in base.get("specs", [])]
    t, scene = 2600, [{"photo": str(foto[0]), "start": 0, "end": 2600, "chip": ""}]
    _numero = lambda c: (re.search(r"\d[\d.,]*", c or "") or [None])[0]
    visti = {_numero(c) for c in chip_di.values() if _numero(c)}
    for f in foto[1:TIKTOK_MAX_FOTO]:
        cat = info.get(str(f), ("",))[0]
        if cat == "documento":
            continue
        chip = chip_di.get(str(f)) or STANZE_IT.get(cat, "")
        while not chip and dati_generici:
            chip = dati_generici.pop(0)
            if _numero(chip) and _numero(chip) in visti:      # niente "139 m²" ripetuto due volte
                chip = ""
        if _numero(chip):
            visti.add(_numero(chip))
        scene.append({"photo": str(f), "start": t, "end": t + 1500, "chip": chip})
        t += 1500
    reveal = {"start": t, "end": t + 3000}
    endcard = {"start": 10 ** 9}
    # voce: gancio all'inizio, le caratteristiche durante il tour, il prezzo quando compare
    prezzo_detto = base["price"].replace("€", "").strip() + " euro" + (" al mese" if s["tipo"] == "affitto" else "")
    if s["tipo"] == "asta":
        fine = f"La base d'asta parte da {prezzo_detto}. Perizia e contatti nel link in bio."
    elif giorno % 2:
        fine = f"Il prezzo? {prezzo_detto}. Tutte le foto e i contatti nel link in bio."
    else:
        fine = f"Prezzo: {prezzo_detto}. Tutte le foto e i contatti nel link in bio."
    # voce: il titolo dell'annuncio, poi tutto il testo della descrizione, poi il prezzo quando compare
    voci = [(testo_annuncio(a), 250), (fine, None)]
    etichetta = {"vendita": "IN VENDITA", "affitto": "IN AFFITTO", "asta": "ALL'ASTA"}[s["tipo"]]
    prezzo = base["price"] + (" al mese" if s["tipo"] == "affitto" else "")
    accent, on = colore_del_giorno(s.get("slot"))
    return {"scenes": scene, "hook": hook, "tag": f"TOUR · {etichetta} · {base['city']}",
            "price": ("da " if s["tipo"] == "asta" else "") + prezzo,
            "revealQ": "Base d'asta" if s["tipo"] == "asta" else ("Affitto" if s["tipo"] == "affitto" else "Prezzo"),
            "revealS": "Tutte le foto e i contatti: link in bio", "reveal": reveal, "endcard": endcard,
            "code": str(s["id"]), "accent": accent, "onAccent": on, "total": t + 3000, "voci": voci,
            "_cat": {str(f): c[0] for f, c in info.items()}}


# ---------------------------------------------------------------- TikTok: stile "home tour" (come @bilocale.it)
# Foto in ordine di visita (soggiorno, cucina, balcone, corridoio, camere, bagni...), movimento lento
# da telecamera, dissolvenza morbida, niente voce: musica, logo Cercocasa e una scritta per foto presa
# dal testo dell'annuncio che parla proprio di quella stanza.
ORDINE_TOUR = ["soggiorno", "camino", "cucina", "terrazzo", "stanza", "camera", "bagno", "mansarda",
               "cantina", "garage", "giardino", "piscina", "terreno", "vista", "esterno"]
PAROLE_STANZA = {
    "soggiorno": r"soggiorno|salone|salotto|living|zona giorno|open space",
    "camino": r"camino",
    "cucina": r"cucin|angolo cottura",
    "terrazzo": r"terrazz|balcon|loggia",
    "stanza": r"ingresso|disimpegno|corridoio|ripostiglio|scala|studio",
    "camera": r"camer|matrimonial|stanza da letto|zona notte",
    "bagno": r"bagn|servizi|doccia|vasca",
    "mansarda": r"mansard|soffitta|sottotetto",
    "cantina": r"cantin|taverna|seminterrato",
    "garage": r"garage|box|posto auto|autorimessa",
    "giardino": r"giardin|corte|resede|prato",
    "piscina": r"piscin",
    "terreno": r"terren|uliv|oliv",
    "vista": r"vista|panoram",
    "esterno": r"facciata|palazzin|stabile|edificio|condominio|immobile|villa|casale|zona",
}
TOUR_PASSO_MS = int(os.environ.get("TIKTOK_PASSO_MS", "2400"))
TOUR_MAX_FOTO = int(os.environ.get("TIKTOK_TOUR_FOTO", "16"))


def pezzi_testo(a):
    """il testo dell'annuncio a pezzi brevi (frasi spezzate su virgole e 'e'), puliti"""
    out = []
    for f in re.split(r"(?<=[.!?;])\s+|\s*\n+\s*|\s*•\s*", a.get("descrizione", "")):
        if NON_LEGGERE.search(f) or re.search(r"€|\beuro\b|prezzo|trattabil", f, re.I):
            continue
        for p in re.split(r",\s*|\s+-\s+|:\s*|\s+e\s+(?=(?:un|una|uno|due|tre|quattro|cinque|\d+)\s)", f):
            p = re.sub(r"\s+", " ", p).strip(" .;-–*")
            p = re.sub(r"^(e|ed|con|oltre a|inoltre|poi|infine|il tutto)\s+", "", p, flags=re.I)
            p = re.sub(r"\b(mq|m2)\b\.?|m²", "m²", p, flags=re.I)
            p = re.sub(r"^(proponiamo|vendesi|si vende|in vendita|vendiamo|offriamo|presentiamo)\s+(in vendita\s+)?",
                       "", p, flags=re.I)
            if 2 <= len(p.split()) <= 9 and len(p) <= 48:
                out.append(p[:1].upper() + p[1:])
    return list(dict.fromkeys(out))


def dati_tour(s, foto, cartella):
    a = s["dettaglio"]
    base = dati_post(s, foto)
    info = foto_stanze.classifica(foto)
    cat = {str(f): info.get(str(f), ("stanza",))[0] for f in foto}
    copertina = foto[0]
    resto = [f for f in foto[1:] if cat[str(f)] != "documento"]
    # ordine di visita: prima la copertina, poi le stanze nell'ordine di un sopralluogo
    resto.sort(key=lambda f: (ORDINE_TOUR.index(cat[str(f)]) if cat[str(f)] in ORDINE_TOUR else 50,
                              foto.index(f)))
    giro = [copertina] + resto[:TOUR_MAX_FOTO - 1]
    pezzi = pezzi_testo(a)
    usati = set()
    dati = {"camera": None, "bagno": None}
    if a.get("camere"):
        dati["camera"] = "Una camera da letto" if a["camere"] == "1" else f"{a['camere']} camere da letto"
    if a.get("bagni"):
        dati["bagno"] = "Un bagno" if a["bagni"] == "1" else f"{a['bagni']} bagni"
    generici = [f for f in cs.frasi_video(a)]
    if a.get("mq"):
        generici = [f"{a['mq']} m²"] + [g for g in generici if "metri" not in g]

    def frase_per(c):
        rx = PAROLE_STANZA.get(c)
        if rx:
            for p in pezzi:
                if p not in usati and re.search(rx, p, re.I):
                    usati.add(p)
                    return p
        d = dati.get(c)
        if d:
            dati[c] = None
            return d
        return ""

    titolo = re.sub(r"\s+", " ", a.get("titolo", "")).strip(" .")
    scene, t, gia_stanza = [], 0, set()
    for i, f in enumerate(giro):
        c = cat[str(f)]
        if i == 0:
            chip = titolo.capitalize() if titolo.isupper() else titolo
        else:
            chip = frase_per(c)
            if not chip and c not in gia_stanza and c in ("esterno", "stanza", "vista") and generici:
                chip = generici.pop(0)
        gia_stanza.add(c)
        scene.append({"photo": str(f), "start": t, "end": t + TOUR_PASSO_MS, "chip": chip})
        t += TOUR_PASSO_MS
    # ultima foto: il prezzo, scritto come gli altri sottotitoli
    prezzo = base["price"] + (" al mese" if s["tipo"] == "affitto" else "")
    scene.append({"photo": str(copertina), "start": t, "end": t + 3200,
                  "chip": ("Base d'asta " if s["tipo"] == "asta" else "") + prezzo + "\nInfo: link in bio"})
    t += 3200
    accent, on = colore_del_giorno(s.get("slot"))
    cs.log("  TikTok tour: " + " | ".join(f"{cat.get(sc['photo'], '?')}: {sc['chip']}" for sc in scene))
    return {"stile": "tour", "scenes": scene, "hook": [], "tag": "", "price": "", "reveal": {"start": 10 ** 9, "end": 10 ** 9},
            "endcard": {"start": 10 ** 9}, "code": str(s["id"]), "accent": accent, "onAccent": on,
            "total": t, "voci": []}


# ---------------------------------------------------------------- video "editoriale" (come il video Trebbi)
# Scene: copertina a tutto schermo con il titolo, poi schede eleganti (fondo crema o verde) con le foto
# di ogni stanza e il testo dell'annuncio che ne parla, planimetrie, prezzo con i punti forti, chiusura.
# Logo Cercocasa sempre in alto al centro. Stessa grafica in verticale (TikTok, Instagram) e quadrata.
NUMERI = {1: "Una", 2: "Due", 3: "Tre", 4: "Quattro", 5: "Cinque", 6: "Sei", 7: "Sette", 8: "Otto"}
NOMI_STANZA = {"soggiorno": "Il soggiorno", "camino": "Il soggiorno con camino", "cucina": "La cucina",
               "terrazzo": "Il terrazzo", "stanza": "Gli interni", "camera": "Le camere", "bagno": "Il bagno",
               "mansarda": "La mansarda", "cantina": "La cantina", "garage": "Il garage", "giardino": "Il giardino",
               "piscina": "La piscina", "terreno": "Il terreno", "vista": "La vista", "esterno": "L'esterno"}
EDIT_SCENA_MS = int(os.environ.get("EDIT_SCENA_MS", "3600"))
EDIT_MAX_SCHEDE = int(os.environ.get("EDIT_MAX_SCHEDE", "7"))


def _bel_titolo(t):
    t = re.sub(r"\s+", " ", t or "").strip(" .")
    if t.isupper():
        t = t.capitalize()
        for citta in ("perugia", "terni", "foligno", "spoleto", "assisi", "orvieto", "todi", "gubbio",
                      "narni", "amelia", "corciano", "bastia", "marsciano", "umbertide", "deruta", "magione"):
            t = re.sub(rf"\b{citta}\b", citta.title(), t)
    return t


def dati_editoriale(s, foto, cartella, W=1080, H=1920):
    a = s["dettaglio"]
    base = dati_post(s, foto)
    info = foto_stanze.classifica(foto)
    cat = {str(f): info.get(str(f), ("stanza",))[0] for f in foto}
    tipo = tipo_bello(s["tipo_imm"])
    zona = (s.get("zona") or "").strip()
    citta = s["citta"].title() if s["tipo"] != "asta" else base["city"].title()
    luogo = f"{citta} · {zona.title()}" if zona and zona.lower() != citta.lower() else citta
    pezzi, usati = pezzi_testo(a), set()

    def frase(c, max_car=60):
        rx = PAROLE_STANZA.get(c)
        for p in pezzi:
            conta = re.match(r"(un|una|uno|due|tre|quattro|cinque|\d+)\s+(bagn|camer|servizi)", p, re.I)
            if p not in usati and len(p) <= max_car and not conta and (rx is None or re.search(rx, p, re.I)):
                usati.add(p)
                return p
        return ""

    gruppi = {}
    for f in foto[1:]:
        gruppi.setdefault(cat[str(f)], []).append(str(f))
    scene = []
    contratto = {"vendita": "In vendita", "affitto": "In affitto", "asta": "All'asta"}[s["tipo"]]
    # 1) copertina
    scene.append({"kind": "full", "photos": [str(foto[0])], "eye": f"{contratto} · {tipo}",
                  "title": _bel_titolo(a.get("titolo")) or f"{tipo} a {citta}", "sub": luogo})
    # 2) seconda foto a tutto schermo: metri quadri e la frase generale dell'annuncio
    seconda = (gruppi.get("esterno") or gruppi.get("vista") or gruppi.get("soggiorno") or [None])[0]
    if seconda:
        for g in gruppi.values():
            if seconda in g:
                g.remove(seconda)
        titolo2 = f"{tipo}, {a['mq']} m²" if a.get("mq") else tipo
        generale = next((p for p in pezzi if not any(re.search(rx, p, re.I) for c, rx in PAROLE_STANZA.items()
                                                      if c != "esterno")), "")
        usati.add(generale)
        scene.append({"kind": "full", "photos": [seconda], "eye": _bel_titolo(a.get("titolo"))[:44],
                      "title": titolo2, "sub": generale})
    # 3) una scheda per stanza, in ordine di visita
    schede = 0
    for c in ORDINE_TOUR:
        if schede >= EDIT_MAX_SCHEDE or not gruppi.get(c):
            continue
        ph = gruppi[c][:3]
        titolo = NOMI_STANZA.get(c, c.title())
        if c == "camera" and a.get("camere"):
            n = int(a["camere"]) if a["camere"].isdigit() else 0
            titolo = "Una camera" if n == 1 else f"{NUMERI.get(n, a['camere'])} camere" if n else titolo
        if c == "bagno" and a.get("bagni"):
            n = int(a["bagni"]) if a["bagni"].isdigit() else 0
            titolo = "Un bagno" if n == 1 else f"{NUMERI.get(n, a['bagni'])} bagni" if n else titolo
        testo = frase(c)
        if testo and len(testo) <= 26 and c not in ("camera", "bagno"):
            titolo, testo = testo, NOMI_STANZA.get(c, "")[3:] if NOMI_STANZA.get(c, "").startswith(("Il ", "La ")) else ""
        kind = "full" if (c == "soggiorno" and len(ph) == 1) else "card"
        scene.append({"kind": kind, "photos": ph, "title": titolo, "sub": testo, "verde": schede % 3 == 2})
        schede += 1
    # 4) planimetrie
    if gruppi.get("documento"):
        scene.append({"kind": "card", "photos": gruppi["documento"][:4], "title": "Le planimetrie",
                      "sub": f"{a['mq']} m²" if a.get("mq") else ""})
    # 5) prezzo e punti forti
    prezzo = base["price"] + (" al mese" if s["tipo"] == "affitto" else "")
    punti = [f for f in cs.frasi_video(a) if "metri" not in f and not f.startswith("Zona")][:5]
    scene.append({"kind": "card", "verde": True, "photos": [str(foto[0])],
                  "eye": "Base d'asta" if s["tipo"] == "asta" else "Prezzo", "title": prezzo, "list": punti})
    # 6) chiusura con i contatti del portale
    agenzia = re.sub(r"\s+", " ", a.get("agenzia", "")).strip()
    scene.append({"kind": "fine", "photos": [], "eye": "Prenota una visita", "title": agenzia.title() if agenzia.isupper() else agenzia,
                  "price": f"Codice {s['id']}", "sub": "Tutte le foto e i contatti: link in bio"})
    t = 0
    for sc in scene:
        lung = 4200 if sc["kind"] == "fine" else EDIT_SCENA_MS + (600 if sc.get("list") else 0)
        sc["start"], sc["end"] = t, t + lung
        t += lung
    cs.log("  video editoriale: " + " | ".join(f"{sc['kind']}:{sc.get('title')}" for sc in scene))
    return {"W": W, "H": H, "place": luogo, "scenes": scene, "total": t}


def video_editoriale(browser, s, cartella, foto, W=1080, H=1920, nome="tiktok"):
    """il video nello stile editoriale; solo musica"""
    foto = foto_senza_filigrana(foto, cartella)
    d = dati_editoriale(s, foto, cartella, W, H)
    fotogrammi = cartella / f"fotogrammi-{nome}"
    fotogrammi.mkdir()
    pagina = browser.new_page(viewport={"width": W, "height": H})
    pagina.add_init_script("window.POST = " + json.dumps(d) + ";")
    pagina.goto("file://" + str(GRAFICA / "editoriale.html"))
    pagina.evaluate("document.fonts.ready")
    pagina.wait_for_timeout(600)
    for i in range(d["total"] * FPS // 1000):
        pagina.evaluate(f"window.seek({i * 1000 / FPS})")
        pagina.screenshot(path=str(fotogrammi / f"{i:04d}.jpg"), type="jpeg", quality=90)
    pagina.close()
    muto = cartella / f"{nome}-muto.mp4"
    cs.ff("-framerate", str(FPS), "-i", fotogrammi / "%04d.jpg", "-c:v", "libx264", "-preset", "veryfast",
          "-crf", "19", "-pix_fmt", "yuv420p", muto)
    shutil.rmtree(fotogrammi, ignore_errors=True)
    out = cs.USCITA / f"{s['slot']}-{nome}.mp4"
    audio = audio_post([], d["total"], cartella)
    cs.ff("-i", muto, "-i", audio, "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-shortest",
          "-movflags", "+faststart", out)
    return out


def foto_senza_filigrana(foto, cartella):
    """copie delle foto senza la filigrana dell'agenzia (solo per TikTok); se non riesce, le foto originali"""
    if os.environ.get("FILIGRANA_TIKTOK", "si") == "no":
        return foto
    dir_ = cartella / "senza-filigrana"
    dir_.mkdir(exist_ok=True)
    copie = []
    for f in foto:
        c = dir_ / Path(f).name
        shutil.copy(f, c)
        copie.append(c)
    try:
        if filigrana.pulisci_foto(copie, log=cs.log):
            return copie
    except Exception as e:
        cs.log("  TikTok: filigrana non tolta:", e)
    return foto


def video_tiktok(browser, s, cartella, foto):
    """video TikTok virale: solo musica (si guarda spesso senza audio), scritte grandi, prezzo alla fine,
    logo piccolo in alto a destra, chiusura animata Cercocasa"""
    stile = os.environ.get("TIKTOK_STILE", "gabbia")
    if stile == "gabbia":       # stessa gabbia dei post Facebook/Instagram, in verticale
        foto = foto_senza_filigrana(foto, cartella)
        _, reel, audio, _, _ = video_post(browser, s, cartella, foto, con_facebook=False)
        return monta(reel, audio, s, cs.USCITA / f"{s['slot']}-tiktok.mp4", verticale=True)
    if stile == "editoriale":
        return video_editoriale(browser, s, cartella, foto, 1080, 1920, "tiktok")
    foto = foto_senza_filigrana(foto, cartella)
    voci = []
    if stile == "tour":      # come il video di riferimento: musica, logo, scritte
        d = dati_tour(s, foto, cartella)
    else:
        d = dati_tiktok(s, foto, cartella)
        if os.environ.get("VOCE_TIKTOK_ATTIVA", "si") != "no":
            d, voci = sincronizza(d, s, cartella)
    fotogrammi = cartella / "fotogrammi-tiktok"
    fotogrammi.mkdir()
    pagina = browser.new_page(viewport={"width": W, "height": 1920})
    pagina.add_init_script("window.POST = " + json.dumps(d) + ";")
    pagina.goto("file://" + str(GRAFICA / "tiktok.html"))
    pagina.evaluate("document.fonts.ready")
    pagina.wait_for_timeout(500)
    for i in range(d["total"] * FPS // 1000):
        pagina.evaluate(f"window.seek({i * 1000 / FPS})")
        pagina.screenshot(path=str(fotogrammi / f"{i:04d}.jpg"), type="jpeg", quality=90)
    pagina.close()
    muto = cartella / "tiktok-muto.mp4"
    cs.ff("-framerate", str(FPS), "-i", fotogrammi / "%04d.jpg", "-c:v", "libx264", "-preset", "veryfast",
          "-crf", "19", "-pix_fmt", "yuv420p", muto)
    shutil.rmtree(fotogrammi, ignore_errors=True)
    chiusura = cs.SIGLE / "chiusura-tiktok.mp4"
    out = cs.USCITA / f"{s['slot']}-tiktok.mp4"
    if chiusura.exists():
        coda = int(durata(chiusura) * 1000)
        audio = audio_post(voci, d["total"] + coda, cartella)
        cs.ff("-i", muto, "-i", chiusura, "-i", audio, "-filter_complex",
              f"[0:v]setsar=1,fps={FPS},format=yuv420p[a];[1:v]scale={W}:1920,setsar=1,fps={FPS},format=yuv420p[b];"
              "[a][b]concat=n=2:v=1:a=0[v]",
              "-map", "[v]", "-map", "2:a", "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
              "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", out)
    else:
        audio = audio_post(voci, d["total"], cartella)
        cs.ff("-i", muto, "-i", audio, "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-shortest",
              "-movflags", "+faststart", out)
    return out


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


def con_copertina_iniziale(video, immagine):
    """video per TikTok: la bozza prende come copertina il primo fotogramma, quindi metto all'inizio
    mezzo secondo con la copertina dell'annuncio (foto, prezzo, titolo) prima della sigla"""
    uscita = Path(video).with_name(Path(video).stem + "-tiktok.mp4")
    cs.ff("-loop", "1", "-t", "0.5", "-i", immagine, "-f", "lavfi", "-t", "0.5",
          "-i", "anullsrc=channel_layout=stereo:sample_rate=48000", "-i", video,
          "-filter_complex",
          f"[0:v]scale={W}:1920,setsar=1,fps={FPS},format=yuv420p[c];"
          f"[2:v]scale={W}:1920,setsar=1,fps={FPS},format=yuv420p[v];"
          "[2:a]aresample=48000,aformat=sample_rates=48000:channel_layouts=stereo[a];"
          "[c][1:a][v][a]concat=n=2:v=1:a=1[vo][ao]",
          "-map", "[vo]", "-map", "[ao]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
          "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", uscita)
    return uscita


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
def tempo_copertina():
    """millisecondo del video in cui c'è la copertina dell'annuncio (dopo la sigla iniziale)"""
    return int((durata(apertura_breve()) * 1000) + COPERTINA_MS + 400)


def pubblica_instagram_reel(video, testo_ig):
    """come cs.pubblica_instagram, ma con la copertina sul post (non sul primo fotogramma della sigla)"""
    offset = tempo_copertina()
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
    """prova gli annunci in ordine finché uno ha almeno 3 foto; se nessuno ce l'ha, usa quello con più foto
    (i 6 post devono uscire sempre). Crea i due video, copertina e testi"""
    from playwright.sync_api import sync_playwright
    pochi = []                                  # (numero di foto, scheda) degli annunci con meno di 3 foto
    giro = list(schede)
    secondo = False
    while giro:
        scheda = giro.pop(0)
        cartella = Path(tempfile.mkdtemp())
        try:
            s = dict(scheda, slot=nome, tipo=tipo, citta=citta)
            s["dettaglio"] = cs.leggi_annuncio(s["id"])
            foto = foto_annuncio(s, cartella)
            if not foto or (len(foto) < MIN_FOTO and not secondo):
                cs.log(f"  {nome}: annuncio {s['id']} con {len(foto)} foto, passo al successivo")
                if foto:
                    pochi.append((len(foto), scheda))
                if not giro and pochi and not secondo:
                    # nessuno con 3 foto: riprovo con quello che ne ha di più (le frasi senza foto vanno sulla pagina col logo)
                    secondo = True
                    giro = [x for _, x in sorted(pochi, key=lambda t: -t[0])]
                    cs.log(f"  {nome}: nessun annuncio con {MIN_FOTO} foto, uso quello con più foto")
                continue
            a = s["dettaglio"]
            cs.log(f"{nome}: {s['id']} – {a['titolo']} – {a['prezzo']} – {a['agenzia']}")
            with sync_playwright() as p:
                browser = p.chromium.launch()
                try:
                    post45, post916, audio, copertina, cop916 = video_post(browser, s, cartella, foto,
                                                                           con_facebook="facebook" in social)
                    if "tiktok" in social and os.environ.get("TIKTOK_VIRALE", "si") != "no":
                        try:     # versione TikTok virale: gancio, ritmo veloce, prezzo svelato alla fine
                            video_tiktok(browser, s, cartella, foto)
                        except Exception as e:
                            cs.log("  TikTok virale non creato, uso il reel:", e)
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


def produci_tiktok(nome, tipo, citta, schede):
    """TikTok "tour": annuncio con almeno 20 foto (se non c'è, almeno 10), video lungo con tutte le foto"""
    from playwright.sync_api import sync_playwright
    letti = []
    for scheda in schede[:30]:
        try:
            d = cs.leggi_annuncio(scheda["id"])
            if tipo != "asta" and re.search(r"all.asta|\basta\b|dimorama|tribunale|esecuzion", 
                                            d.get("titolo", "") + " " + d.get("agenzia", ""), re.I):
                continue        # niente aste nei video di vendita e affitto
            n = len([u for u in d.get("foto", []) if not re.search(r"mappa|planimetr|piantin", u, re.I)])
            letti.append((n, scheda, d))
            if n >= TIKTOK_FOTO_TOP:
                break
        except Exception as e:
            cs.log(f"  {nome} TikTok: annuncio {scheda.get('id')} non letto:", e)
    for soglia in (TIKTOK_FOTO_TOP, TIKTOK_MIN_FOTO):
        for n, scheda, d in sorted(letti, key=lambda x: -x[0]):
            if n < soglia:
                continue
            cartella = Path(tempfile.mkdtemp())
            try:
                s = dict(scheda, slot=nome, tipo=tipo, citta=citta, dettaglio=d)
                foto = foto_annuncio(s, cartella, massimo=TIKTOK_MAX_FOTO)
                if len(foto) < TIKTOK_MIN_FOTO:
                    continue
                cs.log(f"{nome} TikTok: {s['id']} – {d['titolo']} – {len(foto)} foto")
                with sync_playwright() as p:
                    browser = p.chromium.launch()
                    try:
                        video = video_tiktok(browser, s, cartella, foto)
                    finally:
                        browser.close()
                cs.log("Video TikTok pronto:", video.name, f"({durata(video):.1f} s)")
                return s, video
            except Exception as e:
                cs.log(f"  {nome} TikTok: annuncio {scheda.get('id')} non riuscito:", e)
            finally:
                shutil.rmtree(cartella, ignore_errors=True)
    cs.log(f"Nessun annuncio con almeno {TIKTOK_MIN_FOTO} foto per {nome} (TikTok)")
    return None


def main_tiktok(args):
    """giro solo TikTok: un tour al giorno per categoria, annunci con tante foto mai usciti su TikTok"""
    cs.USCITA.mkdir(exist_ok=True)
    apertura_breve()
    stato = cs.carica_stato()
    oggi = date.today().isoformat()
    fatti = {p.get("tt") for p in stato["pubblicati"] if p.get("tt") and str(p.get("data", "")).startswith(oggi)}
    gia_tiktok = {p.get("id") for p in stato["pubblicati"] if "tiktok" in (p.get("social") or [])}
    quanti = int(os.environ.get("TIKTOK_AL_GIORNO", "1") or 1)
    lista = [x for x in candidati(stato, usati=gia_tiktok) if x[3] and (args.prova or x[0] not in fatti)]
    if not args.prova and not args.slot:
        quanti = max(0, quanti - len(fatti))        # quelli già usciti oggi contano
    if quanti <= 6:
        lista = [x for x in lista if not x[0].endswith("-2")]
        g = date.today().toordinal() % max(1, len(lista))      # ogni giorno un tipo diverso (vendita, affitto, asta...)
        lista = (lista[g:] + lista[:g])[:quanti]
    else:
        lista = lista[:quanti]
    if args.slot:
        lista = [x for x in candidati(stato, usati=gia_tiktok) if x[0] == args.slot and x[3]][:1]
    if not lista:
        cs.log("TikTok: niente da fare oggi.")
        return
    from concurrent.futures import ProcessPoolExecutor
    pronti = []
    with ProcessPoolExecutor(max_workers=int(os.environ.get("VIDEO_IN_PARALLELO", "3") or 3)) as pool:
        lavori = [pool.submit(produci_tiktok, n, t, c, sc) for n, t, c, sc in lista]
        for lavoro in lavori:
            try:
                r = lavoro.result()
                if r:
                    pronti.append(r)
            except Exception as e:
                cs.log("  TikTok: video non creato:", e)
    descr = []
    for k, (s, video) in enumerate(pronti):
        a = s["dettaglio"]
        testo = cs.testo_post(a, "tiktok")
        if args.prova:
            cs.log("PROVA, non pubblico:", video.name)
            continue
        if k:
            time.sleep(60 * float(os.environ.get("PAUSA_MINUTI", "3") or 3))
        try:
            os.environ["TIKTOK_COPERTINA_MS"] = "700"
            ris = cs.PUBBLICA["tiktok"](video, testo)
        except Exception as e:
            cs.log("tiktok: ERRORE", s["slot"], e)
            continue
        if ris is None:
            continue
        descr.append((s["slot"], testo))
        stato["pubblicati"].append({"id": s["id"], "tt": s["slot"], "social": ["tiktok"], "tiktok_id": str(ris),
                                    "data": datetime.now().isoformat(timespec="seconds"), "titolo": a.get("titolo"),
                                    "prezzo": a.get("prezzo"), "comune": a.get("comune"), "url": a.get("url")})
        cs.STATO.write_text(json.dumps(stato, ensure_ascii=False, indent=1))
        cs.log("Pubblicato TikTok", s["slot"], s["id"])
    if descr:
        righe = [f"# TikTok del {date.today().strftime('%d/%m/%Y')}", ""]
        for slot, testo in descr:
            righe += [f"## {slot.replace('-', ' ').title()}", "", "```", testo, "```", ""]
        (QUI / "tiktok-descrizioni.md").write_text("\n".join(righe), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prova", action="store_true", help="crea video e testi senza pubblicare")
    ap.add_argument("--solo-tiktok", action="store_true", help="giro TikTok: tour lunghi di annunci con tante foto")
    ap.add_argument("--quanti", type=int, default=int(os.environ.get("QUANTI_POST", "6") or 6))
    ap.add_argument("--slot", default="", help="un post in più di questo tipo, es. vendita-perugia (prova a mano)")
    ap.add_argument("--rifai-oggi", action="store_true",
                    help="ripubblica gli annunci già usciti oggi sui social indicati (es. solo facebook)")
    args = ap.parse_args()
    if args.solo_tiktok:
        return main_tiktok(args)

    social = [x.strip() for x in os.environ.get("SOCIAL_SEI", "facebook,instagram,tiktok").split(",") if x.strip()]
    pausa = int(os.environ.get("PAUSA_MINUTI", "3") or 3) * 60
    stato = cs.carica_stato()
    cs.USCITA.mkdir(exist_ok=True)
    oggi = date.today().isoformat()
    fatti_oggi = [p for p in stato["pubblicati"] if p.get("sei") and str(p.get("data", "")).startswith(oggi)]
    if args.rifai_oggi:
        # solo quelli che non sono ancora usciti su tutti i social richiesti
        solo = {p["sei"]: p["id"] for p in fatti_oggi if not set(social) <= set(p.get("social", []))}
        lista = [x for x in candidati(stato, solo) if x[3]]
        cs.log("Ripubblico gli annunci di oggi:", solo, "trovati:", [x[0] for x in lista])
    elif args.slot:      # un post in più del tipo scelto (annuncio mai pubblicato)
        lista = [x for x in candidati(stato) if x[0] == args.slot and x[3]][:1]
    else:
        da_fare = max(0, args.quanti - (0 if args.prova else len(fatti_oggi)))
        if not da_fare:
            cs.log("I post di oggi sono già stati pubblicati.")
            return
        gia = {p.get("sei") for p in fatti_oggi}
        lista = [x for x in candidati(stato) if x[3] and (args.prova or x[0] not in gia)][:da_fare]

    apertura_breve()
    os.environ["TIKTOK_COPERTINA_MS"] = str(tempo_copertina())   # copertina TikTok = foto dell'annuncio, non la sigla
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
    descrizioni_tiktok = []
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
                elif nome == "tiktok":
                    vt = v916
                    virale = cs.USCITA / f"{s['slot']}-tiktok.mp4"
                    if virale.exists():
                        vt = virale
                        os.environ["TIKTOK_COPERTINA_MS"] = "700"     # copertina = foto con il gancio scritto
                    cop_reel = v916.with_suffix(".jpg")
                    if vt == v916 and cop_reel.exists() and not (os.environ.get("UPLOADPOST_KEY") or os.environ.get("ZERNIO_KEY")):   # con Upload-Post la copertina la sceglie cover_timestamp
                        try:
                            vt = con_copertina_iniziale(v916, cop_reel)
                        except Exception as e:
                            cs.log("  TikTok: copertina iniziale non aggiunta:", e)
                    ris = cs.PUBBLICA[nome](vt, cs.testo_post(a, nome))
                    os.environ["TIKTOK_COPERTINA_MS"] = str(tempo_copertina())
                    if ris is not None:
                        descrizioni_tiktok.append((s["slot"], cs.testo_post(a, nome)))
                else:
                    ris = cs.PUBBLICA[nome](v916, cs.testo_post(a, nome))
                if ris is not None:
                    voce["social"].append(nome)
                    voce[f"{nome}_id"] = str(ris)
            except Exception as e:
                errori += 1
                cs.log(f"{nome}: ERRORE", s["slot"], e, (getattr(getattr(e, "response", None), "text", "") or "")[:500])
        vecchia = next((p for p in fatti_oggi if args.rifai_oggi and p.get("id") == s["id"]), None)
        if voce["social"] and vecchia:
            vecchia["social"] = sorted(set(vecchia.get("social", [])) | set(voce["social"]))
            vecchia.update({k: v for k, v in voce.items() if k.endswith("_id")})
            cs.STATO.write_text(json.dumps(stato, ensure_ascii=False, indent=1))
        elif voce["social"]:
            stato["pubblicati"].append(voce)
            cs.STATO.write_text(json.dumps(stato, ensure_ascii=False, indent=1))
        cs.log("Pubblicato", s["slot"], "su:", ", ".join(voce["social"]) or "nessuno")
    if descrizioni_tiktok:
        # TikTok non riceve il testo insieme alla bozza: lo metto in un file da copiare dal telefono
        righe = [f"# Descrizioni TikTok del {date.today().strftime('%d/%m/%Y')}", "",
                 "Apri la bozza su TikTok, tieni premuto sul testo qui sotto, copia e incolla nella descrizione.", ""]
        for slot, testo in descrizioni_tiktok:
            righe += [f"## {slot.replace('-', ' ').title()}", "", "```", testo, "```", ""]
        (QUI / "tiktok-descrizioni.md").write_text("\n".join(righe), encoding="utf-8")
    if pronti and errori >= len(pronti) * len(social):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
