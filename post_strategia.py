#!/usr/bin/env python3
"""Il post del pomeriggio: un Reel al giorno per far crescere il profilo Instagram, con un tema per ogni giorno.

  lunedì     andamento del mercato (prezzi degli annunci sul portale)
  martedì    Reel dedicato a un immobile
  mercoledì  consigli per vendere o comprare casa      (strategia/consigli.json)
  giovedì    presentazione di un'agenzia               (agenzie_rivista.json)
  venerdì    le 5 proposte della settimana
  sabato     immobili di prestigio
  domenica   curiosità sui borghi umbri                (strategia/borghi.json)

I post della mattina (sei_post.py) restano come sono: questo è un post in più, solo per Instagram.
Video verticale 1080x1920, 20-35 secondi, titolo nei primi due secondi (senza sigla), foto in movimento,
sottotitoli sincronizzati con la voce, logo sempre visibile, invito finale a seguire Cercocasa Umbria.

  python post_strategia.py --prova              crea video e testo di oggi, non pubblica
  python post_strategia.py --prova --tema top5  prova un tema preciso
  python post_strategia.py                      crea e pubblica su Instagram
"""
import argparse
import json
import os
import re
import shutil
import statistics
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

import cercocasa_social as cs
import sei_post as sp

QUI = Path(__file__).resolve().parent
DATI = QUI / "strategia"
STATO = QUI / "strategia.json"
GRAFICA = QUI / "grafica" / "strategia.html"
W, H, FPS = 1080, 1920, 30
TEMI = ["mercato", "immobile", "consigli", "agenzia", "top5", "prestigio", "borghi"]      # lunedì ... domenica
NOMI_GIORNO = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]
PROFILO = os.environ.get("IG_PROFILO", "@cercocasadovecome")
VELOCITA = os.environ.get("VOCE_STRATEGIA_VELOCITA", "+3%")
DURATA_MIN, DURATA_MAX = 20000, 35000
CODA = (f"\n\nSegui {PROFILO} per nuove case ogni giorno.\n"
        "Tutti gli annunci su www.cercocasaumbria.it (link in bio)")
TAG = "#umbria #cercocasaumbria #immobiliare #casa #caseinvendita"


# ---------------------------------------------------------------- memoria
def carica_stato():
    if STATO.exists():
        return json.loads(STATO.read_text(encoding="utf-8"))
    return {"pubblicati": []}


def recenti(stato, tema, giorni):
    limite = (date.today() - timedelta(days=giorni)).isoformat()
    return [p for p in stato["pubblicati"] if p.get("tema") == tema and str(p.get("data", ""))[:10] >= limite]


def ids_recenti(stato, tema, giorni):
    return {i for p in recenti(stato, tema, giorni) for i in p.get("ids", [])}


def turno(stato, tema, quanti):
    """a turno: quante volte è già uscito questo tema (così ogni settimana tocca al successivo)"""
    return len([p for p in stato["pubblicati"] if p.get("tema") == tema]) % max(quanti, 1)


# ---------------------------------------------------------------- annunci del portale
def elenco(tipo, citta):
    """annunci della prima pagina del portale (i più recenti) per tipo e città, solo quelli completi"""
    pagina = {"vendita": "/case-vendita/", "affitto": "/case-affitto/"}[tipo] + citta + "/"
    out = []
    try:
        schede = sp.leggi_elenco(tipo, pagina)
    except Exception as e:
        cs.log("  elenco non leggibile", pagina, e)
        return out
    for x in schede:
        if not x["id"] or not x["foto"] or x["prezzo"] <= 0 or "mappa" in x["foto"].lower():
            continue
        if re.search(r"all.asta|\basta\b", x.get("titolo", ""), re.I):
            continue
        x["tipo"], x["citta"] = tipo, citta
        out.append(x)
    return out


def case(schede):
    return [x for x in schede if not sp.NON_CASE.search(x["tipo_imm"] + " " + x["titolo"])]


def voce_di(x, chiave):
    return next((v[1] for v in x.get("voci", []) if v[0] == chiave), "")


def mq_di(x):
    m = re.search(r"(\d[\d.]*)", voce_di(x, "area"))
    return int(m.group(1).replace(".", "")) if m else 0


