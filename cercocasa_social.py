#!/usr/bin/env python3
"""
Cercocasa Umbria - video automatici per Instagram e TikTok.

Ogni esecuzione:
  1. sceglie un annuncio dal sito (ruotando tra le agenzie, mai due volte lo stesso)
  2. scarica le foto e crea un video verticale 1080x1920
  3. scrive il testo del post con hashtag
  4. pubblica su Instagram (Reel) e TikTok, se le chiavi sono configurate

Uso:
  python cercocasa_social.py                 # sceglie, crea e pubblica
  python cercocasa_social.py --prova         # crea solo il video, non pubblica
  python cercocasa_social.py --id 4586       # usa un annuncio preciso
  python cercocasa_social.py --foto cartella --prova   # video da foto locali (test)
"""
import argparse, glob, json, os, random, re, shutil, subprocess, sys, tempfile, time, html
from datetime import datetime
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

# ---------------------------------------------------------------- impostazioni
SITO = os.environ.get("SITO", "https://www.cercocasaumbria.it").rstrip("/")
QUI = Path(__file__).resolve().parent
FONT = QUI / "font" / "Montserrat.ttf"
MUSICA = QUI / "musica"
STATO = QUI / "pubblicati.json"
USCITA = QUI / "video"

W, H, FPS = 1080, 1920, 30
BLU = (8, 127, 174)          # colore del sito #087fae
SECONDI_FOTO = 2.4
DISSOLVENZA = 0.4
MAX_FOTO = 7

# pagine da cui raccogliere gli annunci (i più recenti per primi)
PAGINE_ELENCO = [
    "/mappa-ricerca.php?operation=vendita&sort=recenti",
    "/",
    "/case-vendita/perugia/", "/case-vendita/terni/", "/case-vendita/todi/",
    "/case-vendita/corciano/", "/case-vendita/magione/", "/case-vendita/assisi/",
    "/case-vendita/marsciano/", "/case-vendita/foligno/", "/case-vendita/spoleto/",
    "/case-vendita/passignano-sul-trasimeno/", "/prestigio.php",
]

HTTP = requests.Session()
HTTP.headers["User-Agent"] = "CercocasaUmbria-Social/1.0 (+https://www.cercocasaumbria.it)"


def log(*a):
    print(datetime.now().strftime("%H:%M:%S"), *a, flush=True)


# ---------------------------------------------------------------- lettura sito
def scarica_testo(url):
    r = HTTP.get(url, timeout=30)
    r.raise_for_status()
    return r.text


def raccogli_id():
    ids = []
    for p in PAGINE_ELENCO:
        try:
            t = scarica_testo(SITO + p)
        except Exception as e:
            log("  pagina saltata", p, e)
            continue
        for m in re.findall(r"immobile\.php\?id=(\d+)", t):
            if int(m) not in ids:
                ids.append(int(m))
    return ids


