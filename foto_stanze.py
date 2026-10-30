"""Riconosce cosa mostra ogni foto dell'annuncio (bagno, cucina, camera, giardino...) e abbina
ogni frase del video alla foto giusta. Se nessuna foto corrisponde, usa una pagina neutra con il logo.

Il riconoscimento usa CLIP (modello aperto, gira sul computer di GitHub senza chiavi).
Se il modello non è disponibile, le frasi su una stanza precisa vanno sulla pagina neutra:
meglio il logo che una foto sbagliata."""
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

QUI = Path(__file__).resolve().parent

# categoria -> descrizioni in inglese per il modello
CATEGORIE = {
    "bagno": ["a photo of a bathroom with toilet, sink and shower", "a bathroom interior"],
    "cucina": ["a photo of a kitchen with cabinets and stove", "a kitchen interior"],
    "camera": ["a photo of a bedroom with a bed", "a bedroom interior"],
    "soggiorno": ["a photo of a living room with sofa", "a living room interior", "a dining room"],
    "camino": ["a fireplace in a room"],
    "esterno": ["the exterior facade of a house or building", "an apartment building seen from the street"],
    "giardino": ["a garden with lawn and plants", "a private garden of a house"],
    "terrazzo": ["a balcony or terrace of an apartment", "a terrace with a view"],
    "garage": ["a garage or parking space", "a car parking area"],
    "piscina": ["a swimming pool"],
    "vista": ["a panoramic view of the landscape", "a view of hills and countryside"],
    "terreno": ["agricultural land, field or olive grove"],
    "mansarda": ["an attic room under the roof"],
    "cantina": ["a cellar or basement", "a tavern room in the basement"],
    "stanza": ["an empty room", "a corridor or hallway", "stairs inside a house"],
    "documento": ["a floor plan drawing", "a map", "a document with text", "a logo"],
}

# frase del video -> categoria di foto che deve mostrare (None = frase generica, va bene una foto qualsiasi)
FRASI_FOTO = [
    (r"camer[ae] da letto", "camera"),
    (r"\bbagn|doppi servizi", "bagno"),
    (r"cucina", "cucina"),
    (r"giardino", "giardino"),
    (r"terrazz|balcon", "terrazzo"),
    (r"garage|posto auto|box auto", "garage"),
    (r"piscina", "piscina"),
    (r"vista panoramica|panoram", "vista"),
    (r"camino", "camino"),
    (r"con terreno|uliveto|oliveto", "terreno"),
    (r"mansard|soffitta", "mansarda"),
    (r"cantina|taverna", "cantina"),
    (r"soggiorno|salone|salotto", "soggiorno"),
    (r"costruzione in pietra", "esterno"),
    (r"ascensore|porta blindata", "nessuna"),   # quasi mai fotografati: pagina neutra
]
# per le frasi generiche (metri quadri, zona, piano, prezzo...) le foto migliori sono queste
GENERICHE_PREFERITE = ["esterno", "soggiorno", "stanza", "vista", "terrazzo", "giardino", "cucina", "camera"]

_modello = None


def _carica():
    global _modello
    if _modello is None:
        try:
            import open_clip
            import torch
            m, _, prep = open_clip.create_model_and_transforms("ViT-B-32", pretrained="laion2b_s34b_b79k")
            tok = open_clip.get_tokenizer("ViT-B-32")
            m.eval()
            etichette, testi = [], []
            for cat, frasi in CATEGORIE.items():
                for f in frasi:
                    etichette.append(cat)
                    testi.append(f)
            with torch.no_grad():
                t = m.encode_text(tok(testi))
                t = t / t.norm(dim=-1, keepdim=True)
            _modello = (m, prep, t, etichette, torch)
        except Exception as e:  # modello non disponibile: lo dico una volta e vado avanti
            print("  riconoscimento foto non disponibile:", e, flush=True)
            _modello = False
    return _modello or None