def euro(n):
    return "€ " + f"{int(n):,}".replace(",", ".")


def euro_voce(n):
    return f"{int(n):,}".replace(",", ".") + " euro"


def tondo(n, passo=1000):
    return int(round(n / passo) * passo)


def luogo(x):
    citta, zona = x["citta"].title(), (x.get("zona") or "").strip().title()
    return f"{citta} · {zona}" if zona and zona.lower() != citta.lower() else citta


def scarica_foto(url, cartella, nome):
    """una foto del portale in jpg; None se non si riesce"""
    try:
        r = cs.HTTP.get(url, timeout=60)
        r.raise_for_status()
        grezzo = cartella / f"{nome}-orig{Path(url.split('?')[0]).suffix or '.jpg'}"
        grezzo.write_bytes(r.content)
        jpg = cartella / f"{nome}.jpg"
        cs.ff("-i", grezzo, "-vf", "scale='min(1600,iw)':-2", "-q:v", "3", jpg)
        return jpg
    except Exception as e:
        cs.log("  foto saltata", url, e)
        return None


def u(f):
    return "file://" + str(f) if f else ""


def maiuscola(t):
    t = (t or "").strip()
    return t[:1].upper() + t[1:]


# ---------------------------------------------------------------- i sette temi
def tema_mercato(stato, cartella):
    """Lunedì: i prezzi degli annunci sul portale, una settimana Perugia e una Terni. Solo numeri letti dal sito."""
    citta = ["perugia", "terni"][turno(stato, "mercato", 2)]
    for _ in range(2):
        vendita, affitto = case(elenco("vendita", citta)), case(elenco("affitto", citta))
        if len(vendita) >= 5:
            break
        cs.log(f"  mercato: pochi annunci a {citta}, provo l'altra città")
        citta = "terni" if citta == "perugia" else "perugia"
    if len(vendita) < 5:
        raise RuntimeError("mercato: non ci sono abbastanza annunci per fare i conti")
    C = citta.title()
    prezzi = sorted(x["prezzo"] for x in vendita)
    mediana = tondo(statistics.median(prezzi))
    economico = min(vendita, key=lambda x: x["prezzo"])
    foto_prima = scarica_foto(vendita[0]["foto"], cartella, "m0")
    foto_eco = scarica_foto(economico["foto"], cartella, "m1")
    oggi = date.today().strftime("%d/%m/%Y")
    fonte = f"Dati: gli ultimi {len(vendita)} annunci in vendita su cercocasaumbria.it, {oggi}"
    scene = [{"kind": "gancio", "photo": u(foto_prima), "eye": "Il mercato della settimana",
              "title": f"Quanto costa casa a {C} oggi?",
              "voce": f"Quanto costa comprare casa a {C} oggi? Guardiamo gli annunci di questa settimana."},
             {"kind": "scheda", "eye": "Prezzo tipico", "title": euro(mediana),
              "sub": "Metà delle case in vendita costa meno", "source": fonte,
              "voce": f"La metà delle case in vendita costa meno di {euro_voce(mediana)}."}]
    al_mq = [x["prezzo"] / mq_di(x) for x in vendita if mq_di(x) >= 25]
    if len(al_mq) >= 5:
        v = tondo(statistics.median(al_mq), 50)
        scene.append({"kind": "scheda", "eye": "Al metro quadro", "title": f"{euro(v)}/m²",
                      "sub": "Il prezzo tipico al metro quadro", "source": fonte,
                      "voce": f"Al metro quadro, il prezzo tipico è di {euro_voce(v)}."})
    scene.append({"kind": "foto", "photo": u(foto_eco), "eye": "Si parte da", "title": euro(economico["prezzo"]),
                  "sub": f"{sp.tipo_bello(economico['tipo_imm'])} · {luogo(economico)}",
                  "voce": f"Si parte da {euro_voce(economico['prezzo'])}."})
    if len(affitto) >= 4:
        a = tondo(statistics.median(x["prezzo"] for x in affitto), 10)
        scene.append({"kind": "scheda", "eye": "Affitto tipico", "title": f"{euro(a)} al mese",
                      "sub": f"Su {len(affitto)} annunci in affitto",
                      "source": f"Dati: annunci in affitto su cercocasaumbria.it, {oggi}",
                      "voce": f"In affitto, il canone tipico è di {euro_voce(a)} al mese."})
    scene.append({"kind": "fine", "voce": "Segui Cercocasa Umbria: ogni lunedì i prezzi delle case in Umbria."})
    testo = (f"Quanto costa casa a {C} oggi?\n\n"
             f"Prezzo tipico in vendita: {euro(mediana)} (metà degli annunci costa meno).\n"
             f"Si parte da {euro(economico['prezzo'])}.\n"
             f"Conti fatti sugli ultimi {len(vendita)} annunci pubblicati su Cercocasa Umbria, {oggi}: "
             "sono prezzi richiesti, non prezzi di vendita finali."
             f"{CODA}\n\n{TAG} #{citta} #mercatoimmobiliare #prezzicase")
    return dict(scene=scene, testo=testo, chiave=citta, ids=[economico["id"]])


