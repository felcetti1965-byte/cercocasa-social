"""Toglie la filigrana dell'agenzia (es. "TEMPOCASA" semitrasparente al centro) dalle foto di un annuncio.

Le agenzie stampano la filigrana nello stesso punto di tutte le foto. Confrontando le foto dello
stesso annuncio si trova ciò che è uguale in tutte (la filigrana) e diverso nel resto (la casa):
- maschera = punti che in quasi tutte le foto sono più chiari (o più scuri) dei dintorni;
- la filigrana semitrasparente si toglie "al contrario" (si stima quanto bianco è stato aggiunto);
- i bordi rimasti si ritoccano con l'inpainting di OpenCV.
Se le foto sono troppo poche o non c'è una filigrana chiara, le foto restano come sono."""
from pathlib import Path

import numpy as np

LATO = 960            # le foto si confrontano a questa larghezza
MIN_FOTO = 3


def _cv():
    import cv2
    return cv2


def _carica(f, cv2):
    im = cv2.imread(str(f), cv2.IMREAD_COLOR)
    if im is None:
        return None
    h, w = im.shape[:2]
    return cv2.resize(im, (LATO, int(round(LATO * h / w))), interpolation=cv2.INTER_AREA)


def _differenza(im, cv2):
    """quanto ogni punto è più chiaro / più scuro della zona intorno (scala di grigi)"""
    g = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY).astype(np.float32)
    fondo = cv2.medianBlur(g.astype(np.uint8), 31).astype(np.float32)
    return g - fondo, fondo


def trova_maschera(immagini, cv2):
    """maschera della filigrana comune a tutte le foto (stesse dimensioni); None se non c'è"""
    diff = np.stack([_differenza(im, cv2)[0] for im in immagini])
    chiaro = np.median(diff, axis=0)                      # positivo dove tutte le foto sono più chiare
    quota = (diff > 6).mean(axis=0)                       # in quante foto quel punto è "più chiaro"
    m = ((chiaro > 7) & (quota >= 0.75)).astype(np.uint8) * 255
    # niente puntini isolati: la filigrana è fatta di tratti
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    n, etichette, stat, _ = cv2.connectedComponentsWithStats(m)
    pulita = np.zeros_like(m)
    for i in range(1, n):
        if stat[i, cv2.CC_STAT_AREA] >= 25:
            pulita[etichette == i] = 255
    area = pulita.mean() / 255
    if area < 0.002 or area > 0.25:                      # niente filigrana, o è un'altra cosa
        return None, None
    return pulita, np.clip(chiaro, 0, None)


def stima_alfa(immagini, maschera, cv2):
    """quanta "bianco" aggiunge la filigrana in ogni punto: uguale in tutte le foto, quindi si usa la mediana.
    Il fondo sotto la filigrana si stima per ogni foto con l'inpainting su una zona un po' più larga."""
    larga = cv2.dilate(maschera, np.ones((9, 9), np.uint8))
    stime = []
    for im in immagini:
        fondo = cv2.inpaint(im, larga, 7, cv2.INPAINT_TELEA).astype(np.float32)
        stime.append(((im.astype(np.float32) - fondo) / np.maximum(255 - fondo, 15)).mean(axis=2))
    alfa = np.clip(np.median(np.stack(stime), axis=0), 0, 0.9)
    alfa[larga == 0] = 0
    alfa[alfa < 0.08] = 0
    return alfa


def togli(im, alfa, maschera, cv2):
    """toglie la filigrana bianca semitrasparente (I = (1-a)*fondo + a*255  ->  fondo)"""
    a = alfa[..., None]
    I = im.astype(np.float32)
    pulita = np.clip((I - 255 * a) / np.maximum(1 - a, 0.15), 0, 255).astype(np.uint8)
    # ritocco solo dove la filigrana era quasi opaca (lì la foto sotto non si recupera)
    opaca = ((alfa > 0.7) * 255).astype(np.uint8)
    if opaca.any():
        pulita = cv2.inpaint(pulita, cv2.dilate(opaca, np.ones((3, 3), np.uint8)), 3, cv2.INPAINT_TELEA)
    return pulita


_lama = None


def _ritocco_lama():
    """modello LaMa (aperto) per ricostruire la foto sotto la filigrana; None se non disponibile"""
    global _lama
    if _lama is None:
        try:
            from simple_lama_inpainting import SimpleLama
            _lama = SimpleLama()
        except Exception as e:
            print("  filigrana: LaMa non disponibile, uso il metodo semplice:", e, flush=True)
            _lama = False
    return _lama or None


def ritocca(orig, maschera, cv2):
    """ricostruisce la foto dove c'è la filigrana (maschera allargata un po')"""
    lama = _ritocco_lama()
    larga = cv2.dilate(maschera, np.ones((7, 7), np.uint8))
    if lama is None:
        return None
    from PIL import Image
    rgb = Image.fromarray(cv2.cvtColor(orig, cv2.COLOR_BGR2RGB))
    out = np.array(lama(rgb, Image.fromarray(larga).convert("L")))
    out = cv2.cvtColor(out, cv2.COLOR_RGB2BGR)
    if out.shape[:2] != orig.shape[:2]:
        out = cv2.resize(out, (orig.shape[1], orig.shape[0]))
    sfuma = cv2.GaussianBlur(larga, (9, 9), 0).astype(np.float32)[..., None] / 255
    return (out * sfuma + orig * (1 - sfuma)).astype(np.uint8)


def pulisci_foto(foto, log=print):
    """toglie la filigrana dalle foto (file jpg) dello stesso annuncio, sovrascrivendole.
    Lavora per gruppi di foto con le stesse proporzioni. Restituisce quante foto ha pulito."""
    try:
        cv2 = _cv()
    except Exception as e:
        log("  filigrana: OpenCV non disponibile:", e)
        return 0
    gruppi = {}
    for f in foto:
        im = _carica(f, cv2)
        if im is not None:
            gruppi.setdefault(im.shape[:2], []).append((f, im))
    pulite = 0
    for forma, elenco in gruppi.items():
        if len(elenco) < MIN_FOTO:
            continue
        maschera, forza = trova_maschera([im for _, im in elenco], cv2)
        if maschera is None:
            continue
        log(f"  filigrana trovata su {len(elenco)} foto ({maschera.mean() / 255:.1%} dell'immagine): la tolgo")
        alfa = stima_alfa([im for _, im in elenco], maschera, cv2)
        for f, _ in elenco:
            orig = cv2.imread(str(f), cv2.IMREAD_COLOR)
            H, W = orig.shape[:2]
            a = cv2.resize(alfa, (W, H), interpolation=cv2.INTER_LINEAR)
            m = cv2.resize(maschera, (W, H), interpolation=cv2.INTER_NEAREST)
            pulita = ritocca(orig, m, cv2)
            if pulita is None:
                pulita = togli(orig, a, m, cv2)
            cv2.imwrite(str(f), pulita, [cv2.IMWRITE_JPEG_QUALITY, 92])
            pulite += 1
    return pulite


if __name__ == "__main__":      # prova: python filigrana.py foto1.jpg foto2.jpg ...
    import sys
    print("pulite:", pulisci_foto([Path(x) for x in sys.argv[1:]]))
