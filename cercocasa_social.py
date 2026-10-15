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
FONT_TITOLI = QUI / "font" / "Oswald.ttf"
URL_OSWALD = "https://raw.githubusercontent.com/google/fonts/main/ofl/oswald/Oswald%5Bwght%5D.ttf"
MUSICA = QUI / "musica"
# usa il primo file .png il cui nome inizia con "logo" (es. logo.png, logo-v191.png)
CORNICE = QUI / "cornice.png"   # grafica con barre in alto e in basso (centro trasparente)
LOGO = next(iter(sorted(QUI.glob("logo*.png")) + sorted(QUI.glob("Logo*.png"))), QUI / "logo.png")
# voci SOLO italiane (quelle "Multilingual" a volte leggono le frasi corte in inglese)
VOCE = os.environ.get("VOCE", "it-IT-IsabellaNeural")
VOCI_PROVA = ["it-IT-IsabellaNeural", "it-IT-ElsaNeural", "it-IT-DiegoNeural"]
VERSIONE = 5   # quando cambia, la settimana già preparata viene rifatta con la grafica nuova
VOCE_VELOCITA = os.environ.get("VOCE_VELOCITA", "-6%")
VOCE_TONO = os.environ.get("VOCE_TONO", "+0Hz")      # tono naturale (abbassarlo rende la voce metallica)
STATO = QUI / "pubblicati.json"
USCITA = QUI / "video"

W, H, FPS = 1080, 1920, 30
BLU = (8, 127, 174)          # colore del sito #087fae
ORO = (190, 145, 40)         # colori del logo
SCURO = (24, 24, 26)
SECONDI_FOTO = 2.6
DISSOLVENZA = 0.4
MAX_FOTO = 12

# pagine da cui raccogliere gli annunci (i più recenti per primi)
PAGINE_ELENCO = [
    "/mappa-ricerca.php?operation=vendita&sort=recenti",
    "/",
    "/case-vendita/perugia/", "/case-vendita/terni/", "/case-vendita/todi/",
    "/case-vendita/corciano/", "/case-vendita/magione/", "/case-vendita/assisi/",
    "/case-vendita/marsciano/", "/case-vendita/foligno/", "/case-vendita/spoleto/",
    "/case-vendita/passignano-sul-trasimeno/", "/prestigio.php",
]

INIZIO = time.time()
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
    t = re.sub(r"<(style|script|noscript)[^>]*>.*?</\1>", " ", t, flags=re.S | re.I)
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
    tt = re.search(r"<title[^>]*>(.*?)</title>", t, re.S | re.I)
    m = re.search(r"(?:vendita|affitto|asta)\s+a\s+([A-ZÀ-Ýa-zà-ý' ]{2,40}?)\s*(?:[–|,\-(]|$)", pulisci(tt.group(1)) if tt else "")
    if not m:
        m = re.search(r"(?:Vendita|Affitto|Asta)\s+a\s+([A-ZÀ-Ý][A-Za-zà-ý' ]{1,40}?)\s*/", testo)
    if not m:
        m = re.search(r"\b([A-ZÀ-Ý][A-Za-zà-ý' ]{2,40}?)\s*\((?:PG|TR)\)", testo)
    if m and not comune:
        comune = m.group(1).strip()
    citta = comune.split("·")[0].strip() if comune else ""
    provincia = "PG" if "(PG)" in testo else ("TR" if "(TR)" in testo else "")

    agenzia = ""
    for m in re.finditer(r'agenzia\.php\?id=\d+[^>]*>([^<]{3,120})</a>', t, re.I):
        agenzia = pulisci(m.group(1))
        break

    def numero(rx):
        m = re.search(rx, testo, re.I)
        return m.group(1) if m else ""

    locali = numero(r"(\d+)\s*local[ei]")
    bagni = numero(r"(\d+)\s*bagn[io]")
    mq = numero(r"(\d{2,5})\s*m²") or numero(r"(\d{2,5})\s*mq")

    operazione = "IN AFFITTO" if re.search(r"/mese|al mese|affitto|locazione", prezzo + " " + titolo, re.I) else "IN VENDITA"
    m_p = re.search(r"\d{1,3}(?:\.\d{3})+|\d+", prezzo)
    if operazione == "IN VENDITA" and m_p and 0 < int(m_p.group(0).replace(".", "")) < 8000:
        operazione = "IN AFFITTO"   # es. € 1.100: è un canone mensile
    if operazione == "IN AFFITTO" and prezzo and "mese" not in prezzo:
        prezzo += "/mese"
    if "ASTA" in titolo.upper() or prezzo.lower().startswith("da"):
        operazione = "ALL'ASTA"

    foto = []
    for f in re.findall(rf'(?:https?://[^"\'\s]+)?/?uploads/properties/{id_}/[^"\'\s)>]+?\.(?:jpe?g|png|webp)', t, re.I):
        f = f if f.startswith("http") else SITO + "/" + f.lstrip("/")
        if f not in foto and not re.search(r"thumb|small|mini", f, re.I):
            foto.append(f)
    if not foto and meta("og:image"):
        foto.append(meta("og:image"))

    descrizione, punti = "", []
    m = re.search(r">\s*Descrizione\s*</h\d>(.*?)<h\d[^>]*>\s*(?:Caratteristiche|Altre caratteristiche|Informazioni)", t, re.S | re.I)
    if m:
        blocco = m.group(1)
        punti = [pulisci(x) for x in re.findall(r"<li[^>]*>(.*?)</li>", blocco, re.S | re.I)]
        blocco = re.sub(r"<li[^>]*>.*?</li>", " ", blocco, flags=re.S | re.I)
        blocco = re.sub(r"(?i)<br\s*/?>|</p>|</div>", ". ", blocco)
        descrizione = pulisci(blocco)
        descrizione = descrizione.split(" Contatta")[0]
    if not descrizione:
        m = re.search(r"\bDescrizione\b(.{40,3000}?)\b(?:Caratteristiche|Altre caratteristiche)\b", testo, re.S)
        if m:
            descrizione = m.group(1).strip()
    camere = numero(r"Camere da letto\s*(\d+)")
    piano = numero(r"\bPiano\s+(terra|rialzato|ultimo|\d+)\b")

    return dict(id=id_, url=url, titolo=titolo, prezzo=prezzo, comune=comune, citta=citta,
                descrizione=descrizione, punti=punti, camere=camere, piano=piano,
                agenzia=agenzia, provincia=provincia, locali=locali, bagni=bagni, mq=mq, operazione=operazione, foto=foto)


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
                a["agenzia"] = ag["nome"]
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