def scena_annuncio(x, foto, numero=None, con_dettagli=True):
    tipo = sp.tipo_bello(x["tipo_imm"])
    pezzi = [tipo] + [v for v in (voce_di(x, "area"), voce_di(x, "bed"), voce_di(x, "bath")) if v]
    parlato = f"{tipo} a {x['citta'].title()}"
    if (x.get("zona") or "").strip() and x["zona"].lower() != x["citta"].lower():
        parlato += f", zona {x['zona'].title()}"
    parlato += f": {euro_voce(x['prezzo'])}."
    if con_dettagli and mq_di(x):
        parlato += f" {mq_di(x)} metri quadrati."
    if numero:
        parlato = f"Numero {numero}. " + parlato
    return {"kind": "foto", "photo": u(foto), "num": str(numero) if numero else "", "eye": luogo(x),
            "title": euro(x["prezzo"]), "sub": " · ".join(pezzi), "voce": parlato}


def scegli_lista(stato, tema, quanti, giorni, ordine=None):
    """annunci in vendita a Perugia e a Terni, alternati, mai gli stessi delle ultime settimane"""
    usati = ids_recenti(stato, tema, giorni)
    pg, tr = case(elenco("vendita", "perugia")), case(elenco("vendita", "terni"))
    if ordine:
        tutti = sorted(pg + tr, key=ordine)
    else:
        tutti = [x for coppia in zip(pg, tr) for x in coppia] + pg[len(tr):] + tr[len(pg):]
    nuovi = [x for x in tutti if x["id"] not in usati]
    return (nuovi + [x for x in tutti if x["id"] in usati])[:quanti * 2]


def tema_lista(stato, cartella, tema, quanti, giorni, gancio, occhio, voce_gancio, voce_fine, etichette, ordine=None):
    scelti = []
    for x in scegli_lista(stato, tema, quanti, giorni, ordine):
        f = scarica_foto(x["foto"], cartella, f"l{len(scelti)}")
        if f:
            scelti.append((x, f))
        if len(scelti) >= quanti:
            break
    if len(scelti) < min(3, quanti):
        raise RuntimeError(f"{tema}: trovati solo {len(scelti)} annunci con la foto")
    scene = [{"kind": "gancio", "photo": u(scelti[0][1]), "eye": occhio, "title": gancio.format(n=len(scelti)),
              "voce": voce_gancio.format(n=len(scelti))}]
    for k, (x, f) in enumerate(scelti, 1):
        scene.append(scena_annuncio(x, f, numero=k, con_dettagli=len(scelti) <= 3))
    scene.append({"kind": "fine", "voce": voce_fine})
    righe = [f"{k}. {sp.tipo_bello(x['tipo_imm'])} a {luogo(x).replace(' · ', ', ')}: {euro(x['prezzo'])}"
             for k, (x, _f) in enumerate(scelti, 1)]
    testo = (gancio.format(n=len(scelti)) + "\n\n" + "\n".join(righe) +
             "\n\nQuale sceglieresti? Scrivilo nei commenti." + f"{CODA}\n\n{TAG} {etichette}")
    return dict(scene=scene, testo=testo, chiave=tema, ids=[x["id"] for x, _f in scelti])


