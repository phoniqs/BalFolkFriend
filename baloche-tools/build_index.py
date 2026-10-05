"""
build_index.py
---------------
Convertit les fichiers .abc du corpus BalFolkFriend (recuperes sur
baloche.onth.org par baloche_download.py puis baloche_convert.py) en un index
FolkFriend valide : folkfriend-non-user-data-balfolk.json

Usage :
    python build_index.py [dossier_corpus] [fichier_sortie]

Sans argument : lit le dossier "corpus" a cote du script et ecrit
folkfriend-non-user-data-balfolk.json a cote du script.

A placer dans le meme dossier que abc_to_contour.py (import local).
"""
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote

from abc_to_contour import abc_to_contour, key_signature

# ----------------------------------------------------------------------
# Chemins relatifs a l'emplacement de ce script, pour que le depot soit
#  utilisable tel quel apres un simple "git clone", sans rien a adapter.
SCRIPT_DIR = Path(__file__).resolve().parent
ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
MIN_CONTOUR = 0           # --min-contour=N (facultatif, desactive par defaut) : ecarte les contours < N
for a in sys.argv[1:]:
    if a.startswith("--min-contour="):
        MIN_CONTOUR = int(a.split("=", 1)[1])
INPUT_DIR = Path(ARGS[0]) if len(ARGS) > 0 else SCRIPT_DIR / "corpus"
OUTPUT_FILE = (Path(ARGS[1]) if len(ARGS) > 1
               else SCRIPT_DIR / "folkfriend-non-user-data-balfolk.json")
# ----------------------------------------------------------------------

HEADER_LETTERS = set("XTMLKRCSNZBDFGHIOPQUVW")
HEADER_RE = re.compile(r'^\s*([A-Za-z]):\s?(.*)$')

MODE_EXPAND = {
    'maj': 'major', 'ion': 'ionian', 'min': 'minor', 'm': 'minor', '': 'major',
    'dor': 'dorian', 'phr': 'phrygian', 'lyd': 'lydian',
    'mix': 'mixolydian', 'loc': 'locrian', 'aeo': 'aeolian',
}

MID_BODY_VOICE_RE = re.compile(r'^\s*V:\s*(\S+)', re.MULTILINE)


def decode_pct(s):
    """Decode les sequences %XX d'un identifiant FolkWiki.
    UTF-8 d'abord, ISO-8859-1 en repli (%F6 = ö, %C4 = Ä, %E5 = å...)."""
    try:
        return unquote(s, encoding='utf-8', errors='strict')
    except UnicodeDecodeError:
        return unquote(s, encoding='latin-1')


def fix_mojibake(text):
    """Repare l'UTF-8 encode deux fois ('BÃ¶rtas' -> 'Börtas'), un defaut
    present dans certains fichiers scrapes (T:, O:, N:... et le page_title
    des .meta.json). Ne modifie le texte que si la reparation supprime le
    marqueur 'Ã' sans produire d'erreur ni de caractere invalide."""
    if 'Ã' not in text and 'Â' not in text:
        return text
    try:
        candidate = text.encode('latin-1').decode('utf-8')
    except (UnicodeDecodeError, UnicodeEncodeError):
        return text
    if 'Ã' in candidate or '\ufffd' in candidate:
        return text  # la "reparation" ne fait qu'empirer les choses, on garde l'original
    return candidate


def nom_lisible(identifiant):
    """'%C4lgabr%F6let_ea2d72' -> 'Älgabrölet' (sans le suffixe de hachage)."""
    nom = re.sub(r'_[0-9a-f]{6}$', '', identifiant)
    return decode_pct(nom).replace('_', ' ')


def titre_page(meta):
    """'FolkWiki | Musik / Trollpolska efter Hans Börtas'
    -> 'Trollpolska efter Hans Börtas' (titre de la page FolkWiki)."""
    t = (meta.get('page_title') or meta.get('title') or '').strip()
    return re.sub(r'^FolkWiki\s*\|\s*Musik\s*/\s*', '', t).strip()


def tous_les_titres(text):
    """Toutes les lignes T: de l'en-tete ABC (jusqu'a la ligne K: ou au
    premier contenu qui n'est pas un champ d'en-tete)."""
    titres = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == '' or stripped.startswith('%'):
            continue
        m = HEADER_RE.match(line)
        if not (m and m.group(1) in HEADER_LETTERS):
            break
        if m.group(1) == 'T' and m.group(2).strip():
            titres.append(m.group(2).strip())
        if m.group(1) == 'K':
            break
    return titres


