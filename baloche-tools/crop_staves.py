"""
crop_staves.py -- ne garde que les portees melodiques (5 lignes) d'une page de
partition et supprime le reste (tablatures d'accordeon : doigtes, rangees C/G,
basses, titres, textes), pour qu'Audiveris ne voie que la melodie.

Usages :
    python crop_staves.py page.png sortie.png            # une image
    python crop_staves.py partition.pdf sortie.pdf       # un PDF (toutes les pages)
    python crop_staves.py --dir raw\\pdf --out raw\\pdf_melodie   # tout un dossier
Options : --melody (premiere portee de chaque systeme si le document en a plusieurs),
--changed-only (avec --dir : n'ecrit que les PDF concernes), --debug (page annotee), --voltas (garde les crochets de reprise 1./2.), --binarize ou --binarize=170 (noir et blanc
propre : fond de papier efface), --min-interline=N (agrandit par un facteur
entier si l'interligne est inferieur a N pixels ; 0 = jamais ; defaut 14).

Les PDF sont rendus a 300 dpi : il faut PyMuPDF (pip install pymupdf) ou, a
defaut, l'outil pdftoppm (poppler). Une page ou aucune portee n'est detectee
(scan de travers, portees trop petites...) est conservee telle quelle, sans
risque de perdre de la musique.
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

DPI = 300
MIN_INTERLINE = 14.0   # --min-interline=N (0 = jamais d'agrandissement)
MELODY = False   # --melody : une seule portee (la premiere) par systeme
CHANGED_ONLY = False   # --changed-only : en mode --dir, n'ecrit que les PDF reduits
VOLTAS = False   # --voltas : garde les crochets de reprise (1. 2.) au-dessus des portees
BINARIZE = None   # --binarize [seuil] : sortie noir et blanc propre (fond de papier efface)


# ----------------------------------------------------------------------
# Detection des portees
# ----------------------------------------------------------------------
def to_rgb_on_white(img):
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, "white")
        bg.paste(img, mask=img.split()[3])
        return bg
    return img.convert("RGB")


def line_centers(ink, min_frac=0.9, smooth=True):
    """Centres des lignes horizontales longues (portees, filets de tablature).

    Le profil des rangees est lisse sur quelques pixels : sur un scan de
    magazine, les lignes de portee sont souvent legerement inclinees ou
    ondulees et s'etalent sur 5 a 7 rangees, chacune ne contenant alors que
    30 a 60 % de la largeur. Compter rangee par rangee les ratait ; on somme
    donc la fraction d'encre sur une petite fenetre (min_frac ~ 0,9 = environ
    une ligne complete)."""
    h, w = ink.shape
    frac = ink.sum(axis=1) / float(w)
    if smooth:
        r = max(1, h // 900)
        prof = np.convolve(frac, np.ones(2 * r + 1), mode="same")
    else:
        prof = frac          # rangee par rangee : mieux sur un rendu flou ou agrandi
    on = prof >= min_frac
    centers, i = [], 0
    while i < h:
        if on[i]:
            j = i
            while j + 1 < h and on[j + 1]:
                j += 1
            ys = np.arange(i, j + 1)
            wts = frac[i:j + 1]
            centers.append(float((ys * wts).sum() / wts.sum()) if wts.sum() > 0 else (i + j) / 2.0)
            i = j + 1
        else:
            i += 1
    return centers


def find_staves(centers, ratio=1.30, max_gap=None):
    """Series de lignes a espacement regulier ; seules celles qui comptent
    exactement 5 lignes sont des portees (une tablature de guitare a 6 lignes,
    ou une grille a 2-3 lignes, est ecartee). max_gap : ecart maximal plausible
    entre deux lignes d'une portee (evite de prendre pour une portee trois
    filets distants qui sont espaces regulierement par hasard)."""
    staves, i, n = [], 0, len(centers)
    while i < n - 1:
        gap0 = centers[i + 1] - centers[i]
        if gap0 <= 1 or (max_gap is not None and gap0 > max_gap):
            i += 1
            continue
        j = i + 1
        while j + 1 < n:
            g = centers[j + 1] - centers[j]
            if gap0 / ratio <= g <= gap0 * ratio:
                j += 1
            else:
                break
        run = j - i + 1
        if run == 5:
            staves.append((centers[i], centers[j], (centers[j] - centers[i]) / 4.0))
            i = j + 1
        elif run >= 6:
            i = j + 1      # serie reguliere trop longue (ex. tablature a 6 lignes)
        else:
            i += 1         # on ne saute rien : la portee peut commencer a la ligne suivante
    return staves


def estimate_skew(gray, ink=235, max_deg=2.0):
    """Angle (en degres) a appliquer pour redresser une page scannee de
    travers : celui qui rend les lignes de portee le plus nettement
    horizontales (variance maximale du profil des lignes). Un scan penche de
    0,3 degre etale deja une ligne de portee sur plusieurs rangees de pixels
    et la fait disparaitre de la detection."""
    h, w = gray.shape
    k = max(1, w // 1000)
    small = Image.fromarray(((gray < ink) * 255).astype(np.uint8)).resize(
        (w // k, h // k), Image.BILINEAR)

    def score(angle):
        r = np.array(small.rotate(angle, resample=Image.BILINEAR, fillcolor=0), dtype=float)
        p = r.sum(axis=1)
        return float((p * p).sum())

    best = max(np.arange(-max_deg, max_deg + 1e-9, 0.1), key=score)
    best = max(np.arange(best - 0.1, best + 0.101, 0.02), key=score)
    return float(best)


def longest_run(row, max_hole):
    xs = np.where(row)[0]
    if len(xs) == 0:
        return None
    best = cur = (xs[0], xs[0])
    for x in xs[1:]:
        cur = (cur[0], x) if x - cur[1] <= max_hole else (x, x)
        if cur[1] - cur[0] > best[1] - best[0]:
            best = cur
    return best


def find_volta_bracket(ink_mask, top, sp, w):
    """Ordonnee du trait horizontal d'un crochet de reprise (1., 2.) situe
    au-dessus de la portee, ou None. Le crochet est un long trait horizontal
    (une mesure de large) entre 3 et 8,5 interlignes au-dessus de la ligne du
    haut ; les noms d'accords et les lettres de repere n'en forment pas."""
    h = ink_mask.shape[0]
    ya = max(0, int(top - 8.5 * sp))
    yb = max(0, int(top - 3.0 * sp))
    found = []
    for y in range(ya, yb):
        r = longest_run(ink_mask[y], 3)
        if r and (r[1] - r[0]) >= 0.06 * w:
            found.append(y)
    return min(found) if found else None


def trim_barline_overshoot(img, ink_mask, staves, pad_above, pad_below, keep_above=False):
    """Raccourcit les barres de mesure a la hauteur exacte de la portee.

    Dans la partition d'origine, les barres de mesure traversent toute la
    tablature ; une fois la tablature coupee, elles depassent de la portee
    d'un cote ou de l'autre (ou pendent vers le haut jusqu'aux crochets de
    reprise). Audiveris ne reconnait alors plus ces traits comme des barres :
    il ne voit qu'une seule mesure par systeme et jette les notes qui ne
    tiennent pas dedans (journal : "4 raw measures", "no correct rhythm").

    Une colonne est une barre si de l'encre la remplit sur toute la hauteur de
    la portee ET la prolonge d'au moins une demi-interligne au-dessus ou
    au-dessous (une hampe de note ne couvre jamais ca : elle est limitee a
    3,5 interlignes et attachee a une tete de note)."""
    arr = np.array(img)
    h, w = ink_mask.shape
    n_cols = 0
    for top, bottom, sp in staves:
        y0, y1 = int(round(top)), int(round(bottom))
        k = max(2, int(0.5 * sp))
        full = ink_mask[y0:y1 + 1].mean(axis=0) >= 0.92
        below = ink_mask[y1 + 1:min(h, y1 + 1 + k)].mean(axis=0) >= 0.85 if y1 + 1 < h else np.zeros(w, bool)
        above = ink_mask[max(0, y0 - k):y0].mean(axis=0) >= 0.85 if y0 > 0 else np.zeros(w, bool)
        cols = np.where(full & (below | above))[0]
        if len(cols) == 0:
            continue
        # groupes de colonnes contigues (traits epais, doubles barres)
        groups, a, b = [], cols[0], cols[0]
        for x in cols[1:]:
            if x - b <= 2:
                b = x
            else:
                groups.append((a, b)); a, b = x, x
        groups.append((a, b))
        ytop = max(0, int(top - pad_above * sp) - 2)
        ybot = min(h, int(bottom + pad_below * sp) + 3)
        m = int(round(0.15 * sp))
        for xa, xb in groups:
            xa0, xb1 = max(0, xa - 3), min(w, xb + 4)
            if not keep_above:
                arr[ytop:max(ytop, y0 - m), xa0:xb1] = 255
            arr[min(ybot, y1 + 1 + m):ybot, xa0:xb1] = 255
            n_cols += 1
    return Image.fromarray(arr), n_cols


def clean_levels(img, thr=190):
    """Noir et blanc propre : le papier devient blanc uni (grain, bruit JPEG et
    taches de scan disparaissent), l'encre noire. Les niveaux sont etires
    d'abord pour que les lignes grises de portee et les barres fines
    survivent au seuil."""
    g = np.array(img.convert("L")).astype(float)
    bg = np.percentile(g, 90)
    lo = np.percentile(g, 0.5)
    n = np.clip((g - lo) / max(1.0, bg - lo), 0, 1) * 255
    return Image.fromarray(np.where(n < thr, 0, 255).astype(np.uint8)).convert("RGB")


def detect_staves(img, ink=235, deskew=True):
    """Redresse la page puis detecte les portees. Renvoie
    (image redressee, niveaux de gris, masque d'encre, portees)."""
    img = to_rgb_on_white(img)
    gray = np.array(img.convert("L"))
    if deskew:
        angle = estimate_skew(gray, ink)
        if abs(angle) >= 0.05:
            img = img.rotate(angle, resample=Image.BICUBIC, fillcolor=(255, 255, 255))
            gray = np.array(img.convert("L"))
    # "non blanc" : robuste aux traits fins et gris d'un rendu basse resolution
    #  ou d'un scan (un seuil classique de 140 manque ces lignes).
    # Plusieurs reglages (seuil d'encre, seuil de ligne) : un scan pale ou un
    #  scan bruite ne reagissent pas au meme ; on garde celui qui trouve le
    #  plus de portees.
    best_staves, ink_mask = [], gray < ink
    reglages = ((ink, 0.9, True), (ink, 0.6, True), (ink + 10, 0.9, True),
                (ink + 10, 0.6, True), (ink - 10, 0.9, True),
                (ink, 0.40, False), (ink + 10, 0.40, False), (ink + 10, 0.30, False))
    for thr_ink, thr_line, smooth in reglages:
        mask = gray < thr_ink
        st = find_staves(line_centers(mask, min_frac=thr_line, smooth=smooth),
                         max_gap=0.015 * mask.shape[0])
        if len(st) > len(best_staves):
            best_staves, ink_mask = st, mask
    staves = best_staves
    return img, gray, ink_mask, staves


def crop_page(img, pad_above=3.3, pad_below=2.6, ink=235, min_interline=None,
              deskew=True, debug=None, detected=None):
    """Renvoie (image ne contenant que les portees, liste des portees) ou
    (None, []) si aucune portee n'est detectee. Si debug est un chemin, ecrit
    la page annotee (portees detectees en rouge, zone gardee en vert)."""
    if detected is None:
        detected = detect_staves(img, ink, deskew)
    img, gray, ink_mask, staves = detected
    if not staves:
        return None, []

    h, w = gray.shape
    img, _ = trim_barline_overshoot(img, ink_mask, staves, pad_above, pad_below, keep_above=VOLTAS)
    # Etendue horizontale des portees : on regarde toute la hauteur de chaque
    #  portee (les lignes inclinees d'un scan ne tiennent pas dans une seule
    #  rangee) et on garde le trait continu le plus long, en tolerant de tres
    #  petits trous. Un trou plus grand rejoindrait le texte de copyright
    #  imprime en vertical dans la marge.
    hole = max(3, int(0.0015 * w))
    xs0, xs1 = [], []
    for top, bottom, sp in staves:
        band = ink_mask[max(0, int(top - 3)):int(bottom + 4)].any(axis=0)
        r = longest_run(band, hole)
        if r:
            xs0.append(r[0])
            xs1.append(r[1])
    x0 = max(0, min(xs0) - int(0.005 * w)) if xs0 else 0
    x1 = min(w, max(xs1) + int(0.004 * w)) if xs1 else w

    bands = []
    for top, bottom, sp in staves:
        pa = pad_above
        if VOLTAS:
            by = find_volta_bracket(ink_mask, top, sp, w)
            if by is not None:
                pa = max(pad_above, (top - by) / sp + 1.8)   # le crochet + une marge (le numero 1./2. peut etre au-dessus du trait)
        bands.append((max(0, int(top - pa * sp)),
                      min(h, int(bottom + pad_below * sp))))
    merged = [list(bands[0])]
    for y0, y1 in bands[1:]:
        if y0 <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], y1)
        else:
            merged.append([y0, y1])

    if debug:
        from PIL import ImageDraw
        dbg = img.copy()
        d = ImageDraw.Draw(dbg)
        for top, bottom, sp in staves:
            d.rectangle((x0, top - 2, x1, bottom + 2), outline=(255, 0, 0), width=3)
        for y0, y1 in merged:
            d.rectangle((x0, y0, x1, y1), outline=(0, 160, 0), width=2)
        dbg.save(debug)

    gap = max(12, int(0.01 * h))
    total = sum(y1 - y0 for y0, y1 in merged) + gap * (len(merged) + 1)
    out = Image.new("RGB", (x1 - x0, total), "white")
    y = gap
    for y0, y1 in merged:
        out.paste(img.crop((x0, y0, x1, y1)), (0, y))
        y += (y1 - y0) + gap
    # Audiveris lit mal une partition dont l'interligne (ecart entre deux
    #  lignes de portee) est trop petit : on agrandit alors l'image.
    sp_mean = sum(sp for _, _, sp in staves) / len(staves)
    mi = MIN_INTERLINE if min_interline is None else min_interline
    if mi and sp_mean < mi:
        # facteur ENTIER : un agrandissement non entier (x1,1 par exemple) donne
        #  des lignes d'epaisseur irreguliere qui perturbent Audiveris.
        kf = min(4, int(np.ceil(mi / sp_mean)))
        out = out.resize((out.width * kf, out.height * kf), Image.LANCZOS)
    if BINARIZE:
        out = clean_levels(out, BINARIZE)
    return out, staves