# ---------------------------------------------------------------- sottotitoli
SCARTA = re.compile(r"€|\biva\b|buona fede|propriet[aà] |dati |telefon|contatt|www|@|\brif\b|codice|"
                    r"agenzia|mediazione|provvigion|appuntamento|chiama|whatsapp|informazion|disponibil", re.I)
APERTURE = re.compile(r"^(proponiamo|vendesi|si vende|in vendita|vendiamo|offriamo|presentiamo|disponiamo di)\s+(in vendita\s+)?", re.I)
ARTICOLO = re.compile(r"^(un|una|uno|il|lo|la|l')\s*(?=\w)", re.I)


def accorcia(frase, massimo=58):
    frase = frase.strip(" .,;:-–")
    if len(frase) <= massimo:
        return [frase]
    pezzi, out = re.split(r",\s+|\s+e\s+(?=[a-zà-ù]+\s)|\s+con\s+", frase), []
    for p in pezzi:
        p = p.strip(" .,;:-–")
        if 10 <= len(p) <= massimo:
            out.append(p)
    return out


def sottotitoli(a, quanti):
    desc, punti = [], []
    testo = a.get("descrizione", "")
    for f in re.split(r"(?<=[.!?;])\s+|\s*[\n•]\s*", testo):
        f = APERTURE.sub("", f.strip())
        if len(f) < 12 or SCARTA.search(f) or sum(ch.isdigit() for ch in f) > 8:
            continue
        desc += accorcia(f)
    for p in a.get("punti", []):
        if not SCARTA.search(p):
            punti += accorcia(p)
    desc = [ARTICOLO.sub("", f) for f in desc]
    # prime 3 frasi della descrizione, poi alternate con i punti di forza
    frasi = desc[:3]
    resto_d, resto_p = desc[3:], punti
    while resto_d or resto_p:
        if resto_p:
            frasi.append(resto_p.pop(0))
        if resto_d:
            frasi.append(resto_d.pop(0))
    extra = []
    if a.get("camere"):
        extra.append(f"{a['camere']} camer{'a' if a['camere'] == '1' else 'e'} da letto" +
                     (f" e {a['bagni']} bagn{'o' if a['bagni'] == '1' else 'i'}" if a.get("bagni") else ""))
    if a.get("mq"):
        extra.append(f"{a['mq']} metri quadrati")
    if a.get("piano"):
        extra.append("Al piano terra" if a["piano"].lower() in ("0", "terra") else f"Al piano {a['piano']}")
    t = (a.get("titolo", "") + " " + testo).lower()
    for parola, frase in (("piscina", "Con piscina"), ("giardino", "Con giardino"), ("garage", "Con garage"),
                          ("terrazz", "Con terrazzo"), ("camino", "Con camino"), ("vista", "Bella vista"),
                          ("ristruttur", "Ristrutturata")):
        if parola in t:
            extra.append(frase)
    visti, out = set(), []
    for f in frasi + extra:
        f = f[0].upper() + f[1:] if f else f
        chiave = f.lower()[:25]
        if f and chiave not in visti:
            visti.add(chiave)
            out.append(f)
    return out[:quanti]


# ---------------------------------------------------------------- voce narrante
TIPI = ("trilocale", "bilocale", "quadrilocale", "monolocale", "appartamento", "attico", "villa", "villetta",
        "casale", "rustico", "casa", "terreno", "negozio", "ufficio", "capannone", "magazzino", "loft", "garage")


ORDINALI = {"1": "primo", "2": "secondo", "3": "terzo", "4": "quarto", "5": "quinto", "6": "sesto"}
CARATTERISTICHE = [  # (cosa cercare nel testo, frase da mostrare e dire)
    (r"da ristrutturare", "Da ristrutturare"),
    (r"nuova costruzione", "Di nuova costruzione"),
    (r"ristrutturat", "Ristrutturat{o}"),
    (r"piscina", "Con piscina"),
    (r"vista panoramica|panoramic", "Con vista panoramica"),
    (r"giardino", "Con giardino"),
    (r"terrazz", "Con terrazzo"),
    (r"balcon", "Con balcone"),
    (r"camino", "Con camino"),
    (r"cucina abitabile", "Cucina abitabile"),
    (r"garage|box auto|autorimessa", "Con garage"),
    (r"posto auto", "Con posto auto"),
    (r"cantina", "Con cantina"),
    (r"ascensore", "Con ascensore"),
    (r"riscaldamento autonomo|termoautonom", "Riscaldamento autonomo"),
    (r"aria condizionata|climatizz", "Con aria condizionata"),
    (r"fotovoltaic", "Con impianto fotovoltaico"),
    (r"classe energetica a\d?\b|classe a\d?\b", "In classe energetica A"),
    (r"ingresso indipendente", "Ingresso indipendente"),
    (r"doppi servizi", "Doppi servizi"),
    (r"taverna", "Con taverna"),
    (r"mansard", "Con mansarda"),
    (r"soffitta", "Con soffitta"),
    (r"travi a vista|travi in legno", "Con travi a vista"),
    (r"parquet", "Pavimenti in parquet"),
    (r"arredat", "Arredat{o}"),
    (r"porta blindata", "Porta blindata"),
    (r"doppi vetri|infissi nuovi|infissi in", "Infissi di qualità"),
    (r"terreno (di|circostante|agricolo|privato|pertinenziale)|ettari|uliveto|oliveto", "Con terreno"),
    (r"(casa|casale|rustico|villa|edificio|costruzione|colonica)\s+in pietra|pietra a vista", "Costruzione in pietra"),
    (r"centro storico", "Vicino al centro storico"),
    (r"vicin\w*\s+(a|ai)\s+(tutti i\s+)?servizi|servizi a pochi passi|vicino a negozi", "Vicino a tutti i servizi"),
]


