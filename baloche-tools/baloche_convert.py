"""
baloche_convert.py

Etape 2 du pipeline BalFolkFriend : convertit les fichiers bruts
telecharges par baloche_download.py (MIDI, MuseScore) en ABC, et
rassemble tout (ABC direct + convertis) dans un dossier de corpus final
avec leurs .meta.json -- meme modele que le corpus Swedish Folkfriend.

Dependances externes (a installer separement, PAS via pip) :

- midi2abc (suite abcMIDI de James Allwright)
  Binaires Windows precompiles : chercher "abcMIDI windows binaries"
  (site historique ifdo.co.uk/abcmidi, miroirs multiples). Une fois
  installe, verifie que 'midi2abc' est dans le PATH, ou donne le
  chemin complet via --midi2abc-path.

- MuseScore 4 (ou 3), pour la conversion .mscz -> MusicXML en ligne de
  commande. Chemin typique sur Windows :
      "C:\\Program Files\\MuseScore 4\\bin\\MuseScore4.exe"
  a fournir via --musescore-path.

- xml2abc.py de Willem G. Vree (licence LGPL), pour la conversion
  MusicXML -> ABC. A telecharger depuis la page officielle :
      https://wim.vree.org/svgParse/xml2abc.html
  puis fournir le chemin du fichier .py telecharge via --xml2abc-path.

- Audiveris (licence AGPL), pour la reconnaissance optique de musique
  (OMR) des PDF -> MusicXML. A installer depuis :
      https://github.com/Audiveris/audiveris
  Emplacement par defaut sur Windows : "C:\\Program Files\\Audiveris\\Audiveris.exe"
  (a fournir via --audiveris-path si different).
  ATTENTION QUALITE : la conversion PDF est une reconnaissance d'image
  en une passe (pas de correction interactive), fiable surtout sur des
  PDF exportes proprement par un logiciel de notation, beaucoup moins
  sur des scans papier anciens. Les morceaux issus de cette etape sont
  marques "needs_review": true dans leur .meta.json -- a relire avant
  utilisation definitive dans BalFolkFriend.

Usage (PowerShell, chemins entre guillemets) :
    python baloche_convert.py --corpus-dir ./BalFolkCorpus `
        --musescore-path "C:\\Program Files\\MuseScore 4\\bin\\MuseScore4.exe" `
        --xml2abc-path "C:\\outils\\xml2abc.py" `
        --midi2abc-path "midi2abc" `
        --audiveris-path "C:\\Program Files\\Audiveris\\Audiveris.exe"

Chaque etape (MIDI, MuseScore, PDF) peut etre desactivee avec
--skip-midi / --skip-musescore / --skip-pdf si l'outil correspondant
n'est pas encore installe -- le script traite alors seulement ce qui
est disponible.
"""

import argparse
import json
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path