def expand_mode(key_field):
    """'Ador' -> 'Adorian', 'D' -> 'Dmajor', 'Gmix' -> 'Gmixolydian'."""
    if not key_field or not key_field.strip():
        return ''
    m = re.match(r'\s*([A-Ga-g])([#b]?)\s*([A-Za-z]*)', key_field)
    if not m:
        return key_field.strip()
    root, acc, mode = m.group(1).upper(), m.group(2), m.group(3).lower()[:3]
    return root + acc + MODE_EXPAND.get(mode, 'major')


def premiere_voix_reelle(body_full):
    """Isole le contenu de la premiere voix qui contient reellement des
    notes, pour le contour de reconnaissance audio. Ignore les lignes de
    declaration de voix sans notes (ex. 'V:2 treble-8 stafflines=5' avant
    le vrai debut de la musique) et ne suppose pas que cette voix soit
    forcement numerotee '1' : certains fichiers de ce corpus etiquettent
    leur unique voix 'V:2' ou 'V:3'."""
    parts = re.split(r'^\s*V:\s*\S+[^\n]*\n?', body_full, flags=re.MULTILINE)
    for part in parts:
        # Certains fichiers placent un champ d'en-tete (Q:, L:, M:...) ou un
        #  commentaire (%...) juste apres K:, avant le "V:1" : ils se
        #  retrouvent alors dans ce segment sans etre de vraies notes.
        lines = part.splitlines()
        i = 0
        while i < len(lines):
            stripped = lines[i].strip()
            if stripped == '' or stripped.startswith('%'):
                i += 1
                continue
            m = HEADER_RE.match(lines[i])
            if m and m.group(1) in HEADER_LETTERS and m.group(1) != 'V':
                i += 1
                continue
            break
        cleaned = '\n'.join(lines[i:])
        if cleaned.strip():
            return cleaned
    return body_full  # aucun marqueur V: dans le fichier : tout est la melodie


def parse_abc_file(text):
    """Separe les champs d'en-tete (X:,T:,M:,L:,K:,R:,...) du corps musical.
    Renvoie le corps complet (toutes les voix, pour l'affichage et
    l'ecoute) et le corps de la premiere voix reelle seule, pour ne pas
    melanger melodie et accompagnement dans le contour de reconnaissance
    audio - une deuxieme voix fausserait sa forme."""
    lines = text.splitlines()
    headers = {}
    body_start = 0
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('%'):
            body_start = idx + 1
            continue
        if stripped == '':
            continue
        m = HEADER_RE.match(line)
        if m and m.group(1) in HEADER_LETTERS and len(m.group(1)) == 1:
            headers.setdefault(m.group(1), m.group(2).strip())
            body_start = idx + 1
            if m.group(1) == 'K':
                # K: est toujours le dernier champ d'en-tete en ABC ; tout ce
                #  qui suit (notamment un "V:1" ouvrant la premiere voix) fait
                #  partie du corps et doit etre preserve, pas avale comme un
                #  en-tete de plus.
                break
        else:
            break
    body_full = '\n'.join(lines[body_start:])

    # Corps limite a la premiere voix reelle, pour le contour uniquement.
    #  body_full (toutes les voix) reste utilise pour l'affichage et l'ecoute.
    body_melody = premiere_voix_reelle(body_full)

    return headers, body_full, body_melody