def tema_top5(stato, cartella):
    """Venerdì: cinque proposte della settimana, le più recenti in vendita a Perugia e a Terni"""
    return tema_lista(stato, cartella, "top5", 5, 28,
                      gancio="{n} case che non puoi perderti in Umbria", occhio="Le proposte della settimana",
                      voce_gancio="{n} case in vendita che non puoi perderti questa settimana in Umbria.",
                      voce_fine="Quale sceglieresti? Segui Cercocasa Umbria per le prossime.",
                      etichette="#perugia #terni #casedasogno")


def tema_prestigio(stato, cartella):
    """Sabato: i tre immobili con il prezzo più alto tra gli annunci recenti"""
    return tema_lista(stato, cartella, "prestigio", 3, 28,
                      gancio="Le case di prestigio della settimana in Umbria", occhio="Immobili di prestigio",
                      voce_gancio="Le case di prestigio di questa settimana in Umbria.",
                      voce_fine="Segui Cercocasa Umbria: ogni sabato gli immobili di prestigio.",
                      etichette="#perugia #terni #immobilidiprestigio #luxuryhomes",
                      ordine=lambda x: -x["prezzo"])


def tema_immobile(stato, cartella):
    """Martedì: un Reel tutto per un immobile, con le sue foto e i suoi dati"""
    citta = ["perugia", "terni"][turno(stato, "immobile", 2)]
    usati = ids_recenti(stato, "immobile", 120)
    candidati = [x for x in case(elenco("vendita", citta)) + case(elenco("vendita", "terni" if citta == "perugia" else "perugia"))
                 if x["id"] not in usati]
    for x in candidati[:8]:
        try:
            a = cs.leggi_annuncio(x["id"])
        except Exception as e:
            cs.log("  annuncio saltato", x["id"], e)
            continue
        if len(a.get("foto", [])) < 5:
            continue
        x["dettaglio"], x["slot"] = a, "strategia"
        foto = sp.foto_annuncio(x, cartella, massimo=7)
        if len(foto) < 4:
            continue
        break
    else:
        raise RuntimeError("immobile: nessun annuncio con abbastanza foto")
    comune = (a.get("comune") or "").split("·")[0].strip() or x["citta"].title()
    frasi = [f for f in cs.frasi_video(a) if not f.lower().startswith("asta")][:4]
    try:
        import foto_stanze
        abbinate = foto_stanze.abbina(frasi, foto, cartella, "#DB9C12", log=cs.log)
    except Exception as e:
        cs.log("  foto non abbinate alle frasi, uso l'ordine dell'annuncio:", e)
        abbinate = (foto[1:] * 2)[:len(frasi)]
    cifra = tondo(x["prezzo"])
    tipo = sp.tipo_bello(x["tipo_imm"])
    scene = [{"kind": "gancio", "photo": u(foto[0]), "eye": f"In vendita · {comune}",
              "title": f"Cosa compri con {f'{cifra:,}'.replace(',', '.')} euro a {comune}?",
              "voce": f"Cosa compri con {euro_voce(cifra)} a {comune}? Guarda questa casa."}]
    for f, fp in zip(frasi, abbinate):
        scene.append({"kind": "foto", "photo": u(fp), "title": f.rstrip("."), "voce": sp.parlato(f)})
    agenzia = sp.nome_agenzia(a.get("agenzia"))
    scene.append({"kind": "foto", "photo": u(foto[0]), "eye": "Prezzo", "title": euro(x["prezzo"]),
                  "sub": f"{tipo} · {luogo(x)}" + (f" · {agenzia}" if agenzia else ""),
                  "voce": f"Il prezzo: {euro_voce(x['prezzo'])}." + (f" La propone {agenzia}." if agenzia else "")})
    scene.append({"kind": "fine", "sub": f"Codice annuncio {x['id']} · tutte le foto dal link in bio",
                  "voce": "Tutte le foto dal link in bio. Segui Cercocasa Umbria."})
    testo = (f"Cosa compri con {euro(cifra)} a {comune}?\n\n"
             f"{maiuscola(a.get('titolo') or tipo)}\n"
             f"Prezzo: {euro(x['prezzo'])}" + (f"\nAnnuncio di {agenzia}" if agenzia else "") +
             f"\nCodice {x['id']}: {x['url']}"
             f"{CODA}\n\n{TAG} #{x['citta']} #{re.sub(r'[^a-z]', '', comune.lower())}")
    return dict(scene=scene, testo=testo, chiave=str(x["id"]), ids=[x["id"]])