def system_gap_threshold(gaps):
    """gaps : ecarts (en interlignes) entre portees consecutives de tout le
    document. Renvoie le seuil qui separe les ecarts "meme systeme" (petits et
    reguliers) des ecarts "entre systemes" (plus grands), ou None si la
    structure n'est pas nette."""
    g = sorted(gaps)
    if len(g) < 2:
        return None
    j = max(range(len(g) - 1), key=lambda i: g[i + 1] / max(g[i], 1e-6))
    a, b = g[j], g[j + 1]
    if b / max(a, 1e-6) < 1.25:
        return None
    small = g[:j + 1]
    if max(small) / max(min(small), 1e-6) > 1.25:
        return None
    return (a * b) ** 0.5


def split_systems(staves, thr):
    """Regroupe les portees consecutives dont l'ecart est inferieur a thr."""
    systems, cur = [], [staves[0]]
    for prev, nxt in zip(staves, staves[1:]):
        gap = (nxt[0] - prev[1]) / ((prev[2] + nxt[2]) / 2.0)
        if gap < thr:
            cur.append(nxt)
        else:
            systems.append(cur)
            cur = [nxt]
    systems.append(cur)
    return systems


def melody_staves(all_staves):
    """all_staves : liste (une entree par page) des portees detectees. Si le
    document a des systemes de plusieurs portees (flute / violon / guitare,
    piano main droite et main gauche...) tous de meme taille, renvoie pour
    chaque page la premiere portee de chaque systeme, sinon None."""
    gaps = []
    for st in all_staves:
        gaps += [(n[0] - p[1]) / ((p[2] + n[2]) / 2.0) for p, n in zip(st, st[1:])]
    thr = system_gap_threshold(gaps)
    if thr is None:
        return None
    pages = [split_systems(st, thr) if st else [] for st in all_staves]
    sizes = {len(s) for systems in pages for s in systems}
    if len(sizes) != 1 or min(sizes) < 2:
        return None
    return [[s[0] for s in systems] for systems in pages]