def main():
    abc_files = sorted(INPUT_DIR.glob('*.abc'))
    print(f"{len(abc_files)} fichiers .abc trouves dans {INPUT_DIR}")

    settings = {}
    aliases = {}
    n_ok, n_failed, n_empty = 0, 0, 0
    skipped = []   # (nom, raison) des morceaux laisses hors de l'index

    for idx, abc_path in enumerate(abc_files):
        meta_path = abc_path.with_suffix('.meta.json')
        try:
            meta = json.loads(meta_path.read_text(encoding='utf-8')) if meta_path.exists() else {}
        except Exception:
            meta = {}

        try:
            raw = abc_path.read_bytes()
            try:
                text = raw.decode('utf-8')
            except UnicodeDecodeError:
                # fichiers en ISO-8859-1 / Windows-1252
                text = raw.decode('cp1252', errors='replace')
            text = fix_mojibake(text)
        except Exception as e:
            print(f"  ! lecture impossible {abc_path.name}: {e}")
            n_failed += 1
            continue

        if meta:
            meta = {k: (fix_mojibake(v) if isinstance(v, str) else v) for k, v in meta.items()}

        headers, body_full, body_melody = parse_abc_file(text)
        # Conversion Audiveris sans mesure lue ("M:none") : il n'a pas reconnu
        #  les barres, la partition est presque toujours tronquee. Le morceau
        #  reste dans le corpus (needs_review) mais pas dans l'index.
        if meta.get('needs_review') and str(headers.get('M', '')).strip().lower() == 'none':
            skipped.append((abc_path.stem, 'M:none'))
            continue
        meter = headers.get('M', '4/4')
        mode = expand_mode(headers.get('K', ''))
        # Genre : R: du fichier, a defaut le style de la fiche Baloche
        #  (beaucoup d'ABC directs n'ont pas de R:).
        dance = headers.get('R', '') or str(meta.get('style') or '')

        try:
            contour = abc_to_contour(body_melody, headers.get('K', ''))
        except Exception as e:
            print(f"  ! conversion echouee {abc_path.name}: {e}")
            n_failed += 1
            continue

        if len(contour) < MIN_CONTOUR:
            n_empty += 1  # trop court pour etre reconnu : conversion ratee ou morceau vide
            skipped.append((abc_path.stem, f'contour {len(contour)} < {MIN_CONTOUR}'))
            continue

        # tune_id = page FolkWiki (regroupe les variantes d'un meme morceau,
        #  comme les X:1, X:2, X:3 d'une meme page thesession.org). Les
        #  .meta.json de ce corpus n'ont pas de page_id, mais page_url est
        #  unique par page et partage entre les fichiers d'une meme page :
        #  c'est donc la cle de regroupement.
        #  setting_id = ce fichier precis (une transcription particuliere).
        page_url_raw = str(meta.get('page_url', '')).strip()
        page_id = page_url_raw or str(meta.get('page_id', abc_path.stem))
        setting_id = abc_path.stem

        settings[setting_id] = {
            "tune_id": page_id,
            "meter": meter,
            "mode": mode,
            "abc": body_full.strip(),
            "dance": dance,
            "contour": contour,
            # Adresse de la page d'origine (affichee comme lien "Source"
            #  dans l'appli) ; le worker la retire avant de passer l'index
            #  au moteur WebAssembly.
            "source_url": str(meta.get('page_url', '')),
            # Ordre deterministe (position dans la liste triee). L'ancien
            #  int(st_mtime) donnait des valeurs identiques a des milliers de
            #  fichiers ecrits dans la meme seconde.
            "order": idx,
        }

        # Nom principal affiche : le premier T: du fichier (a defaut,
        #  l'identifiant decode, ex. "%C4lgabr%F6let_ea2d72" -> "Älgabrölet").
        #  Le genre (R:) et le mode (K:) sont deja affiches a part par
        #  l'appli ("Polska in Cmaj"), donc on ne les recolle pas au titre.
        nom_principal = (headers.get('T') or '').strip() or nom_lisible(setting_id)

        # Titres alternatifs, recherchables et affiches sous "Also known as" :
        #  les autres lignes T: du fichier (ex. "Rättviks trollpolska") et le
        #  titre de la page FolkWiki, s'ils different du nom principal.
        titre_wiki = titre_page(meta)
        # Conversions approximatives (OCR, MIDI) : les T: supplementaires sont du
        #  bruit ("El", "g#"...), pas des titres alternatifs.
        extras = [] if meta.get('needs_review') else tous_les_titres(text)[1:]
        candidats = [nom_principal] + extras
        if titre_wiki and titre_wiki.lower() != nom_principal.lower():
            candidats.append(titre_wiki)

        liste = aliases.setdefault(page_id, [])
        for n in candidats:
            if n and n not in liste:
                liste.append(n)
        n_ok += 1

    index = {"settings": settings, "aliases": aliases}
    OUTPUT_FILE.write_text(json.dumps(index, ensure_ascii=False), encoding='utf-8')

    rapport = OUTPUT_FILE.with_name("morceaux_ecartes.txt")
    rapport.write_text("\n".join(f"{n}\t{r}" for n, r in skipped), encoding="utf-8")
    n_m = sum(1 for _, r in skipped if r == 'M:none')
    print(f"\nTermine : {n_ok} morceaux dans l'index, {n_failed} echecs de lecture, "
          f"{len(skipped)} ecartes (M:none : {n_m}, contour trop court : {len(skipped) - n_m}).")
    print(f"Liste des ecartes : {rapport}")
    print(f"Fichier ecrit : {OUTPUT_FILE}")


if __name__ == '__main__':
    main()