def tipo_parola(a):
    t = a["titolo"].lower()
    return next((x for x in TIPI if x in t), "immobile")


def frasi_video(a):
    """frasi brevi e sicure: dati dell'annuncio + caratteristiche trovate nel testo"""
    femminile = tipo_parola(a) in ("villa", "villetta", "casa")
    frasi = []
    if "·" in (a.get("comune") or ""):
        frasi.append("Zona " + a["comune"].split("·")[-1].strip())
    if a.get("mq"):
        frasi.append(f"{a['mq']} metri quadrati")
    if a.get("camere"):
        frasi.append("Una camera da letto" if a["camere"] == "1" else f"{a['camere']} camere da letto")
    if a.get("bagni"):
        frasi.append("Un bagno" if a["bagni"] == "1" else f"{a['bagni']} bagni")
    piano = (a.get("piano") or "").lower()
    if piano in ("0", "terra"):
        frasi.append("Al piano terra")
    elif piano in ORDINALI:
        frasi.append(f"Al {ORDINALI[piano]} piano")
    elif piano == "ultimo":
        frasi.append("All'ultimo piano")
    testo = " ".join([a.get("titolo", ""), a.get("descrizione", ""), " ".join(a.get("punti", []))]).lower()
    for rx, frase in CARATTERISTICHE:
        m = re.search(rx, testo)
        if not m:
            continue
        prima = testo[max(0, m.start() - 20):m.start()]
        if re.search(r"\b(senza|no|privo di|priva di|non)\s+(\w+\s+)?$", prima):
            continue  # "senza ascensore" ecc.
        if frase.startswith("Ristrutturat") and any(f.startswith("Da ristrutturare") for f in frasi):
            continue
        if frase == "Con terreno" and tipo_parola(a) == "terreno":
            continue
        frasi.append(frase.format(o="a" if femminile else "o"))
    return list(dict.fromkeys(frasi))


def prezzo_voce(a):
    m = re.search(r"\d{1,3}(?:\.\d{3})+", a.get("prezzo", ""))
    return f"{m.group(0)} euro" if m else ""


def voce_apertura(a):
    tipo = tipo_parola(a).capitalize()
    dove = a["citta"] or "Umbria"
    p = prezzo_voce(a)
    if a["operazione"] == "ALL'ASTA":
        return f"{tipo} all'asta a {dove}. Base d'asta {p}." if p else f"{tipo} all'asta a {dove}."
    if a["operazione"] == "IN AFFITTO":
        return f"{tipo} in affitto a {dove}, {p} al mese." if p else f"{tipo} in affitto a {dove}."  # canone
    return f"{tipo} in vendita a {dove}, a {p}." if p else f"{tipo} in vendita a {dove}."


def voce_finale(a):
    ag = re.sub(r"\s*[:|]\s*", ", ", a.get("agenzia") or "").strip(", ").title()
    ag = re.sub(r"\b(Srl|Sas|Snc|Spa)\b", "", ag, flags=re.I).strip(" ,")
    parti = [f"Annuncio di {ag}." if ag else "", "Tutte le foto su Cerco Casa Umbria. Link in bio."]
    return " ".join(x for x in parti if x)


def crea_voce(testo, destinazione, voce=None):
    """voce neurale gratuita (edge-tts); se non funziona il video esce senza voce"""
    try:
        subprocess.run([sys.executable, "-m", "edge_tts", "--voice", voce or VOCE, f"--rate={VOCE_VELOCITA}",
                        f"--pitch={VOCE_TONO}", "--text", testo, "--write-media", str(destinazione)],
                       check=True, timeout=120, capture_output=True)
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                              str(destinazione)], capture_output=True, text=True, check=True)
        return float(out.stdout.strip())
    except Exception as e:
        log("  voce non disponibile:", e)
        return None


# ---------------------------------------------------------------- grafica
def font(dim, peso="ExtraBold"):
    f = ImageFont.truetype(str(FONT), dim)
    try:
        f.set_variation_by_name(peso)
    except Exception:
        pass
    return f


def titolo_font(dim, peso="Bold"):
    if not FONT_TITOLI.exists():
        try:
            FONT_TITOLI.parent.mkdir(exist_ok=True)
            FONT_TITOLI.write_bytes(HTTP.get(URL_OSWALD, timeout=60).content)
        except Exception:
            return font(dim, "Black")
    f = ImageFont.truetype(str(FONT_TITOLI), dim)
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


def ombra_testo(d, xy, testo, f, colore="white"):
    d.text((xy[0] + 2, xy[1] + 3), testo, font=f, fill=(0, 0, 0, 160))
    d.text(xy, testo, font=f, fill=colore)


def tipo_immobile(a):
    t = a["titolo"].lower()
    return next((x for x in TIPI if x in t), "immobile").upper()