# ----------------------------------------------------------------------
# PDF <-> images
# ----------------------------------------------------------------------
def render_pdf(path, dpi=DPI):
    try:
        try:
            import pymupdf as fitz  # PyMuPDF recent
        except ImportError:
            import fitz  # anciennes versions
        pages = []
        with fitz.open(path) as doc:
            for page in doc:
                pix = page.get_pixmap(dpi=dpi)
                pages.append(Image.frombytes("RGB", (pix.width, pix.height), pix.samples))
        return pages
    except ImportError:
        pass
    exe = shutil.which("pdftoppm")
    if not exe:
        raise RuntimeError("Pour lire un PDF, installe PyMuPDF : pip install pymupdf")
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run([exe, "-r", str(dpi), "-png", str(path), os.path.join(tmp, "p")],
                       check=True, capture_output=True)
        return [Image.open(os.path.join(tmp, f)).convert("RGB")
                for f in sorted(os.listdir(tmp)) if f.endswith(".png")]


def process_pdf(src, dst, debug=False, melody=False, changed_only=False):
    """Ecrit dans dst un PDF (ou, si dst finit par .png, une image PNG par page,
    sans aucune compression avec perte) ne contenant que les portees. Avec
    melody=True, ne garde que la premiere portee de chaque systeme quand le
    document en compte plusieurs (partition a plusieurs instruments).
    Renvoie (pages, pages_recadrees, reduit) ; avec changed_only, un PDF sans
    portees multiples n'est pas ecrit."""
    pages = render_pdf(src)
    dets = [detect_staves(im) for im in pages]
    reduit = False
    if melody:
        sel = melody_staves([d[3] for d in dets])
        if sel is not None:
            dets = [(d[0], d[1], d[2], sel[i]) for i, d in enumerate(dets)]
            reduit = True
    if changed_only and not reduit:
        return len(pages), 0, False
    out_pages, n_ok = [], 0
    for n, (im, det) in enumerate(zip(pages, dets), 1):
        dbg = f"{str(dst)[:-4]}_debug_p{n}.png" if debug else None
        # Portee de melodie d'un systeme a plusieurs instruments : on laisse plus de place
        #  au-dessus (noms d'accords plus hauts) et moins en dessous (chiffres de tablature).
        pad_above, pad_below = (4.4, 1.8) if reduit else (3.3, 2.6)
        cropped, staves = crop_page(im, pad_above=pad_above, pad_below=pad_below, debug=dbg, detected=det)
        if cropped is None:
            out_pages.append(to_rgb_on_white(im))  # rien detecte : page conservee
        else:
            out_pages.append(cropped)
            n_ok += 1
    dst = str(dst)
    if dst.lower().endswith(".png"):
        base = dst[:-4]
        if len(out_pages) == 1:
            out_pages[0].convert("L").save(dst)
        else:
            for i, p in enumerate(out_pages, 1):
                p.convert("L").save(f"{base}_p{i}.png")
    else:
        gray = [p.convert("L") for p in out_pages]
        gray[0].save(dst, "PDF", resolution=float(DPI), save_all=True,
                     append_images=gray[1:], quality=98, subsampling=0)
    return len(pages), n_ok, reduit