def logo_agenzia(pagina, nome, cartella):
    """il logo dell'agenzia dalla sua pagina sul portale (non il logo di Cercocasa, non le foto degli annunci)"""
    from bs4 import BeautifulSoup
    from urllib.parse import urljoin
    zuppa = BeautifulSoup(pagina, "html.parser")
    parole = [w for w in re.findall(r"[a-zà-ù]{4,}", nome.lower()) if w not in ("immobiliare", "agenzia", "affiliato", "studio")]
    scelti = []
    for k, img in enumerate(zuppa.find_all("img")):
        src = img.get("src") or img.get("data-src") or ""
        attorno = " ".join([src, img.get("alt", ""), " ".join(img.get("class", []))] +
                           [" ".join(g.get("class", [])) for g in list(img.parents)[:3]]).lower()
        if not src or src.startswith("data:") or re.search(r"uploads/properties|/assets/|logo-v\d|cercocasa|mappa|placeholder", src, re.I):
            continue
        punti = (3 if re.search(r"agenc|agenz|agency", attorno) else 0) + (2 if "logo" in attorno else 0) + \
                (2 if any(w in attorno for w in parole) else 0)
        if punti:
            scelti.append((-punti, k, urljoin(cs.SITO + "/", src)))
    cs.log("  logo agenzia, candidati: " + (", ".join(f"{u_} ({-p_})" for p_, _k, u_ in sorted(scelti)[:4]) or "nessuno"))
    for _p, _k, url in sorted(scelti)[:3]:
        try:
            r = cs.HTTP.get(url, timeout=60)
            r.raise_for_status()
            est = Path(url.split("?")[0]).suffix.lower() or ".png"
            grezzo = cartella / f"logo-agenzia-orig{est}"
            grezzo.write_bytes(r.content)
            if est == ".svg":
                return grezzo
            png = cartella / "logo-agenzia.png"
            cs.ff("-i", grezzo, "-vf", "scale='min(700,iw)':-2", png)
            return png
        except Exception as e:
            cs.log("  logo agenzia non scaricato", url, e)
    return None