def livello_apertura(a):
    """stile Moderno: scheda bianca con prezzo, etichetta oro e caratteristiche"""
    lv = sfumatura(300, 0)
    d = ImageDraw.Draw(lv)
    x0, x1 = 60, W - 60
    interno = x1 - x0 - 100
    f_tag, f_tit, f_zona = font(32, "Bold"), font(44, "SemiBold"), font(36, "Medium")
    f_prezzo = font(120, "Black")
    while d.textlength(a["prezzo"], font=f_prezzo) > interno and f_prezzo.size > 70:
        f_prezzo = font(f_prezzo.size - 6, "Black")
    tit = a_capo(d, a["titolo"], f_tit, interno, 2)
    altezza = 50 + 60 + 24 + f_prezzo.size + 22 + len(tit) * 58 + (52 if a["comune"] else 0) + 44
    y1 = H - 470
    y0 = y1 - altezza
    # ombra della scheda
    om = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(om).rounded_rectangle([x0, y0 + 12, x1, y1 + 12], 40, fill=(0, 0, 0, 90))
    lv.alpha_composite(om.filter(ImageFilter.GaussianBlur(18)))
    d = ImageDraw.Draw(lv)
    d.rounded_rectangle([x0, y0, x1, y1], 40, fill=(255, 255, 255, 246))
    op = {"IN VENDITA": "IN VENDITA", "IN AFFITTO": "IN AFFITTO", "ALL'ASTA": "ALL'ASTA"}[a["operazione"]]
    tag = f"{tipo_immobile(a)} · {op}"
    tw = d.textlength(tag, font=f_tag)
    y = y0 + 50
    d.rounded_rectangle([x0 + 50, y, x0 + 50 + tw + 48, y + 60], 30, fill=ORO)
    d.text((x0 + 74, y + 10), tag, font=f_tag, fill="white")
    y += 60 + 24
    d.text((x0 + 46, y - 8), a["prezzo"], font=f_prezzo, fill=SCURO)
    y += f_prezzo.size + 22
    for r in tit:
        d.text((x0 + 52, y), r, font=f_tit, fill=(60, 60, 60))
        y += 58
    if a["comune"]:
        d.text((x0 + 52, y + 4), a["comune"], font=f_zona, fill=ORO)
    # caratteristiche in pillole nere
    x, y = x0, y1 + 30
    for c in [c for c in caratteristiche(a).split("  ·  ") if c]:
        f = font(38, "Bold")
        w = d.textlength(c, font=f) + 56
        d.rounded_rectangle([x, y, x + w, y + 70], 35, fill=(*SCURO, 230))
        d.text((x + 28, y + 12), c, font=f, fill="white")
        x += w + 16
    if not applica_cornice(lv):
        marchio(d, lv)
    return lv


def livello_foto(a, frase=""):
    """stile Moderno: prezzo in pillola bianca e sottotitolo in riquadro bianco con barra oro"""
    lv = sfumatura(300, 0)
    d = ImageDraw.Draw(lv)
    fp = font(54, "Black")
    pw = d.textlength(a["prezzo"], font=fp)
    y0 = 330 if CORNICE.exists() else 130
    d.rounded_rectangle([60, y0, 60 + pw + 60, y0 + 85], 42, fill=(255, 255, 255, 240))
    d.text((90, y0 + 8), a["prezzo"], font=fp, fill=SCURO)
    if a["comune"]:
        ombra_testo(d, (66, y0 + 102), a["comune"], font(38, "Bold"))
    if frase:
        f = font(54, "ExtraBold")
        righe = a_capo(d, frase, f, W - 260, 2)
        tw = max(d.textlength(r, font=f) for r in righe)
        x, y = (W - tw) / 2, H - 760
        h = len(righe) * 72 + 44
        om = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(om).rounded_rectangle([x - 44, y - 22 + 10, x + tw + 44, y + h - 22 + 10], 22, fill=(0, 0, 0, 80))
        lv.alpha_composite(om.filter(ImageFilter.GaussianBlur(14)))
        d = ImageDraw.Draw(lv)
        d.rounded_rectangle([x - 44, y - 22, x + tw + 44, y + h - 22], 22, fill=(255, 255, 255, 246))
        d.rounded_rectangle([x - 44, y - 22, x - 30, y + h - 22], 7, fill=ORO)
        for i, r in enumerate(righe):
            d.text((x, y + i * 72), r, font=f, fill=SCURO)
    if not applica_cornice(lv):
        marchio(d, lv)
    return lv


_cornice_cache = []


def cornice():
    if not _cornice_cache:
        _cornice_cache.append(Image.open(CORNICE).convert("RGBA").resize((W, H), Image.LANCZOS) if CORNICE.exists() else None)
    return _cornice_cache[0]


def applica_cornice(lv):
    """mette la cornice sopra la scena; restituisce True se c'è (allora il logo piccolo non serve)"""
    c = cornice()
    if c is None:
        return False
    lv.alpha_composite(c)
    return True


_logo_cache = {}


def logo(larghezza, altezza):
    """logo ridimensionato per stare dentro larghezza x altezza"""
    chiave = (larghezza, altezza)
    if chiave not in _logo_cache:
        if not LOGO.exists():
            _logo_cache[chiave] = None
        else:
            im = Image.open(LOGO).convert("RGBA")
            im = im.crop(im.getchannel("A").getbbox() or (0, 0, im.width, im.height))
            r = min(larghezza / im.width, altezza / im.height)
            _logo_cache[chiave] = im.resize((round(im.width * r), round(im.height * r)), Image.LANCZOS)
    return _logo_cache[chiave]


def marchio(d, lv=None):
    lg = logo(400, 190) if lv is not None else None
    if lg is not None:
        # ombra leggera per staccarlo dalle foto chiare
        ombra = Image.new("RGBA", lg.size, (0, 0, 0, 0))
        ombra.putalpha(lg.getchannel("A").point(lambda v: v * 0.55))
        ombra = ombra.filter(ImageFilter.GaussianBlur(6))
        x, y = W - lg.width - 32, 36
        lv.alpha_composite(ombra, (x + 3, y + 4))
        lv.alpha_composite(lg, (x, y))
        return
    f = font(36, "Bold")
    t = "CERCOCASA UMBRIA"
    d.text(((W - d.textlength(t, font=f)) / 2, 58), t, font=f, fill=(255, 255, 255, 230))