# ----------------------------------------------------------------------
if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    a = sys.argv[1:]
    for x in list(a):
        if x == "--binarize":
            BINARIZE = 190
            a.remove(x)
        elif x.startswith("--binarize="):
            BINARIZE = int(x.split("=", 1)[1])
            a.remove(x)
        elif x == "--voltas":
            VOLTAS = True
            a.remove(x)
        elif x == "--melody":
            MELODY = True
            a.remove(x)
        elif x == "--changed-only":
            CHANGED_ONLY = True
            a.remove(x)
        elif x.startswith("--min-interline="):
            MIN_INTERLINE = float(x.split("=", 1)[1])
            a.remove(x)
    if a and a[0] == "--dir":
        src_dir, dst_dir = Path(a[1]), Path(a[a.index("--out") + 1])
        dst_dir.mkdir(parents=True, exist_ok=True)
        tot = ok = conserves = erreurs = reduits = 0
        liste = []
        for pdf in sorted(src_dir.glob("*.pdf")):
            tot += 1
            try:
                n, c, red = process_pdf(pdf, dst_dir / pdf.name, melody=MELODY,
                                        changed_only=CHANGED_ONLY)
                if CHANGED_ONLY and not red:
                    continue
                meta = pdf.with_name(pdf.name + ".meta.json")
                if meta.exists():
                    shutil.copyfile(meta, dst_dir / meta.name)
                ok += (c > 0)
                conserves += (c == 0)
                reduits += bool(red)
                if red:
                    liste.append(pdf.name)
                print(f"[{tot}] {pdf.name}: {c}/{n} pages recadrees" + (" | melodie seule" if red else ""))
            except Exception as e:
                erreurs += 1
                print(f"[{tot}] ERREUR {pdf.name}: {e}")
        if MELODY:
            (dst_dir / "melodie_seule.txt").write_text("\n".join(liste), encoding="utf-8")
        print(f"\nPDF : {tot} | recadres : {ok} | conserves tels quels (aucune portee detectee) : {conserves} | melodie seule : {reduits} | erreurs : {erreurs}")
    else:
        debug = "--debug" in a
        a = [x for x in a if x != "--debug"]
        src, dst = a[0], a[1]
        if src.lower().endswith(".pdf"):
            n, c, red = process_pdf(src, dst, debug=debug, melody=MELODY)
            print(f"{c}/{n} pages recadrees -> {dst}" + (" | melodie seule" if red else ""))
        else:
            out, staves = crop_page(Image.open(src),
                                    debug=(dst[:-4] + "_debug.png") if debug else None)
            print("portees detectees :", len(staves))
            if out is not None:
                out.save(dst)
                print("ecrit :", dst, out.size)