def tema_agenzia(stato, cartella):
    """Giovedì: un'agenzia della rivista con tre dei suoi annunci. Se nel file agenzie_rivista.json l'agenzia ha
    il campo "instagram" (es. "nomeprofilo"), il Reel viene proposto in collaborazione con il suo profilo."""
    agenzie = [a for a in json.loads(cs.AGENZIE.read_text(encoding="utf-8"))["agenzie"] if a.get("attiva", True)]
    ultima = {p.get("chiave"): i for i, p in enumerate(stato["pubblicati"]) if p.get("tema") == "agenzia"}
    agenzie.sort(key=lambda a: ultima.get(str(a["id"]), -1))       # prima chi non è mai stata presentata
    for ag in agenzie:
        try:
            pagina = cs.scarica_testo(f"{cs.SITO}/agenzia.php?id={ag['id']}")
        except Exception as e:
            cs.log("  agenzia saltata", ag["nome"], e)
            continue
        ids = sorted(dict.fromkeys(int(i) for i in re.findall(r"immobile\.php\?id=(\d+)", pagina)), reverse=True)
        scelti = []
        for id_ in ids[:8]:
            try:
                a = cs.leggi_annuncio(id_)
            except Exception as e:
                cs.log("  annuncio saltato", id_, e)
                continue
            if not a.get("foto") or not cs.prezzo_numero(a) or a.get("operazione") == "ALL'ASTA":
                continue
            f = scarica_foto(a["foto"][0], cartella, f"a{len(scelti)}")
            if f:
                scelti.append((a, f))
            if len(scelti) >= 3:
                break
        if len(scelti) >= 2:
            break
        cs.log(f"  {ag['nome']}: pochi annunci adatti, passo alla prossima agenzia")
    else:
        raise RuntimeError("agenzia: nessuna agenzia con almeno due annunci adatti")
    nome = sp.nome_agenzia(ag["nome"])
    zona = ag.get("rivista", "Umbria")
    logo = logo_agenzia(pagina, ag["nome"], cartella)
    scene = [{"kind": "gancio", "photo": u(scelti[0][1]), "eye": "L'agenzia della settimana", "title": nome, "logo": u(logo),
              "sub": f"{zona} · i suoi annunci su Cercocasa Umbria",
              "voce": f"L'agenzia della settimana: {nome}, a {zona}. Ecco alcune delle sue proposte."}]
    for a, f in scelti:
        comune = (a.get("comune") or "").split("·")[0].strip() or zona
        tipo = maiuscola(cs.tipo_parola(a))
        operazione = "in affitto" if "AFFIT" in (a.get("operazione") or "").upper() else "in vendita"
        prezzo = cs.prezzo_numero(a)
        scene.append({"kind": "foto", "photo": u(f), "eye": f"{tipo} {operazione} · {comune}",
                      "title": euro(prezzo) + (" al mese" if operazione == "in affitto" else ""),
                      "sub": " · ".join(v for v in (f"{a['mq']} m²" if a.get("mq") else "",
                                                     f"{a['camere']} camere" if a.get("camere") else "") if v),
                      "voce": f"{tipo} {operazione} a {comune}: {euro_voce(prezzo)}" +
                              (" al mese." if operazione == "in affitto" else ".")})
    scene.append({"kind": "fine", "logo": u(logo), "sub": f"Tutti gli annunci di {nome} dal link in bio",
                  "voce": f"Trovi tutti gli annunci di {nome} su Cercocasa Umbria. Seguici."})
    profilo = (ag.get("instagram") or "").strip().lstrip("@")
    testo = (f"L'agenzia della settimana: {nome}" + (f" (@{profilo})" if profilo else "") + f", {zona}.\n\n" +
             "\n".join(f"• {maiuscola(a.get('titolo') or '')}: {euro(cs.prezzo_numero(a))}" for a, _f in scelti) +
             f"\n\nTutti i suoi annunci: {cs.SITO}/agenzia.php?id={ag['id']}"
             f"{CODA}\n\n{TAG} #{zona.lower()} #agenziaimmobiliare")
    return dict(scene=scene, testo=testo, chiave=str(ag["id"]), ids=[a["id"] for a, _f in scelti],
                collab=[profilo] if profilo else [])


def tema_schede(stato, cartella, tema, voce, occhio, gancio, voce_gancio, punti, voce_fine, testo, foto=()):
    """consigli e borghi: schede grafiche (o le foto indicate nel file), una per punto"""
    locali = [DATI / "foto" / f for f in foto if (DATI / "foto" / f).exists()]
    scene = [{"kind": "gancio", "photo": u(locali[0]) if locali else "", "eye": occhio, "title": gancio, "voce": voce_gancio}]
    for k, p in enumerate(punti, 1):
        f = locali[k % len(locali)] if locali else None
        scene.append({"kind": "foto" if f else "scheda", "photo": u(f), "num": str(k), "title": p["titolo"],
                      "sub": p["testo"], "voce": p["testo"]})
    scene.append({"kind": "fine", "voce": voce_fine})
    return dict(scene=scene, testo=testo, chiave=voce, ids=[])


def tema_consigli(stato, cartella):
    """Mercoledì: un consiglio a settimana dal file strategia/consigli.json"""
    tutti = json.loads((DATI / "consigli.json").read_text(encoding="utf-8"))["consigli"]
    c = tutti[turno(stato, "consigli", len(tutti))]
    testo = (c["titolo"] + "\n\n" + "\n".join(f"{k}. {p['titolo']}: {p['testo']}" for k, p in enumerate(c["punti"], 1)) +
             "\n\nSalva il post: ti servirà quando sarà il momento." + f"{CODA}\n\n{TAG} #consiglicasa #venderecasa #comprarecasa")
    return tema_schede(stato, cartella, "consigli", c["titolo"], "Il consiglio della settimana", c["titolo"], c["gancio"],
                       c["punti"], "Salva il video e segui Cercocasa Umbria per altri consigli.", testo, c.get("foto", ()))


