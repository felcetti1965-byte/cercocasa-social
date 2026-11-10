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

def maschera(imgs, size, severita=8):
    m = mappa(imgs, size)
    med = np.median(m); mad = np.median(np.abs(m - med)) + 1e-3
    b = (m > max(med + severita * mad, 14 + severita - 8)).astype(np.uint8) * 255
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

LAMA_URL = "https://github.com/enesmsahin/simple-lama-inpainting/releases/download/v0.1.0/big-lama.pt"
_lama = None


def _carica_lama():
    """modello LaMa (circa 200 MB), scaricato una volta e tenuto nella cache di torch"""
    import torch
    from torch.hub import download_url_to_file, get_dir
    cartella = Path(get_dir()) / "checkpoints"
    cartella.mkdir(parents=True, exist_ok=True)
    f = cartella / "big-lama.pt"
    if not f.exists():
        download_url_to_file(LAMA_URL, str(f), progress=False)
    m = torch.jit.load(str(f), map_location="cpu")
    m.eval()
    return m


def _tensore(a, mod=8):
    """immagine (h,w,c) o maschera (h,w) -> tensore 1,c,H,W con lati multipli di 8"""
    import torch
    a = a.astype(np.float32) / 255
    a = a[None] if a.ndim == 2 else np.transpose(a, (2, 0, 1))
    h, w = a.shape[1:]
    a = np.pad(a, ((0, 0), (0, (-h) % mod), (0, (-w) % mod)), mode="symmetric")
    return torch.from_numpy(a).unsqueeze(0)


def ricostruisci(img, m):
    global _lama
    try:
        import torch
        if _lama is None:
            _lama = _carica_lama()
        x = _tensore(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        k = (_tensore(m) > 0).float()
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
        size = (1024, 768) if land else (768, 1024)
        # due prove: solo le foto dell'annuncio (logo messo su quell'annuncio) e insieme alle altre
        # dell'agenzia (logo fisso dell'agenzia, riconosciuto meglio). Si toglie quello che trovano.
        prove = [[imgs[f] for f in gruppo]]
        altre_g = [i for i in altre.values() if (i.shape[1] >= i.shape[0]) == land]
        if altre_g:
            prove.append(prove[0] + altre_g)
        m = None
        for campione in prove:
            if len(campione) < (3 if campione is prove[0] else MIN_FOTO):
                continue
            for severita in (8, 11, 15, 20):          # se la zona trovata è troppo grande, si è più severi
                mm = maschera(campione, size, severita)
                if mm.mean() / 255 <= 0.12:
                    break
            if 0.001 <= mm.mean() / 255 <= 0.12:
                m = mm if m is None else cv2.bitwise_or(m, mm)
        if m is None:
            log(f"  loghi: niente di sicuro da togliere ({'orizzontali' if land else 'verticali'})")
            continue
        quota = m.mean() / 255
        for f in gruppo:
            im = imgs[f]
            mm = cv2.resize(m, (im.shape[1], im.shape[0]), interpolation=cv2.INTER_NEAREST)
            cv2.imwrite(str(f), ricostruisci(im, mm), [cv2.IMWRITE_JPEG_QUALITY, 93])
            pulite += 1
        log(f"  loghi tolti da {len(gruppo)} foto ({quota:.1%} della foto ricostruita)")
    return pulite

if __name__ == "__main__":
    pulisci([Path(p) for p in sys.argv[1:]])