def convert_midi_to_abc(mid_path, midi2abc_path):
    result = subprocess.run(
        [midi2abc_path, str(mid_path)],
        capture_output=True, text=True, timeout=60
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise RuntimeError(f"midi2abc a echoue: {result.stderr[:300] or 'sortie vide'}")
    return result.stdout


def convert_mscz_to_abc(mscz_path, musescore_path, xml2abc_path, tmp_dir):
    xml_path = Path(tmp_dir) / (mscz_path.stem + ".musicxml")
    r1 = subprocess.run(
        [musescore_path, "-o", str(xml_path), str(mscz_path)],
        capture_output=True, text=True, timeout=120
    )
    if r1.returncode != 0 or not xml_path.exists():
        raise RuntimeError(f"MuseScore CLI a echoue: {r1.stderr[:300] or 'fichier de sortie absent'}")

    r2 = subprocess.run(
        ["python", "-X", "utf8", str(xml2abc_path), str(xml_path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60
    )
    if r2.returncode != 0 or not r2.stdout.strip():
        raise RuntimeError(f"xml2abc.py a echoue: {r2.stderr[:300] or 'sortie vide'}")

    return r2.stdout


def extract_musicxml_from_mxl(mxl_path, dest_dir):
    """Un .mxl est un zip contenant le vrai fichier MusicXML (+ META-INF/container.xml)."""
    with zipfile.ZipFile(mxl_path) as zf:
        candidates = [
            n for n in zf.namelist()
            if n.lower().endswith((".xml", ".musicxml")) and not n.startswith("META-INF/")
        ]
        if not candidates:
            raise RuntimeError(f"aucun fichier MusicXML trouve dans {mxl_path.name}")
        inner = candidates[0]
        zf.extract(inner, dest_dir)
        return Path(dest_dir) / inner


def convert_pdf_to_abc(pdf_path, audiveris_path, xml2abc_path, tmp_dir):
    out_dir = Path(tmp_dir) / f"omr_{pdf_path.stem}"
    out_dir.mkdir(parents=True, exist_ok=True)

    r1 = subprocess.run(
        [audiveris_path, "-batch", "-export", "-output", str(out_dir), str(pdf_path)],
        capture_output=True, text=True, timeout=300
    )
    mxl_files = sorted(out_dir.rglob("*.mxl"), key=lambda f: f.stat().st_size, reverse=True)  # le plus gros = le plus complet
    if r1.returncode != 0 or not mxl_files:
        raise RuntimeError(f"Audiveris a echoue: {r1.stderr[:300] or 'aucun .mxl produit'}")

    xml_path = extract_musicxml_from_mxl(mxl_files[0], out_dir)

    r2 = subprocess.run(
        ["python", "-X", "utf8", str(xml2abc_path), str(xml_path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60
    )
    if r2.returncode != 0 or not r2.stdout.strip():
        raise RuntimeError(f"xml2abc.py a echoue: {r2.stderr[:300] or 'sortie vide'}")

    return r2.stdout


def load_meta(source_file):
    meta_path = source_file.with_suffix(source_file.suffix + ".meta.json")
    if meta_path.exists():
        return json.loads(meta_path.read_text(encoding="utf-8"))
    return {}


MODE_BY_TONIC = {
    "C": "C", "D": "Ddor", "E": "Ephr", "F": "Flyd",
    "G": "Gmix", "A": "Am", "B": "Bloc",
}


def guess_key_from_last_note(abc_text):
    """K:none (aucune armure) : on suppose que la derniere note est la tonique
    et on en deduit le mode (A -> Am, D -> Ddor, G -> Gmix...). Heuristique."""
    body_lines = [
        l for l in abc_text.splitlines()
        if l.strip() and not re.match(r"^[A-Za-z]:", l) and not l.startswith("%")
    ]
    body = "\n".join(body_lines)
    body = re.sub(r"%.*", "", body)
    body = re.sub(r'"[^"]*"', "", body)
    body = re.sub(r"![^!]*!", "", body)
    body = re.sub(r"\{[^}]*\}", "", body)
    notes = re.findall(r"[=^_]*([A-Ga-g])", body)
    if not notes:
        return None
    return MODE_BY_TONIC.get(notes[-1].upper())


_BASE_FIFTHS = {"C": 0, "G": 1, "D": 2, "A": 3, "E": 4, "B": 5, "F": -1}
_MODE_SHIFT = {"": 0, "maj": 0, "ion": 0, "lyd": 1, "mix": -1, "dor": -2,
               "m": -3, "min": -3, "aeo": -3, "phr": -4, "loc": -5}
_FR_NOTES = {"do": "C", "ré": "D", "re": "D", "mi": "E", "fa": "F",
             "sol": "G", "la": "A", "si": "B"}
_FR_MODES = {"majeur": "", "ionien": "", "mineur": "m", "eolien": "m", "éolien": "m",
             "dorien": "dor", "mixolydien": "mix", "lydien": "lyd",
             "phrygien": "phr", "locrien": "loc"}


def key_fifths(k):
    """Nombre d'alterations de l'armure (+ dieses, - bemols) d'une tonalite ABC
    ('Am' -> 0, 'D' -> 2, 'Gmix' -> 0...). None si non reconnue."""
    m = re.match(r"^\s*([A-G])([#b]?)\s*([A-Za-z]*)", k or "")
    if not m:
        return None
    letter, acc, mode = m.group(1), m.group(2), m.group(3).lower()
    mode = mode[:3] if len(mode) >= 3 else mode
    if mode not in _MODE_SHIFT:
        return None
    fifths = _BASE_FIFTHS[letter] + (7 if acc == "#" else -7 if acc == "b" else 0)
    return fifths + _MODE_SHIFT[mode]


def fiche_key_to_abc(tonalite, mode):
    """('La', 'Mineur') -> 'Am' ; ('Ré', 'Dorien') -> 'Ddor'. None si incomplet/inconnu."""
    if not tonalite or not mode:
        return None
    m = re.match(r"^\s*(do|ré|re|mi|fa|sol|la|si)\s*([#♯b♭]?)\s*$", tonalite, re.I)
    suffix = _FR_MODES.get(mode.strip().lower())
    if not m or suffix is None:
        return None
    acc = "#" if m.group(2) in ("#", "♯") else "b" if m.group(2) in ("b", "♭") else ""
    return f"{_FR_NOTES[m.group(1).lower()]}{acc}{suffix}"


_PITCH = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
_NOTE_PAT = r"[=^_]*[A-Ga-g][,']*\d*(?:/\d*)?-?"
_CHORD_RE = re.compile(r"\[((?:%s)+)\](\d*(?:/\d*)?)" % _NOTE_PAT)
_TOKEN_RE = re.compile(r"([=^_]*)([A-Ga-g])([,']*)(\d*(?:/\d*)?)(-?)")


def _note_pitch(m):
    acc, letter, marks = m.group(1), m.group(2), m.group(3)
    p = _PITCH[letter.upper()] + (12 if letter.islower() else 0)
    p += 12 * marks.count("'") - 12 * marks.count(",")
    return p + acc.count("^") - acc.count("_")


def reduce_chords_to_melody(abc_text):
    """midi2abc sur un MIDI polyphonique (melodie + basse + accords) ecrit des
    accords [DDG,]2. On garde la note la plus haute de chaque accord (la melodie)
    et on supprime les lignes %%MIDI dupliquees. Renvoie (texte, nb_accords_reduits)."""
    count = 0

    def repl(m):
        nonlocal count
        toks = list(_TOKEN_RE.finditer(m.group(1)))
        if len(toks) < 2:
            return m.group(0)
        top = max(toks, key=_note_pitch)  # premiere occurrence en cas d'egalite
        count += 1
        acc, letter, marks, inner, tie = top.groups()
        outer = m.group(2)
        if inner and outer:
            return f"[{acc}{letter}{marks}{inner}]{outer}"
        return f"{acc}{letter}{marks}{inner or outer}{tie}"

    out, seen_midi = [], set()
    for line in abc_text.splitlines():
        if line.startswith("%%MIDI"):
            if line in seen_midi:
                continue
            seen_midi.add(line)
            out.append(line)
        elif re.match(r"^[A-Za-z]:", line) or line.startswith("%"):
            out.append(line)
        else:
            out.append(_CHORD_RE.sub(repl, line))
    return "\n".join(out) + "\n", count


def fix_mojibake(s):
    """'BourrÃ©e' -> 'Bourrée' (UTF-8 lu a tort en Latin-1/cp1252). Sans effet sinon."""
    if not isinstance(s, str) or not re.search("[ÃÂâ]", s):
        return s
    for enc in ("cp1252", "latin-1"):
        try:
            return s.encode(enc).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
    return s


def read_text_smart(path):
    """Lit un fichier texte : UTF-8 d'abord, sinon Windows-1252 (frequent dans les ABC anciens)."""
    data = Path(path).read_bytes()
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def postprocess_abc(abc_text, meta, conversion):
    """Nettoie les ABC issus de conversions (xml2abc, midi2abc) et les complete
    avec la 'Fiche du morceau' Baloche (meta['fiche']) : T:, C:, F:, O:, R:, S:, M:, K:.
    Les ABC directs sont laisses intacts. Renvoie (texte, infos_pour_meta)."""
    if conversion == "direct":
        return abc_text, {}

    info = {}
    fiche = {
        k: ([fix_mojibake(x) for x in v] if isinstance(v, list) else fix_mojibake(v))
        for k, v in (meta.get("fiche") or {}).items()
    }
    title = fix_mojibake(meta.get("title"))
    url = meta.get("page_url")

    if conversion == "midi2abc":
        abc_text, n_chords = reduce_chords_to_melody(abc_text)
        if n_chords:
            info["chords_reduced"] = n_chords

    # Champs d'en-tete (ordre alphabetique) : C: compositeurs, F: une ligne par
    # lien YouTube, O: origine, R: style, S: page Baloche
    new_fields = []
    if fiche.get("compositeurs"):
        new_fields.append(("C", ", ".join(fiche["compositeurs"])))
    for link in meta.get("youtube") or []:
        new_fields.append(("F", link))
    origin = ", ".join(
        x for x in (fiche.get("pays"), fiche.get("region"), fiche.get("departement")) if x
    )
    if origin:
        new_fields.append(("O", origin))
    if fiche.get("style"):
        new_fields.append(("R", fiche["style"]))
    if url:
        new_fields.append(("S", url))
    overridden = {k for k, _ in new_fields}

    text = abc_text.replace("!^!", "")  # artefact OMR (accords mal lus)
    lines = []
    for line in text.splitlines():
        if line.startswith("V:"):
            line = re.sub(r'\s+s?nm="[^"]*"', "", line)
        if len(line) > 1 and line[1] == ":" and line[0] in overridden:
            continue  # remplace par la valeur de la fiche
        lines.append(line)

    extra = [f"{k}:{v}" for k, v in new_fields]
    idx_t = next((i for i, l in enumerate(lines) if l.startswith("T:")), None)
    if idx_t is not None:
        first = [f"T:{title}"] if title else [lines[idx_t]]
        lines[idx_t:idx_t + 1] = first + extra
    else:
        idx_x = next((i for i, l in enumerate(lines) if l.startswith("X:")), -1)
        lines[idx_x + 1:idx_x + 1] = ([f"T:{title}"] if title else []) + extra

    # Mesure : la fiche fait foi
    meter = fiche.get("mesure")
    if meter:
        idx_m = next((i for i, l in enumerate(lines) if l.startswith("M:")), None)
        if idx_m is not None:
            old = lines[idx_m][2:].strip()
            if old and old != meter:
                info["meter_conflict"] = old
            lines[idx_m] = f"M:{meter}"
        else:
            idx_k = next((i for i, l in enumerate(lines) if l.startswith("K:")), len(lines))
            lines.insert(idx_k, f"M:{meter}")

    # Tonalite : la fiche fait foi, sauf si elle contredit l'armure reconnue
    idx_k = next((i for i, l in enumerate(lines) if l.startswith("K:")), None)
    fiche_k = fiche_key_to_abc(fiche.get("tonalite"), fiche.get("mode"))
    if idx_k is not None:
        current = lines[idx_k][2:].strip()
        is_none = current.lower() == "none"
        if fiche_k:
            if is_none or key_fifths(current) == key_fifths(fiche_k):
                lines[idx_k] = f"K:{fiche_k}"
                info["key_source"] = "fiche"
            else:
                info["key_conflict"] = fiche_k  # on garde l'armure reconnue
        elif is_none:
            guessed = guess_key_from_last_note("\n".join(lines))
            lines[idx_k] = f"K:{guessed or 'C'}"
            info["key_guessed"] = True

    return "\n".join(lines) + "\n", info


def write_output(corpus_dir, slug, abc_text, meta, conversion):
    abc_text, info = postprocess_abc(abc_text, meta, conversion)
    out_abc = corpus_dir / f"{slug}.abc"
    out_abc.write_text(abc_text, encoding="utf-8")
    meta = dict(meta)
    meta.update(info)
    meta["conversion"] = conversion
    # Conversions approximatives (devinette MIDI, reconnaissance optique) :
    # a relire avant usage definitif. ABC direct et MuseScore : fideles.
    meta["needs_review"] = conversion in ("midi2abc", "audiveris+xml2abc")
    (corpus_dir / f"{slug}.meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-dir", required=True,
                         help="dossier utilise par baloche_download.py (contient raw/ et manifest.json)")
    parser.add_argument("--musescore-path", default=None)
    parser.add_argument("--xml2abc-path", default=None)
    parser.add_argument("--midi2abc-path", default="midi2abc")
    parser.add_argument("--audiveris-path",
                         default=r"C:\Program Files\Audiveris\Audiveris.exe")
    parser.add_argument("--skip-musescore", action="store_true")
    parser.add_argument("--skip-midi", action="store_true")
    parser.add_argument("--skip-pdf", action="store_true")
    args = parser.parse_args()

    corpus_dir = Path(args.corpus_dir)
    raw_dir = corpus_dir / "raw"
    final_dir = corpus_dir / "corpus"
    final_dir.mkdir(parents=True, exist_ok=True)

    counts = {"abc_direct": 0, "midi2abc": 0, "musescore": 0, "audiveris_pdf": 0, "errors": 0}

    # 1) ABC directs : simple copie (deja au bon format)
    abc_raw_dir = raw_dir / "abc"
    if abc_raw_dir.exists():
        for abc_file in abc_raw_dir.glob("*.abc"):
            meta = load_meta(abc_file)
            write_output(
                final_dir, abc_file.stem,
                read_text_smart(abc_file),
                meta, "direct"
            )
            counts["abc_direct"] += 1

    # 2) MIDI -> ABC
    midi_raw_dir = raw_dir / "midi"
    midi_ok = Path(args.midi2abc_path).is_file() or shutil.which(args.midi2abc_path)
    if not args.skip_midi and midi_raw_dir.exists() and not midi_ok:
        print(
            f"MIDI : '{args.midi2abc_path}' n'est pas un executable midi2abc valide, "
            "cette etape est ignoree (il faut midi2abc.exe, pas runabc.tcl ; "
            "utilise --midi2abc-path ou --skip-midi)"
        )
    elif not args.skip_midi and midi_raw_dir.exists():
        for mid_file in midi_raw_dir.glob("*.mid"):
            meta = load_meta(mid_file)
            try:
                abc_text = convert_midi_to_abc(mid_file, args.midi2abc_path)
                write_output(final_dir, mid_file.stem, abc_text, meta, "midi2abc")
                counts["midi2abc"] += 1
            except Exception as e:
                print(f"  ! {mid_file.name}: {e}")
                counts["errors"] += 1

    # 3) MuseScore -> MusicXML -> ABC
    mscz_raw_dir = raw_dir / "musescore"
    if not args.skip_musescore and mscz_raw_dir.exists():
        if not args.musescore_path or not args.xml2abc_path:
            print(
                "MuseScore/xml2abc : chemins non fournis, cette etape est ignoree "
                "(utilise --musescore-path et --xml2abc-path pour l'activer)"
            )
        else:
            with tempfile.TemporaryDirectory() as tmp:
                for mscz_file in mscz_raw_dir.glob("*.mscz"):
                    meta = load_meta(mscz_file)
                    try:
                        abc_text = convert_mscz_to_abc(
                            mscz_file, args.musescore_path, args.xml2abc_path, tmp
                        )
                        write_output(final_dir, mscz_file.stem, abc_text, meta, "musescore+xml2abc")
                        counts["musescore"] += 1
                    except Exception as e:
                        print(f"  ! {mscz_file.name}: {e}")
                        counts["errors"] += 1

    # 4) PDF -> (Audiveris OMR) -> MusicXML -> ABC   [qualite variable]
    pdf_raw_dir = raw_dir / "pdf"
    if not args.skip_pdf and pdf_raw_dir.exists():
        if not args.xml2abc_path or not Path(args.audiveris_path).exists():
            print(
                "PDF/Audiveris : xml2abc ou Audiveris introuvable, cette etape est ignoree "
                "(verifie --xml2abc-path et --audiveris-path, ou utilise --skip-pdf)"
            )
        else:
            pdf_files = sorted(pdf_raw_dir.glob("*.pdf"))
            with tempfile.TemporaryDirectory() as tmp:
                for i, pdf_file in enumerate(pdf_files, 1):
                    meta = load_meta(pdf_file)
                    try:
                        abc_text = convert_pdf_to_abc(
                            pdf_file, args.audiveris_path, args.xml2abc_path, tmp
                        )
                        write_output(final_dir, pdf_file.stem, abc_text, meta, "audiveris+xml2abc")
                        counts["audiveris_pdf"] += 1
                        print(f"  [PDF {i}/{len(pdf_files)}] OK  {pdf_file.name}")
                    except Exception as e:
                        print(f"  [PDF {i}/{len(pdf_files)}] ! {pdf_file.name}: {e}")
                        counts["errors"] += 1

    print("\n=== Resume conversion ===")
    for k, v in counts.items():
        print(f"{k:15s}: {v}")
    print(f"\nCorpus final (.abc + .meta.json) dans: {final_dir}")


if __name__ == "__main__":
    main()