def classifica(foto):
    """{percorso: (categoria, sicurezza 0-1)}; vuoto se il modello non c'è"""
    mod = _carica()
    if not mod:
        return {}
    m, prep, t, etichette, torch = mod
    out = {}
    for f in foto:
        try:
            with torch.no_grad():
                im = prep(Image.open(f).convert("RGB")).unsqueeze(0)
                v = m.encode_image(im)
                v = v / v.norm(dim=-1, keepdim=True)
                p = (100 * v @ t.T).softmax(dim=-1)[0]
            per_cat = {}
            for e, x in zip(etichette, p.tolist()):
                per_cat[e] = per_cat.get(e, 0) + x
            cat = max(per_cat, key=per_cat.get)
            out[str(f)] = (cat, per_cat[cat], per_cat)
        except Exception as e:
            print("  foto non riconosciuta:", f, e, flush=True)
    return out


def categoria_frase(frase):
    f = frase.lower()
    for rx, cat in FRASI_FOTO:
        if re.search(rx, f):
            return cat
    return None


def pagina_neutra(cartella, accento="#DB9C12"):
    """foto 'neutra': fondo scuro con il logo tondo Cercocasa al centro"""
    p = Path(cartella) / "neutra.jpg"
    if p.exists():
        return p
    W, H = 1600, 1200
    im = Image.new("RGB", (W, H), (24, 24, 26))
    d = ImageDraw.Draw(im)
    # alone morbido del colore del giorno
    r, g, b = int(accento[1:3], 16), int(accento[3:5], 16), int(accento[5:7], 16)
    for k in range(40, 0, -1):
        a = k / 40
        col = tuple(int(24 + (c - 24) * 0.18 * (1 - a)) for c in (r, g, b))
        d.ellipse([W / 2 - 520 * a, H / 2 - 520 * a, W / 2 + 520 * a, H / 2 + 520 * a], fill=col)
    logo = Image.open(QUI / "tondo-annuncio.png").convert("RGBA")
    logo.thumbnail((560, 560))
    im.paste(logo, ((W - logo.width) // 2, (H - logo.height) // 2 - 40), logo)
    try:
        font = ImageFont.truetype(str(QUI / "font" / "Montserrat.ttf"), 46)
    except Exception:
        font = ImageFont.load_default()
    testo = "cercocasaumbria.it"
    w = d.textbbox((0, 0), testo, font=font)[2]
    d.text(((W - w) / 2, H / 2 + 280), testo, font=font, fill=(235, 235, 235))
    im.save(p, quality=90)
    return p


def abbina(frasi, foto, cartella, accento="#DB9C12", log=print):
    """per ogni frase la foto giusta. foto[0] è la copertina (apertura e chiusura) e non viene usata qui.
    Restituisce la lista di foto, una per frase."""
    altre = list(foto[1:])
    info = classifica(foto)
    usate, scelte = set(), [None] * len(frasi)
    if info:
        log("  foto riconosciute: " + ", ".join(f"{Path(f).name}={c}" for f, (c, *_r) in info.items()))

    def migliore(cat):
        cand = [(info[str(f)][2].get(cat, 0), f) for f in altre if str(f) in info and f not in usate
                and info[str(f)][0] == cat]
        return max(cand)[1] if cand else None

    # 1) frasi su una stanza precisa: solo la foto di quella stanza, altrimenti pagina neutra
    for i, fr in enumerate(frasi):
        cat = categoria_frase(fr)
        if cat is None:
            continue
        f = migliore(cat) if (info and cat != "nessuna") else None
        if f is None and cat == "esterno":
            f = foto[0]
        scelte[i] = f or pagina_neutra(cartella, accento)
        if f is not None and f != foto[0]:
            usate.add(f)
        log(f"  «{fr}» -> {cat}: {Path(scelte[i]).name}")

    # 2) frasi generiche: le foto rimaste, prima esterni e soggiorni (mai documenti)
    def ordine(f):
        c = info.get(str(f), ("stanza",))[0]
        return GENERICHE_PREFERITE.index(c) if c in GENERICHE_PREFERITE else (99 if c == "documento" else 50)

    rimaste = sorted([f for f in altre if f not in usate and ordine(f) < 99], key=ordine)
    for i, fr in enumerate(frasi):
        if scelte[i] is None:
            scelte[i] = rimaste.pop(0) if rimaste else foto[0]
    return scelte