def immagine_finale(a, sfondo):
    """chiusura: logo tondo, marchio, agenzia e invito al link"""
    oro2 = (236, 190, 72)
    img = ImageOps.fit(sfondo, (W, H)).filter(ImageFilter.GaussianBlur(30)).convert("RGBA")
    img = Image.alpha_composite(img, Image.new("RGBA", (W, H), (14, 14, 15, 222)))
    d = ImageDraw.Draw(img)

    def centra(testo, y, f, colore="white"):
        d.text(((W - d.textlength(testo, font=f)) / 2, y), testo, font=f, fill=colore)

    lg = logo(460, 460)
    if lg is not None:
        om = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        x, y = (W - lg.width) // 2, 230
        om.paste((0, 0, 0, 180), (x + 8, y + 14), lg.getchannel("A"))
        img.alpha_composite(om.filter(ImageFilter.GaussianBlur(14)))
        img.alpha_composite(lg, (x, y))
        d = ImageDraw.Draw(img)
    ft = titolo_font(112)
    a1, a2 = "CERCOCASA", "UMBRIA"
    tot = d.textlength(a1, font=ft) + 16 + d.textlength(a2, font=ft)
    x = (W - tot) / 2
    d.text((x, 735), a1, font=ft, fill=oro2)
    d.text((x + d.textlength(a1, font=ft) + 16, 735), a2, font=ft, fill=(242, 242, 242))
    centra("IL PORTALE IMMOBILIARE DELL'UMBRIA", 895, font(32, "SemiBold"), (205, 205, 205))
    d.rectangle([W / 2 - 90, 975, W / 2 + 90, 980], fill=ORO)
    if a["agenzia"]:
        centra("Annuncio di", 1030, font(40, "Medium"), (215, 215, 215))
        for i, r in enumerate(a_capo(d, a["agenzia"], font(52, "Bold"), W - 160, 2)):
            centra(r, 1085 + i * 66, font(52, "Bold"))
    pillola(d, (0, 1300), "LINK IN BIO", font(58, "Black"), ORO, "white", (50, 24), centro=True)
    fu = titolo_font(70)
    p1, p2, p3 = "www.", "cercocasa", "umbria.it"
    tot = sum(d.textlength(t, font=fu) for t in (p1, p2, p3))
    x = (W - tot) / 2
    for t, col in ((p1, (240, 240, 240)), (p2, oro2), (p3, (240, 240, 240))):
        d.text((x, 1455), t, font=fu, fill=col)
        x += d.textlength(t, font=fu)
    centra(f"Codice annuncio {a['id']}", 1570, font(36, "Medium"), (190, 190, 190))
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


def clip_foto(fp, lv, dur, i, tmp):
    base = copri(Image.open(fp))
    base_p, lv_p, out = tmp / f"b{i}.jpg", tmp / f"l{i}.png", tmp / f"c{i}.mp4"
    base.save(base_p, quality=92)
    lv.save(lv_p)
    if i % 2 == 0:
        x, y = f"(iw-{W})*t/{dur}", f"(ih-{H})*t/{dur}"
    else:
        x, y = f"(iw-{W})*(1-t/{dur})", f"(ih-{H})*(1-t/{dur})"
    ff("-loop", "1", "-t", dur, "-i", base_p, "-i", lv_p,
       "-filter_complex", f"[0:v]crop={W}:{H}:x='{x}':y='{y}',fps={FPS},format=yuv420p[b];[b][1:v]overlay=0:0,format=yuv420p",
       "-t", dur, "-r", FPS, "-c:v", "libx264", "-preset", "ultrafast", "-crf", "17", out)
    return out


