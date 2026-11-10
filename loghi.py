"""Toglie i loghi stampati sopra le foto di un annuncio (filigrane delle agenzie).
Un logo sta nello stesso punto in tutte le foto: la mediana dei gradienti (con il segno)
cancella la stanza, che cambia da foto a foto, e lascia solo il logo. Poi la zona del logo
viene ricostruita con LaMa (modello che 'ridisegna' la parte mancante), o con OpenCV se LaMa manca."""
import cv2, numpy as np, sys
from pathlib import Path

MIN_FOTO = 5

def mappa(imgs, size):
    X, Y = [], []
    for im in imgs:
        g = cv2.cvtColor(cv2.resize(im, size, interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY).astype(np.float32)
        X.append(cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3)); Y.append(cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3))
    return np.hypot(np.median(np.stack(X), 0), np.median(np.stack(Y), 0))

def maschera(imgs, size):
    m = mappa(imgs, size)
    med = np.median(m); mad = np.median(np.abs(m - med)) + 1e-3
    b = (m > max(med + 8 * mad, 14)).astype(np.uint8) * 255
    b = cv2.morphologyEx(b, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    n, lab, st, _ = cv2.connectedComponentsWithStats(cv2.dilate(b, np.ones((9, 9), np.uint8)))
    out = np.zeros_like(b)
    W, H = size
    for k in range(1, n):
        x, y, w, h, area = st[k]
        if area < 250 or w > 0.75 * W or h > 0.6 * H:
            continue
        out[lab == k] = 255
    # i loghi spesso hanno un fondo semitrasparente: si copre tutta la loro forma (involucro), non solo i bordi
    out = cv2.morphologyEx(out, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (25, 25)))
    piena = np.zeros_like(out)
    for c in cv2.findContours(out, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]:
        cv2.drawContours(piena, [cv2.convexHull(c)], -1, 255, -1)
    return cv2.dilate(piena, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15)))

_lama = None
def _carica_lama():
    import torch
    from simple_lama_inpainting.models.model import LAMA_MODEL_URL
    from simple_lama_inpainting.utils import download_model
    m = torch.jit.load(download_model(LAMA_MODEL_URL), map_location="cpu")
    m.eval()
    return m

def ricostruisci(img, m):
    global _lama
    try:
        import torch
        from PIL import Image
        from simple_lama_inpainting.utils import prepare_img_and_mask
        if _lama is None:
            _lama = _carica_lama()
        x, k = prepare_img_and_mask(Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)), Image.fromarray(m), torch.device("cpu"))
        with torch.inference_mode():
            r = _lama(x, k)[0].permute(1, 2, 0).numpy()
        r = cv2.cvtColor(np.clip(r * 255, 0, 255).astype(np.uint8), cv2.COLOR_RGB2BGR)[:img.shape[0], :img.shape[1]]
        # fuori dalla maschera resta la foto originale, identica
        mm = (cv2.GaussianBlur(m, (0, 0), 2) / 255.0)[..., None]
        return (r * mm + img * (1 - mm)).astype(np.uint8)
    except Exception as e:
        print("  LaMa non disponibile, uso OpenCV:", str(e)[:120])
        return cv2.inpaint(img, m, 9, cv2.INPAINT_TELEA)


def pulisci(files, extra=(), log=print):
    """files: foto dell'annuncio (vengono sovrascritte pulite); extra: altre foto della stessa agenzia,
    usate solo per riconoscere meglio il logo. Ritorna quante foto sono state pulite."""
    leggi = lambda fs: {f: i for f in fs if (i := cv2.imread(str(f))) is not None}
    imgs, altre = leggi(files), leggi(extra)
    pulite = 0
    for land in (True, False):
        gruppo = [f for f, i in imgs.items() if (i.shape[1] >= i.shape[0]) == land]
        if not gruppo:
            continue
        campione = [imgs[f] for f in gruppo] + [i for i in altre.values() if (i.shape[1] >= i.shape[0]) == land]
        if len(campione) < MIN_FOTO:
            log(f"  loghi: troppe poche foto {'orizzontali' if land else 'verticali'} per riconoscerli ({len(campione)})")
            continue
        size = (1024, 768) if land else (768, 1024)
        m = maschera(campione, size)
        quota = m.mean() / 255
        if quota < 0.001 or quota > 0.14:
            log(f"  loghi: niente di sicuro da togliere ({quota:.1%})")
            continue
        for f in gruppo:
            im = imgs[f]
            mm = cv2.resize(m, (im.shape[1], im.shape[0]), interpolation=cv2.INTER_NEAREST)
            cv2.imwrite(str(f), ricostruisci(im, mm), [cv2.IMWRITE_JPEG_QUALITY, 93])
            pulite += 1
        log(f"  loghi tolti da {len(gruppo)} foto ({quota:.1%} della foto ricostruita)")
    return pulite

if __name__ == "__main__":
    pulisci([Path(p) for p in sys.argv[1:]])