def tema_borghi(stato, cartella):
    """Domenica: tre curiosità su un borgo umbro dal file strategia/borghi.json"""
    tutti = json.loads((DATI / "borghi.json").read_text(encoding="utf-8"))["borghi"]
    b = tutti[turno(stato, "borghi", len(tutti))]
    n = len(b["punti"])
    parola = {2: "Due", 3: "Tre", 4: "Quattro"}.get(n, str(n))
    testo = (f"{n} curiosità su {b['nome']} ({b['provincia']})\n\n" + "\n".join(f"{k}. {p['testo']}" for k, p in enumerate(b["punti"], 1)) +
             f"\n\nCi sei mai stato? Scrivilo nei commenti." +
             f"{CODA}\n\n{TAG} #{re.sub(r'[^a-zà-ù]', '', b['nome'].lower())} #borghiumbri #borghipiubelliditalia")
    return tema_schede(stato, cartella, "borghi", b["nome"], "Borghi dell'Umbria", f"{n} curiosità su {b['nome']}",
                       f"{parola} curiosità su {b['nome']}, in provincia di {b['provincia']}.", b["punti"],
                       "Cerchi casa in Umbria? Segui Cercocasa Umbria.", testo, b.get("foto", ()))


FUNZIONI = {"mercato": tema_mercato, "immobile": tema_immobile, "consigli": tema_consigli, "agenzia": tema_agenzia,
            "top5": tema_top5, "prestigio": tema_prestigio, "borghi": tema_borghi}


# ---------------------------------------------------------------- voce, sottotitoli, video
def tempi(scene, cartella):
    """una voce per scena; i sottotitoli sono le parole dette in quel momento. Restituisce (sottotitoli, voci, durata)"""
    t, voci, didascalie = 0, [], []
    for k, sc in enumerate(scene):
        detto = sc.pop("voce", "")
        d = None
        if detto:
            mp3 = cartella / f"voce{k}.mp3"
            d = cs.crea_voce(detto, mp3, velocita=VELOCITA)
        parlato_ms = int(d * 1000) if d else int(len(detto) * 62)
        attacco = 150 if k == 0 else 380
        dur = max(3400 if sc["kind"] == "fine" else 2600, attacco + parlato_ms + 450)
        if d:
            voci.append((mp3, t + attacco))
        pezzi = [p for frase in re.split(r"(?<=[.?!:])\s+", detto) if frase
                 for p in sp.spezza(frase, max_car=24, max_parole=4)]
        lettere = sum(len(p) for p in pezzi) or 1
        quando = t + attacco
        for p in pezzi:
            lungo = parlato_ms * len(p) / lettere
            didascalie.append({"text": p, "start": int(quando), "end": int(quando + lungo)})
            quando += lungo
        if didascalie and pezzi:
            didascalie[-1]["end"] = t + dur - 120
        sc["start"], sc["end"] = t, t + dur
        t += dur
    return didascalie, voci, t