def pulisci(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def leggi_annuncio(id_):
    url = f"{SITO}/immobile.php?id={id_}"
    t = scarica_testo(url)
    testo = pulisci(t)

    def meta(prop):
        m = re.search(rf'<meta[^>]+(?:property|name)=["\']{prop}["\'][^>]+content=["\']([^"\']*)', t, re.I) \
            or re.search(rf'<meta[^>]+content=["\']([^"\']*)["\'][^>]+(?:property|name)=["\']{prop}["\']', t, re.I)
        return html.unescape(m.group(1)).strip() if m else ""

    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", t, re.S | re.I)
    titolo = pulisci(h1.group(1)) if h1 else meta("og:title").split("|")[0].strip()

    prezzo = ""
    m = re.search(r"(da\s*)?€\s?\d{1,3}(?:\.\d{3})+", testo)
    if m:
        prezzo = m.group(0).replace("€ ", "€ ").strip()
        if not re.search(r"€ ", prezzo):
            prezzo = prezzo.replace("€", "€ ")

    comune = ""
    m = re.search(r"⌖\s*([^⌖()]{2,60}?)\s*\((PG|TR)\)", testo)
    if m:
        comune = m.group(1).strip()
    citta = comune.split("·")[0].strip() if comune else ""

    agenzia = ""
    m = re.search(r'agenzia\.php\?id=\d+[^>]*>(.*?)</a>', t, re.S | re.I)
    if m:
        agenzia = pulisci(m.group(1))

    def numero(rx):
        m = re.search(rx, testo, re.I)
        return m.group(1) if m else ""

    locali = numero(r"(\d+)\s*local[ei]")
    bagni = numero(r"(\d+)\s*bagn[io]")
    mq = numero(r"(\d{2,5})\s*m²") or numero(r"(\d{2,5})\s*mq")

    operazione = "IN AFFITTO" if re.search(r"/mese|affitto", prezzo + " " + titolo, re.I) else "IN VENDITA"
    if "ASTA" in titolo.upper() or prezzo.lower().startswith("da"):
        operazione = "ALL'ASTA"

    foto = []
    for f in re.findall(rf'(?:https?://[^"\'\s]+)?/?uploads/properties/{id_}/[^"\'\s)>]+?\.(?:jpe?g|png|webp)', t, re.I):
        f = f if f.startswith("http") else SITO + "/" + f.lstrip("/")
        if f not in foto and not re.search(r"thumb|small|mini", f, re.I):
            foto.append(f)
    if not foto and meta("og:image"):
        foto.append(meta("og:image"))

    return dict(id=id_, url=url, titolo=titolo, prezzo=prezzo, comune=comune, citta=citta,
                agenzia=agenzia, locali=locali, bagni=bagni, mq=mq, operazione=operazione, foto=foto)


# ---------------------------------------------------------------- scelta annuncio
def carica_stato():
    if STATO.exists():
        return json.loads(STATO.read_text())
    return {"pubblicati": []}


AGENZIE = QUI / "agenzie_rivista.json"


def scegli_da_rivista(stato):
    """un'agenzia delle riviste al giorno, alternando Perugia e Terni"""
    elenco = [a for a in json.loads(AGENZIE.read_text(encoding="utf-8"))["agenzie"] if a.get("attiva", True)]
    if not elenco:
        return None
    gia = {p["id"] for p in stato["pubblicati"]}
    ultima = {}
    for i, p in enumerate(stato["pubblicati"]):
        if p.get("agenzia_id"):
            ultima[p["agenzia_id"]] = i
    ultima_rivista = next((p.get("rivista") for p in reversed(stato["pubblicati"]) if p.get("rivista")), None)
    # prima le agenzie dell'altra rivista rispetto a ieri, poi quelle ferme da più tempo
    elenco.sort(key=lambda a: (a.get("rivista") == ultima_rivista, ultima.get(a["id"], -1)))
    for ag in elenco:
        try:
            pagina = scarica_testo(f"{SITO}/agenzia.php?id={ag['id']}")
        except Exception as e:
            log("  agenzia saltata", ag["nome"], e)
            continue
        ids = list(dict.fromkeys(int(i) for i in re.findall(r"immobile\.php\?id=(\d+)", pagina)))
        for id_ in sorted((i for i in ids if i not in gia), reverse=True)[:8]:
            try:
                a = leggi_annuncio(id_)
            except Exception as e:
                log("  annuncio saltato", id_, e)
                continue
            if len(a["foto"]) >= 3 and a["prezzo"]:
                a["agenzia"] = a["agenzia"] or ag["nome"]
                a["agenzia_id"], a["rivista"] = ag["id"], ag.get("rivista", "")
                return a
        log(f"  {ag['nome']}: nessun annuncio nuovo adatto")
    return None


def scegli_annuncio(stato):
    if AGENZIE.exists():
        return scegli_da_rivista(stato)
    gia = {p["id"] for p in stato["pubblicati"]}
    ultima_volta = {}
    for i, p in enumerate(stato["pubblicati"]):
        ultima_volta[p.get("agenzia", "")] = i
    candidati = [i for i in raccogli_id() if i not in gia]
    log(f"annunci trovati non ancora pubblicati: {len(candidati)}")
    letti = []
    for id_ in candidati[:25]:
        try:
            a = leggi_annuncio(id_)
        except Exception as e:
            log("  annuncio saltato", id_, e)
            continue
        if len(a["foto"]) >= 3 and a["prezzo"]:
            letti.append(a)
    if not letti:
        return None
    # agenzia pubblicata da più tempo (o mai) per prima, poi annuncio più nuovo
    letti.sort(key=lambda a: (ultima_volta.get(a["agenzia"], -1), -a["id"]))
    return letti[0]


# ---------------------------------------------------------------- grafica
def font(dim, peso="ExtraBold"):
    f = ImageFont.truetype(str(FONT), dim)
    try:
        f.set_variation_by_name(peso)
    except Exception:
        pass
    return f


def a_capo(draw, testo, f, larghezza, max_righe):
    parole, righe, riga = testo.split(), [], ""
    for p in parole:
        prova = (riga + " " + p).strip()
        if draw.textlength(prova, font=f) <= larghezza:
            riga = prova
        else:
            righe.append(riga)
            riga = p
    righe.append(riga)
    if len(righe) > max_righe:
        righe = righe[:max_righe]
        while draw.textlength(righe[-1] + "…", font=f) > larghezza and " " in righe[-1]:
            righe[-1] = righe[-1].rsplit(" ", 1)[0]
        righe[-1] += "…"
    return righe


def sfumatura(alto, basso):
    """livello trasparente con ombra in alto e in basso per leggere le scritte"""
    lv = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    px = ImageDraw.Draw(lv)
    for y in range(alto):
        px.line([(0, y), (W, y)], fill=(0, 0, 0, int(170 * (1 - y / alto) ** 1.6)))
    for y in range(basso):
        px.line([(0, H - 1 - y), (W, H - 1 - y)], fill=(0, 0, 0, int(200 * (1 - y / basso) ** 1.4)))
    return lv


def pillola(d, xy, testo, f, fondo, colore=(255, 255, 255), pad=(28, 14), centro=False):
    x, y = xy
    tw = d.textlength(testo, font=f)
    asc, disc = f.getmetrics()
    w, h = tw + 2 * pad[0], asc + disc + 2 * pad[1]
    if centro:
        x = (W - w) / 2
    d.rounded_rectangle([x, y, x + w, y + h], radius=h / 2, fill=fondo)
    d.text((x + pad[0], y + pad[1]), testo, font=f, fill=colore)
    return h


def caratteristiche(a):
    c = []
    if a["locali"]:
        c.append(f'{a["locali"]} locali')
    if a["bagni"]:
        c.append(f'{a["bagni"]} bagn{"o" if a["bagni"] == "1" else "i"}')
    if a["mq"]:
        c.append(f'{a["mq"]} m²')
    return "  ·  ".join(c)


def livello_apertura(a):
    lv = sfumatura(760, 1000)
    d = ImageDraw.Draw(lv)
    y = 160
    y += pillola(d, (70, y), a["operazione"] + (f" · {a['citta'].upper()}" if a["citta"] else ""),
                 font(40, "Bold"), BLU) + 36
    fp = font(150, "Black")
    d.text((66, y), a["prezzo"], font=fp, fill="white", stroke_width=2, stroke_fill=(0, 0, 0, 80))
    y += 175
    for r in a_capo(d, a["titolo"], font(54, "Bold"), W - 140, 3):
        d.text((70, y), r, font=font(54, "Bold"), fill="white")
        y += 68
    car = caratteristiche(a)
    if car:
        pillola(d, (0, H - 600), car, font(46, "Bold"), (255, 255, 255, 235), (20, 20, 20), centro=True)
    marchio(d)
    return lv


def livello_foto(a):
    lv = sfumatura(330, 420)
    d = ImageDraw.Draw(lv)
    pillola(d, (60, 140), a["prezzo"], font(52, "Black"), BLU)
    if a["comune"]:
        d.text((64, 235), a["comune"], font=font(42, "Bold"), fill="white")
    marchio(d)
    return lv


def marchio(d):
    f = font(36, "Bold")
    t = "CERCOCASA UMBRIA"
    d.text(((W - d.textlength(t, font=f)) / 2, 58), t, font=f, fill=(255, 255, 255, 230))


def immagine_finale(a, sfondo):
    img = ImageOps.fit(sfondo, (W, H)).filter(ImageFilter.GaussianBlur(28))
    img = Image.alpha_composite(img.convert("RGBA"), Image.new("RGBA", (W, H), (*BLU, 205)))
    d = ImageDraw.Draw(img)

    def centra(testo, y, f, colore="white"):
        d.text(((W - d.textlength(testo, font=f)) / 2, y), testo, font=f, fill=colore)

    centra("CERCOCASA", 470, font(110, "Black"))
    centra("UMBRIA", 590, font(110, "Black"))
    centra("Il portale delle case in Umbria", 735, font(44, "SemiBold"))
    if a["agenzia"]:
        centra("Annuncio di", 920, font(40, "Medium"))
        for i, r in enumerate(a_capo(d, a["agenzia"], font(52, "Bold"), W - 140, 2)):
            centra(r, 975 + i * 64, font(52, "Bold"))
    pillola(d, (0, 1230), "👉 LINK IN BIO".replace("👉 ", ""), font(56, "Black"), "white", BLU, (44, 22), centro=True)
    centra("cercocasaumbria.it", 1385, font(50, "Bold"))
    centra(f"Codice annuncio {a['id']}", 1460, font(40, "Medium"), (255, 255, 255, 220))
    return img.convert("RGB")


def copri(img, verticale_ok=True):
    """ridimensiona perché copra 1080x1920 lasciando margine per il movimento"""
    img = ImageOps.exif_transpose(img).convert("RGB")
    r = max(W / img.width, H / img.height)
    if img.width / img.height <= W / H:      # foto verticale: un po' di zoom per poter scorrere in verticale
        r *= 1.12
    return img.resize((round(img.width * r), round(img.height * r)), Image.LANCZOS)


# ---------------------------------------------------------------- video
def ff(*args):
    cmd = ["ffmpeg", "-y", "-loglevel", "error", *map(str, args)]
    subprocess.run(cmd, check=True)


def crea_video(a, foto_locali, destinazione):
    tmp = Path(tempfile.mkdtemp())
    clip = []
    foto_locali = foto_locali[:MAX_FOTO]
    for i, fp in enumerate(foto_locali):
        base = copri(Image.open(fp))
        base_p = tmp / f"b{i}.jpg"
        base.save(base_p, quality=92)
        lv = livello_apertura(a) if i == 0 else livello_foto(a)
        lv_p = tmp / f"l{i}.png"
        lv.save(lv_p)
        dur = SECONDI_FOTO + (0.8 if i == 0 else 0)
        verso = 1 if i % 2 == 0 else -1
        # scorrimento lento della foto (effetto "tour")
        if verso == 1:
            x, y = f"(iw-{W})*t/{dur}", f"(ih-{H})*t/{dur}"
        else:
            x, y = f"(iw-{W})*(1-t/{dur})", f"(ih-{H})*(1-t/{dur})"
        out = tmp / f"c{i}.mp4"
        ff("-loop", "1", "-t", dur, "-i", base_p, "-i", lv_p,
           "-filter_complex", f"[0:v]crop={W}:{H}:x='{x}':y='{y}',fps={FPS},format=yuv420p[b];[b][1:v]overlay=0:0,format=yuv420p",
           "-t", dur, "-r", FPS, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", out)
        clip.append((out, dur))
    # schermata finale
    fin = immagine_finale(a, Image.open(foto_locali[0]))
    fin_p = tmp / "fine.jpg"
    fin.save(fin_p, quality=92)
    out = tmp / "cfine.mp4"
    ff("-loop", "1", "-t", 2.6, "-i", fin_p, "-vf", f"fps={FPS},format=yuv420p", "-t", 2.6,
       "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", out)
    clip.append((out, 2.6))

    # unione con dissolvenze
    ingressi, filtri, prec, t = [], [], "0:v", 0.0
    for c, _ in clip:
        ingressi += ["-i", c]
    for k in range(1, len(clip)):
        t += clip[k - 1][1] - DISSOLVENZA
        nome = f"v{k}"
        filtri.append(f"[{prec}][{k}:v]xfade=transition=fade:duration={DISSOLVENZA}:offset={t:.2f}[{nome}]")
        prec = nome
    durata = sum(d for _, d in clip) - DISSOLVENZA * (len(clip) - 1)

    brani = sorted(glob.glob(str(MUSICA / "*.mp3")) + glob.glob(str(MUSICA / "*.m4a")))
    if brani:
        audio = ["-stream_loop", "-1", "-i", random.choice(brani)]
        afiltro = f";[{len(clip)}:a]atrim=0:{durata:.2f},afade=t=in:d=0.5,afade=t=out:st={durata - 1.2:.2f}:d=1.2,volume=0.8[a]"
    else:
        audio = ["-f", "lavfi", "-t", f"{durata:.2f}", "-i", "anullsrc=r=44100:cl=stereo"]
        afiltro = f";[{len(clip)}:a]anull[a]"
    ff(*ingressi, *audio, "-filter_complex", ";".join(filtri) + f";[{prec}]format=yuv420p[v]" + afiltro,
       "-map", "[v]", "-map", "[a]", "-t", f"{durata:.2f}",
       "-c:v", "libx264", "-preset", "medium", "-crf", "21", "-profile:v", "high", "-pix_fmt", "yuv420p",
       "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", destinazione)
    shutil.rmtree(tmp, ignore_errors=True)
    return durata


# ---------------------------------------------------------------- testo del post
def hashtag(s):
    s = re.sub(r"[^\w]", "", s.lower().replace("à", "a").replace("è", "e").replace("é", "e")
               .replace("ì", "i").replace("ò", "o").replace("ù", "u"))
    return "#" + s if s else ""


def prezzo_numero(a):
    m = re.search(r"\d{1,3}(?:\.\d{3})+", a.get("prezzo", ""))
    return int(m.group(0).replace(".", "")) if m else 0


def gancio(a):
    """prima riga del post: quella che fa fermare chi scorre"""
    t, c, p = a["titolo"].lower(), a["citta"] or "Umbria", prezzo_numero(a)
    if a["operazione"] == "ALL'ASTA":
        return f"⚖️ All'asta a {c}: si parte {a['prezzo'].replace('da ', 'da ')}!"
    if a["operazione"] == "IN AFFITTO":
        return f"🔑 In affitto a {c}: {a['prezzo']}"
    if any(k in t for k in ("casale", "rustico", "colonica", "tenuta")):
        return f"🌿 Il sogno di un casale in Umbria: {c}, {a['prezzo']}"
    if "villa" in t:
        return f"🏡 Villa a {c} a {a['prezzo']}"
    if "terreno" in t:
        return f"🌾 Terreno a {c}: {a['prezzo']}"
    if 0 < p < 100000:
        return f"👀 Casa a {c} sotto i 100.000 €: {a['prezzo']}"
    return f"🏠 Nuova in vendita a {c}: {a['prezzo']}"


def hashtags(a, quanti):
    op = {"IN VENDITA": "#casainvendita", "IN AFFITTO": "#casainaffitto", "ALL'ASTA": "#asteimmobiliari"}[a["operazione"]]
    prov = "#perugia" if a.get("rivista") == "Perugia" else ("#terni" if a.get("rivista") == "Terni" else "")
    tag = [hashtag(a["citta"]), "#umbria", op, prov, "#case", "#immobiliare", "#cercocasaumbria",
           "#casa", "#casedavendere", "#immobili", "#umbriahouse", "#italianhome", "#realestateitaly"]
    return " ".join(list(dict.fromkeys(t for t in tag if t))[:quanti])


def testo_post(a, social="instagram"):
    car = caratteristiche(a).replace("  ·  ", " · ")
    scheda = [x for x in (f"📍 {a['comune']}" if a["comune"] else "", f"💶 {a['prezzo']}",
                          f"📐 {car}" if car else "") if x]
    agenzia = f"Annuncio di {a['agenzia']}" if a["agenzia"] else ""
    domanda = "Che ne pensi del prezzo? Scrivilo nei commenti 👇"

    if social == "facebook":
        righe = [gancio(a), "", a["titolo"], "", *scheda, ""]
        righe += [agenzia, "", f"👉 Tutte le foto e i contatti: {a['url']}", "", domanda, "", hashtags(a, 4)]
    elif social == "tiktok":
        righe = [gancio(a), f"{a['titolo']}", f"{car}" if car else "", agenzia,
                 f"Foto e contatti su cercocasaumbria.it (codice {a['id']})", hashtags(a, 5)]
    else:  # instagram
        righe = [gancio(a), "", a["titolo"], "", *scheda, "", agenzia, "",
                 f"👉 Tutte le foto e i contatti su cercocasaumbria.it (link in bio) – codice {a['id']}",
                 "", domanda, "", "📌 Salva il post e condividilo con chi cerca casa in Umbria", "", hashtags(a, 12)]
    out = "\n".join(righe)
    return re.sub(r"\n{3,}", "\n\n", out).strip()


# ---------------------------------------------------------------- pubblicazione Instagram
GRAPH = "https://graph.facebook.com/v21.0"


def pubblica_instagram(video, testo):
    ig, token = os.environ.get("IG_USER_ID"), os.environ.get("IG_TOKEN")
    if not (ig and token):
        log("Instagram: chiavi non configurate, salto")
        return None
    r = HTTP.post(f"{GRAPH}/{ig}/media", data={
        "media_type": "REELS", "upload_type": "resumable", "caption": testo,
        "share_to_feed": "true", "access_token": token}, timeout=60)
    r.raise_for_status()
    cont = r.json()["id"]
    dati = Path(video).read_bytes()
    r = HTTP.post(f"https://rupload.facebook.com/ig-api-upload/v21.0/{cont}", data=dati, timeout=300,
                  headers={"Authorization": f"OAuth {token}", "offset": "0", "file_size": str(len(dati))})
    r.raise_for_status()
    for _ in range(60):
        time.sleep(10)
        s = HTTP.get(f"{GRAPH}/{cont}", params={"fields": "status_code,status", "access_token": token}, timeout=30).json()
        if s.get("status_code") == "FINISHED":
            break
        if s.get("status_code") == "ERROR":
            raise RuntimeError(f"Instagram ha rifiutato il video: {s}")
    r = HTTP.post(f"{GRAPH}/{ig}/media_publish", data={"creation_id": cont, "access_token": token}, timeout=60)
    r.raise_for_status()
    log("Instagram: pubblicato", r.json())
    return r.json().get("id")


# ---------------------------------------------------------------- pubblicazione Facebook
def pubblica_facebook(video, testo):
    pagina, token = os.environ.get("FB_PAGE_ID"), os.environ.get("FB_PAGE_TOKEN") or os.environ.get("IG_TOKEN")
    if not (pagina and token):
        log("Facebook: chiavi non configurate, salto")
        return None
    # il token della Pagina si ricava dal token di sistema
    r = HTTP.get(f"{GRAPH}/{pagina}", params={"fields": "access_token", "access_token": token}, timeout=30)
    if r.ok and r.json().get("access_token"):
        token = r.json()["access_token"]
    r = HTTP.post(f"{GRAPH}/{pagina}/video_reels", data={"upload_phase": "start", "access_token": token}, timeout=60)
    r.raise_for_status()
    vid = r.json()["video_id"]
    dati = Path(video).read_bytes()
    r = HTTP.post(f"https://rupload.facebook.com/video-upload/v21.0/{vid}", data=dati, timeout=300,
                  headers={"Authorization": f"OAuth {token}", "offset": "0", "file_size": str(len(dati))})
    r.raise_for_status()
    r = HTTP.post(f"{GRAPH}/{pagina}/video_reels", data={
        "upload_phase": "finish", "video_id": vid, "video_state": "PUBLISHED",
        "description": testo, "access_token": token}, timeout=60)
    r.raise_for_status()
    log("Facebook: pubblicato", vid)
    return vid


# ---------------------------------------------------------------- pubblicazione TikTok
def token_tiktok():
    rt = os.environ.get("TIKTOK_REFRESH_TOKEN")
    if not rt:
        return os.environ.get("TIKTOK_TOKEN")
    r = HTTP.post("https://open.tiktokapis.com/v2/oauth/token/", data={
        "client_key": os.environ["TIKTOK_CLIENT_KEY"], "client_secret": os.environ["TIKTOK_CLIENT_SECRET"],
        "grant_type": "refresh_token", "refresh_token": rt}, timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]


def pubblica_tiktok(video, testo):
    token = token_tiktok()
    if not token:
        log("TikTok: chiavi non configurate, salto")
        return None
    dim = Path(video).stat().st_size
    modo = os.environ.get("TIKTOK_MODO", "bozza")  # bozza = arriva nelle notifiche TikTok da confermare
    sorgente = {"source": "FILE_UPLOAD", "video_size": dim, "chunk_size": dim, "total_chunk_count": 1}
    if modo == "diretto":
        url = "https://open.tiktokapis.com/v2/post/publish/video/init/"
        corpo = {"post_info": {"title": testo[:2200], "privacy_level": os.environ.get("TIKTOK_PRIVACY", "PUBLIC_TO_EVERYONE"),
                               "disable_comment": False}, "source_info": sorgente}
    else:
        url = "https://open.tiktokapis.com/v2/post/publish/inbox/video/init/"
        corpo = {"source_info": sorgente}
    r = HTTP.post(url, json=corpo, timeout=60,
                  headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"})
    r.raise_for_status()
    d = r.json()["data"]
    r = HTTP.put(d["upload_url"], data=Path(video).read_bytes(), timeout=300, headers={
        "Content-Type": "video/mp4", "Content-Range": f"bytes 0-{dim - 1}/{dim}"})
    r.raise_for_status()
    log(f"TikTok: inviato ({modo})", d.get("publish_id"))
    return d.get("publish_id")


# ---------------------------------------------------------------- avvio
def scarica_foto(a, cartella):
    file = []
    for i, u in enumerate(a["foto"][:MAX_FOTO]):
        try:
            r = HTTP.get(u, timeout=60)
            r.raise_for_status()
            p = cartella / f"{i:02d}{Path(u).suffix or '.jpg'}"
            p.write_bytes(r.content)
            Image.open(p).verify()
            file.append(p)
        except Exception as e:
            log("  foto saltata", u, e)
    return file


PUBBLICA = {"facebook": lambda v, t: pubblica_facebook(v, t),
            "instagram": lambda v, t: pubblica_instagram(v, t),
            "tiktok": lambda v, t: pubblica_tiktok(v, t)}


def prepara(a, args):
    """scarica le foto e crea video + testo; restituisce (video, testo) o None"""
    log(f"Annuncio: {a['id']} – {a['titolo']} – {a['prezzo']} – {a['agenzia']} ({a.get('rivista', '')})")
    if args.foto:
        foto = sorted(p for p in Path(args.foto).iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"))
    else:
        foto = scarica_foto(a, Path(tempfile.mkdtemp()))
    if len(foto) < 3:
        log("Troppe poche foto, salto.")
        return None
    video = USCITA / f"annuncio-{a['id']}.mp4"
    durata = crea_video(a, foto, video)
    log(f"Video pronto: {video.name} ({durata:.1f} s)")
    return video


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prova", action="store_true", help="crea i video senza pubblicare")
    ap.add_argument("--id", type=int, help="annuncio preciso")
    ap.add_argument("--foto", help="cartella di foto locali (per test)")
    ap.add_argument("--dati", help="file json con i dati dell'annuncio (per test)")
    args = ap.parse_args()

    stato = carica_stato()
    USCITA.mkdir(exist_ok=True)
    social = [x.strip() for x in os.environ.get("SOCIAL", "facebook,instagram,tiktok").split(",") if x.strip()]
    # diversi = un annuncio (e un'agenzia) diverso per ogni social; uguale = stesso video ovunque
    modo = os.environ.get("MODO_POST", "diversi")

    if args.dati or args.id:
        a = json.loads(Path(args.dati).read_text()) if args.dati else leggi_annuncio(args.id)
        turni = [(a, social)]
    else:
        turni = []
        gruppi = [[s] for s in social] if modo == "diversi" else [social]
        for gruppo in gruppi:
            a = scegli_annuncio(stato)
            if not a:
                log("Nessun annuncio nuovo per", ",".join(gruppo))
                continue
            turni.append((a, gruppo))
            # segna subito, così il social successivo prende un'altra agenzia
            stato["pubblicati"].append({"id": a["id"], "agenzia": a["agenzia"], "agenzia_id": a.get("agenzia_id"),
                                        "rivista": a.get("rivista"), "social": gruppo,
                                        "data": datetime.now().isoformat(timespec="minutes")})

    errori = totale = 0
    for a, gruppo in turni:
        pronto = prepara(a, args)
        if not pronto:
            continue
        video = pronto
        for nome in gruppo:
            testo = testo_post(a, nome)
            (USCITA / f"annuncio-{a['id']}-{nome}.txt").write_text(testo, encoding="utf-8")
            if args.prova:
                print(f"\n===== {nome.upper()} =====\n{testo}\n")
                continue
            totale += 1
            try:
                PUBBLICA[nome](video, testo)
            except Exception as e:
                dettagli = getattr(getattr(e, "response", None), "text", "")
                log(f"{nome}: ERRORE", e, (dettagli or "")[:500])
                errori += 1

    if not args.prova and not (args.dati or args.id):
        STATO.write_text(json.dumps(stato, ensure_ascii=False, indent=1))
    if totale and errori == totale:
        sys.exit(1)


if __name__ == "__main__":
    main()