def crea_video(a, foto_locali, destinazione):
    tmp = Path(tempfile.mkdtemp())
    foto_locali = foto_locali[:MAX_FOTO]
    frasi = frasi_video(a)[:max(0, min(10, len(foto_locali) - 1))]
    extra = max(0, min(7, len(foto_locali) - 1) - len(frasi))      # almeno 8 foto quando ci sono
    # scene: (foto, frase sullo schermo, testo detto dalla voce)
    scene = [(foto_locali[0], None, voce_apertura(a))]
    for i, f in enumerate(frasi):
        scene.append((foto_locali[i + 1], f, f + "."))
    for j in range(extra):
        scene.append((foto_locali[len(frasi) + 1 + j], "", ""))
    scene.append((None, None, voce_finale(a)))

    # voce: un pezzo per scena, così è sempre sincronizzata con le scritte
    voci, con_voce = [], True
    for k, (_, _, detto) in enumerate(scene):
        d = crea_voce(detto, tmp / f"v{k}.mp3") if (detto and con_voce) else None
        if detto and d is None:
            con_voce = False
        voci.append(d)
    if not con_voce:
        voci = [None] * len(scene)
    else:
        log(f"  voce: {sum(v or 0 for v in voci):.1f} s in {len(scene)} scene")

    clip = []
    for k, (fp, frase, _) in enumerate(scene):
        minimo = 4.0 if k == 0 or fp is None else 3.2
        dur = max(minimo, (voci[k] or 0) + 0.8 + DISSOLVENZA + (0.2 if k else 0))
        if fp is None:      # schermata finale
            fin_p, out = tmp / "fine.jpg", tmp / "cfine.mp4"
            immagine_finale(a, Image.open(foto_locali[0])).save(fin_p, quality=92)
            ff("-loop", "1", "-t", dur, "-i", fin_p, "-vf", f"fps={FPS},format=yuv420p", "-t", dur,
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", out)
        else:
            lv = livello_apertura(a) if k == 0 else livello_foto(a, frase)
            out = clip_foto(fp, lv, dur, k, tmp)
        clip.append((out, dur))

    # unione con dissolvenze
    ingressi, filtri, prec, t, inizi = [], [], "0:v", 0.0, [0.0]
    for c, _ in clip:
        ingressi += ["-i", c]
    for k in range(1, len(clip)):
        t += clip[k - 1][1] - DISSOLVENZA
        inizi.append(t)
        filtri.append(f"[{prec}][{k}:v]xfade=transition=fade:duration={DISSOLVENZA}:offset={t:.2f}[v{k}]")
        prec = f"v{k}"
    durata = sum(d for _, d in clip) - DISSOLVENZA * (len(clip) - 1)

    n = len(clip)
    brani = sorted(glob.glob(str(MUSICA / "*.mp3")) + glob.glob(str(MUSICA / "*.m4a")))
    if brani:
        audio = ["-stream_loop", "-1", "-i", random.choice(brani)]
        vol = 0.15 if con_voce else 0.8
        afiltro = f";[{n}:a]atrim=0:{durata:.2f},afade=t=in:d=0.5,afade=t=out:st={durata - 1.2:.2f}:d=1.2,volume={vol}[m]"
    else:
        audio = ["-f", "lavfi", "-t", f"{durata:.2f}", "-i", "anullsrc=r=44100:cl=stereo"]
        afiltro = f";[{n}:a]anull[m]"
    pezzi, idx = [], n + 1
    for k, d in enumerate(voci):
        if not d:
            continue
        audio += ["-i", tmp / f"v{k}.mp3"]
        ms = int((inizi[k] + (0.25 if k == 0 else DISSOLVENZA * 0.6)) * 1000)
        afiltro += f";[{idx}:a]aformat=sample_rates=44100:channel_layouts=stereo,adelay={ms}|{ms},volume=1.5[p{k}]"
        pezzi.append(f"[p{k}]")
        idx += 1
    if pezzi:
        afiltro += f";[m]{''.join(pezzi)}amix=inputs={len(pezzi) + 1}:duration=first:normalize=0[a]"
    else:
        afiltro += ";[m]anull[a]"
    ff(*ingressi, *audio, "-filter_complex", ";".join(filtri) + f";[{prec}]format=yuv420p[v]" + afiltro,
       "-map", "[v]", "-map", "[a]", "-t", f"{durata:.2f}",
       "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-profile:v", "high", "-pix_fmt", "yuv420p",
       "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-movflags", "+faststart", destinazione)
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
    prov = "#perugia" if a.get("provincia") == "PG" or a.get("rivista") == "Perugia" else (
        "#terni" if a.get("provincia") == "TR" or a.get("rivista") == "Terni" else "")
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


ULTIMO_VIDEO_FB = {}


def url_video_facebook(vid, token, attesa=240):
    """indirizzo pubblico del video appena pubblicato su Facebook (serve a Instagram)"""
    fine = time.time() + attesa
    while time.time() < fine:
        r = HTTP.get(f"{GRAPH}/{vid}", params={"fields": "source", "access_token": token}, timeout=30)
        if r.ok and r.json().get("source"):
            return r.json()["source"]
        time.sleep(15)
    return None


def attendi_e_pubblica_ig(ig, cont, token):
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


def url_pubblico_github(video):
    """mette il video in un ramo pubblico 'ig-video' del repository e restituisce l'indirizzo diretto"""
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not repo:
        return None
    try:
        auth = subprocess.run(["git", "-C", str(QUI), "config", "--get", "http.https://github.com/.extraheader"],
                              capture_output=True, text=True).stdout.strip()
        tmp = Path(tempfile.mkdtemp())
        nome = f"reel-{datetime.now().strftime('%Y%m%d-%H%M%S')}.mp4"
        shutil.copy(video, tmp / nome)
        def g(*a):
            pre = ["git", "-C", str(tmp)] + (["-c", f"http.https://github.com/.extraheader={auth}"] if auth else [])
            subprocess.run(pre + list(a), check=True, capture_output=True, text=True)
        g("init", "-q")
        g("checkout", "-q", "-b", "ig-video")
        g("config", "user.name", "cercocasa-bot")
        g("config", "user.email", "bot@cercocasaumbria.it")
        g("add", nome)
        g("commit", "-q", "-m", "video per Instagram")
        g("push", "-q", "-f", f"https://github.com/{repo}.git", "ig-video")
        url = f"https://raw.githubusercontent.com/{repo}/ig-video/{nome}"
        for _ in range(12):
            time.sleep(5)
            if HTTP.head(url, timeout=30, allow_redirects=True).status_code == 200:
                return url
        log("  Instagram: il video non è raggiungibile da fuori (il repository deve essere pubblico)")
    except subprocess.CalledProcessError as e:
        log("  Instagram: non riesco a pubblicare il video su GitHub:", (e.stderr or "")[-300:])
    except Exception as e:
        log("  Instagram: errore indirizzo pubblico:", e)
    return None


def versione_instagram(video):
    """copia del video con le specifiche consigliate da Instagram per i Reels"""
    dest = Path(video).with_name(Path(video).stem + "-ig.mp4")
    try:
        ff("-i", video, "-vf", "scale=1080:1920,setsar=1,fps=30,format=yuv420p",
           "-c:v", "libx264", "-profile:v", "main", "-level", "4.0", "-preset", "veryfast",
           "-b:v", "4500k", "-maxrate", "5000k", "-bufsize", "10000k", "-g", "60", "-r", "30",
           "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2",
           "-movflags", "+faststart", dest)
        return dest
    except Exception as e:
        log("  copia per Instagram non creata:", e)
        return video


def pubblica_instagram(video, testo):
    ig, token = os.environ.get("IG_USER_ID"), os.environ.get("IG_TOKEN")
    if not (ig and token):
        log("Instagram: chiavi non configurate, salto")
        return None
    # metodo 0: Instagram scarica il video da un indirizzo pubblico su GitHub (non di Meta)
    url_pub = url_pubblico_github(versione_instagram(video))
    if url_pub:
        try:
            r = HTTP.post(f"{GRAPH}/{ig}/media", data={"media_type": "REELS", "video_url": url_pub, "caption": testo,
                                                     "share_to_feed": "true", "access_token": token}, timeout=60)
            r.raise_for_status()
            log("  Instagram: video consegnato da GitHub, attendo l'elaborazione")
            return attendi_e_pubblica_ig(ig, r.json()["id"], token)
        except Exception as e:
            log("  Instagram (da GitHub) non riuscito:", (getattr(getattr(e, "response", None), "text", "") or str(e))[:300])
    # metodo 1: Instagram scarica il video già pubblicato su Facebook
    if not ULTIMO_VIDEO_FB.get("id") and os.environ.get("FB_PAGE_ID"):
        try:
            pagina = os.environ["FB_PAGE_ID"]
            r = HTTP.get(f"{GRAPH}/{pagina}/videos", params={"fields": "id,created_time", "limit": 1,
                                                            "access_token": token}, timeout=30)
            dati_v = r.json().get("data") or []
            if dati_v:
                ULTIMO_VIDEO_FB.update(id=dati_v[0]["id"], token=token)
                log("  Instagram: uso l'ultimo video della Pagina", dati_v[0]["id"])
            else:
                log("  Instagram: nessun video trovato sulla Pagina", r.text[:200])
        except Exception as e:
            log("  Instagram: non trovo il video della Pagina:", e)
    if ULTIMO_VIDEO_FB.get("id"):
        url = url_video_facebook(ULTIMO_VIDEO_FB["id"], ULTIMO_VIDEO_FB["token"])
        if not url:
            log("  Instagram: Facebook non ha dato l'indirizzo del video")
        if url:
            try:
                r = HTTP.post(f"{GRAPH}/{ig}/media", data={"media_type": "REELS", "video_url": url, "caption": testo,
                                                         "share_to_feed": "true", "access_token": token}, timeout=60)
                r.raise_for_status()
                return attendi_e_pubblica_ig(ig, r.json()["id"], token)
            except Exception as e:
                log("  Instagram (da Facebook) non riuscito:", e, (getattr(getattr(e, "response", None), "text", "") or "")[:300])
    # metodo 2: caricamento a Instagram, provando i 3 modi documentati da Meta
    video = versione_instagram(video)
    dati = Path(video).read_bytes()
    url_fb = None
    if ULTIMO_VIDEO_FB.get("id"):
        url_fb = url_video_facebook(ULTIMO_VIDEO_FB["id"], ULTIMO_VIDEO_FB["token"], attesa=30)
    modi = [("chiave nell'indirizzo", "query"), ("chiave nell'intestazione", "header")]
    if url_fb:
        modi.append(("file da indirizzo", "file_url"))
    ultimo = None
    for nome_modo, modo in modi:
        try:
            r = HTTP.post(f"{GRAPH}/{ig}/media", data={
                "media_type": "REELS", "upload_type": "resumable", "caption": testo,
                "share_to_feed": "true", "access_token": token}, timeout=60)
            r.raise_for_status()
            cont = r.json()["id"]
            uri = r.json().get("uri") or f"https://rupload.facebook.com/ig-api-upload/v21.0/{cont}"
            if modo == "query":
                r = HTTP.post(uri, params={"access_token": token}, data=dati, timeout=300,
                              headers={"offset": "0", "file_size": str(len(dati))})
            elif modo == "header":
                r = HTTP.post(uri, data=dati, timeout=300, headers={
                    "Authorization": f"OAuth {token}", "offset": "0", "file_size": str(len(dati))})
            else:
                r = HTTP.post(uri, timeout=120, headers={"Authorization": f"OAuth {token}", "file_url": url_fb})
            r.raise_for_status()
            log(f"  Instagram: caricamento riuscito ({nome_modo})")
            return attendi_e_pubblica_ig(ig, cont, token)
        except Exception as e:
            ultimo = e
            log(f"  Instagram ({nome_modo}) non riuscito:",
                (getattr(getattr(e, "response", None), "text", "") or str(e))[:300])
            time.sleep(5)
    raise ultimo


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
    ULTIMO_VIDEO_FB.update(id=vid, token=token)
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


GIORNI_IT = ["lunedi", "martedi", "mercoledi", "giovedi", "venerdi", "sabato", "domenica"]
MESI_IT = ["gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic"]


def settimana(stato, args, giorni, inizio=1):
    """prepara i post di N giorni, da programmare a mano su Meta Business Suite e TikTok Studio:
    ogni giorno 1 video per Facebook+Instagram e 1 video (altra agenzia) per TikTok"""
    from datetime import timedelta
    oggi = datetime.now()
    prova = USCITA / "00-PROVA-VOCI"
    prova.mkdir(parents=True, exist_ok=True)
    for i, v in enumerate(VOCI_PROVA, 1):
        nome = v.replace("it-IT-", "").replace("MultilingualNeural", "").replace("Neural", "")
        crea_voce("Villa in vendita a Todi, a 330.000 euro. Con giardino e piscina. "
                  "Tutte le foto su Cerco Casa Umbria. Link in bio.", prova / f"{i}-{nome}.mp3", v)
    calendario = ["CALENDARIO POST CERCOCASA UMBRIA", "=" * 34, ""]
    fatti = 0
    partenza = time.time()
    for k in range(giorni):
        if time.time() - INIZIO > 22 * 60:
            log("Tempo quasi finito: salvo i giorni già pronti, gli altri li preparo la prossima volta.")
            break
        g = inizio + k
        giorno = oggi + timedelta(days=g)
        etichetta = f"{k + 1:02d}-{GIORNI_IT[giorno.weekday()]}-{giorno.day:02d}-{MESI_IT[giorno.month - 1]}"
        cartella = USCITA / etichetta
        cartella.mkdir(parents=True, exist_ok=True)
        calendario.append(f"{GIORNI_IT[giorno.weekday()].upper()} {giorno.day} {MESI_IT[giorno.month - 1]}  (cartella {etichetta})")
        for nome_file, gruppo in (("FACEBOOK-INSTAGRAM", ["facebook", "instagram"]), ("TIKTOK", ["tiktok"])):
            a = scegli_annuncio(stato)
            if not a:
                log("Nessun annuncio nuovo disponibile per", etichetta, nome_file)
                continue
            stato["pubblicati"].append({"id": a["id"], "agenzia": a["agenzia"], "agenzia_id": a.get("agenzia_id"),
                                        "rivista": a.get("rivista"), "social": gruppo,
                                        "data": giorno.strftime("%Y-%m-%d")})
            video = prepara(a, args)
            if not video:
                continue
            shutil.move(str(video), cartella / f"{nome_file}.mp4")
            for nome in gruppo:
                (cartella / f"testo-{nome}.txt").write_text(testo_post(a, nome), encoding="utf-8")
            calendario.append(f"   {nome_file:<20} {a['prezzo']:<12} {a['citta'] or ''} – {a['agenzia']}")
            fatti += 1
        calendario.append("")
    calendario += ["COME PROGRAMMARE:",
                   "- Meta Business Suite: Crea Reel -> carica FACEBOOK-INSTAGRAM.mp4 -> spunta Facebook e Instagram",
                   "  -> incolla testo-instagram.txt (e personalizza Facebook con testo-facebook.txt) -> Programma: giorno indicato, ore 8:30",
                   "- TikTok Studio (computer): Carica -> TIKTOK.mp4 -> incolla testo-tiktok.txt -> Programma: giorno indicato, ore 8:30"]
    (USCITA / "00-CALENDARIO.txt").write_text("\n".join(calendario), encoding="utf-8")
    STATO.write_text(json.dumps(stato, ensure_ascii=False, indent=1))
    log(f"Pronti {fatti} video per {giorni} giorni")


def pubblica_oggi(stato, args):
    """ogni mattina: un annuncio nuovo pubblicato da solo su Facebook (e Instagram se configurato)"""
    oggi = datetime.now().strftime("%Y-%m-%d")
    social = []
    if os.environ.get("FB_PAGE_ID") and (os.environ.get("FB_PAGE_TOKEN") or os.environ.get("IG_TOKEN")):
        social.append("facebook")
    if os.environ.get("IG_USER_ID") and os.environ.get("IG_TOKEN") and os.environ.get("AUTO_INSTAGRAM", "si") == "si":
        social.append("instagram")
    if not social:
        return
    gia = next((p for p in stato["pubblicati"] if p.get("auto") == oggi), None)
    if gia:
        mancano = [x for x in social if x not in gia.get("social", [])]
        if not mancano:
            log("Il post automatico di oggi è già stato pubblicato.")
            return
        log("Completo il post di oggi su:", ", ".join(mancano))
        try:
            a = leggi_annuncio(gia["id"])
        except Exception as e:
            log("  annuncio di oggi non leggibile:", e)
            return
        a["agenzia"] = gia.get("agenzia") or a["agenzia"]
        a["agenzia_id"], a["rivista"] = gia.get("agenzia_id"), gia.get("rivista")
        if gia.get("fb_video"):
            ULTIMO_VIDEO_FB.update(id=gia["fb_video"], token=os.environ.get("FB_PAGE_TOKEN") or os.environ.get("IG_TOKEN"))
        voce = gia
        social = mancano
    else:
        a = scegli_annuncio(stato)
        if not a:
            log("Nessun annuncio nuovo da pubblicare oggi.")
            return
        voce = {"id": a["id"], "agenzia": a["agenzia"], "agenzia_id": a.get("agenzia_id"),
                "rivista": a.get("rivista"), "social": [], "auto": oggi,
                "data": datetime.now().isoformat(timespec="minutes")}
        stato["pubblicati"].append(voce)
    video = prepara(a, args)
    if not video:
        return
    for nome in social:
        try:
            ris = PUBBLICA[nome](video, testo_post(a, nome))
            voce["social"].append(nome)
            if nome == "facebook" and ris:
                voce["fb_video"] = ris
        except Exception as e:
            dettagli = getattr(getattr(e, "response", None), "text", "")
            log(f"{nome}: ERRORE", e, (dettagli or "")[:800])
    STATO.write_text(json.dumps(stato, ensure_ascii=False, indent=1))
    log("Pubblicato in automatico su:", ", ".join(voce["social"]) or "nessuno")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prova", action="store_true", help="crea i video senza pubblicare")
    ap.add_argument("--id", type=int, help="annuncio preciso")
    ap.add_argument("--foto", help="cartella di foto locali (per test)")
    ap.add_argument("--dati", help="file json con i dati dell'annuncio (per test)")
    ap.add_argument("--giorni", type=int, default=int(os.environ.get("GIORNI", "0") or 0),
                    help="prepara i post di N giorni da programmare a mano")
    args = ap.parse_args()

    stato = carica_stato()
    USCITA.mkdir(exist_ok=True)
    social = [x.strip() for x in os.environ.get("SOCIAL", "facebook,instagram,tiktok").split(",") if x.strip()]
    # diversi = un annuncio (e un'agenzia) diverso per ogni social; uguale = stesso video ovunque
    modo = os.environ.get("MODO_POST", "diversi")
    if not (args.dati or args.id) and not args.prova:
        pubblica_oggi(stato, args)
    if not (args.dati or args.id):
        # una volta a settimana prepara i 7 giorni successivi; negli altri giorni non fa niente
        from datetime import date, timedelta
        oggi = date.today()
        if stato.get("versione") != VERSIONE:
            # grafica/voce cambiate: rifà i giorni futuri già preparati
            stato["pubblicati"] = [p for p in stato["pubblicati"] if not (
                isinstance(p.get("data"), str) and len(p["data"]) == 10 and date.fromisoformat(p["data"]) > oggi)]
            stato["versione"] = VERSIONE
        future = [date.fromisoformat(p["data"]) for p in stato["pubblicati"]
                  if isinstance(p.get("data"), str) and len(p["data"]) == 10]
        ultimo = max(future) if future else None
        if ultimo and ultimo >= oggi + timedelta(days=1):
            log(f"I post sono già pronti fino al {ultimo.strftime('%d/%m')}: oggi non serve fare niente.")
            return
        inizio = 1 if not ultimo or ultimo < oggi else (ultimo - oggi).days + 1
        settimana(stato, args, args.giorni or 7, inizio)
        return

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