def crea_video(browser, post, cartella, nome):
    scene = post["scene"]
    didascalie, voci, totale = tempi(scene, cartella)
    if not DURATA_MIN <= totale <= DURATA_MAX:
        cs.log(f"  attenzione: il video dura {totale / 1000:.1f} s (obiettivo 20-35 s)")
    r, g, b = cs.COLORI_GIORNO[datetime.now().timetuple().tm_yday % len(cs.COLORI_GIORNO)]
    chiaro = (0.2126 * r + 0.7152 * g + 0.0722 * b) > 140
    dati = {"scenes": scene, "captions": didascalie, "total": totale, "handle": PROFILO,
            "accent": f"#{r:02X}{g:02X}{b:02X}", "onAccent": "#1F1F1F" if chiaro else "#FFFFFF"}
    fotogrammi = cartella / "fotogrammi"
    fotogrammi.mkdir()
    pagina = browser.new_page(viewport={"width": W, "height": H})
    pagina.add_init_script("window.POST = " + json.dumps(dati) + ";")
    pagina.goto("file://" + str(GRAFICA))
    pagina.evaluate("window.pronto")
    pagina.wait_for_function("[...document.images].every(i => i.complete)", timeout=30000)
    for i in range(totale * FPS // 1000):
        pagina.evaluate(f"window.seek({i * 1000 / FPS})")
        pagina.screenshot(path=str(fotogrammi / f"{i:04d}.jpg"), type="jpeg", quality=92)
    pagina.close()
    muto = cartella / "muto.mp4"
    cs.ff("-framerate", str(FPS), "-i", fotogrammi / "%04d.jpg", "-c:v", "libx264", "-preset", "veryfast",
          "-crf", "18", "-pix_fmt", "yuv420p", muto)
    shutil.rmtree(fotogrammi, ignore_errors=True)
    audio = sp.audio_post(voci, totale, cartella)
    cs.USCITA.mkdir(exist_ok=True)
    out = cs.USCITA / f"{nome}.mp4"
    cs.ff("-i", muto, "-i", audio, "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
          "-shortest", "-movflags", "+faststart", out)
    cs.log(f"  video: {totale / 1000:.1f} s, {len(scene)} scene, {len(voci)} voci, {len(didascalie)} sottotitoli")
    return out, totale


# ---------------------------------------------------------------- pubblicazione
def pubblica_instagram(video, testo, collab=()):
    """Reel con copertina sul titolo iniziale; con collab = profili invitati come collaboratori (devono accettare)"""
    originale = cs.HTTP.post

    def con_collaboratori(url, *a, **kw):
        dati = kw.get("data")
        if isinstance(dati, dict) and dati.get("media_type") == "REELS":
            dati["thumb_offset"] = "0"
            if collab:
                dati["collaborators"] = json.dumps(list(collab))
        return originale(url, *a, **kw)

    cs.HTTP.post = con_collaboratori
    try:
        return cs.pubblica_instagram(video, testo)
    finally:
        cs.HTTP.post = originale


def main():
    ap = argparse.ArgumentParser(description="Il post del pomeriggio per Instagram, un tema al giorno")
    ap.add_argument("--prova", action="store_true", help="crea video e testo, non pubblica")
    ap.add_argument("--tema", choices=TEMI, help="forza un tema (di norma lo decide il giorno della settimana)")
    args = ap.parse_args()
    oggi = date.today()
    tema = args.tema or TEMI[oggi.weekday()]
    stato = carica_stato()
    if not args.prova and any(str(p.get("data", "")).startswith(oggi.isoformat()) and p.get("instagram_id")
                              for p in stato["pubblicati"]):
        cs.log("Il post del pomeriggio di oggi è già stato pubblicato.")
        return
    cs.log(f"Post del pomeriggio: {NOMI_GIORNO[oggi.weekday()]}, tema '{tema}'" + (" (prova)" if args.prova else ""))
    from playwright.sync_api import sync_playwright
    cartella = Path(tempfile.mkdtemp(prefix="strategia-"))
    post = FUNZIONI[tema](stato, cartella)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            video, totale = crea_video(browser, post, cartella, f"strategia-{tema}")
        finally:
            browser.close()
    righe = post["testo"].split("\n")            # niente hashtag ripetuti (es. #perugia due volte)
    righe[-1] = " ".join(dict.fromkeys(righe[-1].split()))
    post["testo"] = "\n".join(righe)
    (cs.USCITA / f"strategia-{tema}.txt").write_text(post["testo"], encoding="utf-8")
    cs.log("  testo del post:\n" + post["testo"])
    if args.prova:
        cs.log(f"Prova: video creato ({video}), niente pubblicato.")
        return
    collab = post.get("collab") or []
    try:
        ig = pubblica_instagram(video, post["testo"], collab)
    except Exception as e:
        if not collab:
            raise
        cs.log("  con il collaboratore non è riuscito, riprovo senza:", e)
        ig = pubblica_instagram(video, post["testo"])
    if not ig:
        raise SystemExit("Instagram non ha pubblicato il post del pomeriggio")
    stato["pubblicati"].append({"data": datetime.now().strftime("%Y-%m-%dT%H:%M"), "tema": tema, "chiave": post["chiave"],
                                "ids": post["ids"], "instagram_id": str(ig), "durata_s": round(totale / 1000, 1)})
    STATO.write_text(json.dumps(stato, ensure_ascii=False, indent=1), encoding="utf-8")
    cs.log(f"Pubblicato su Instagram: {ig}")


if __name__ == "__main__":
    main()
