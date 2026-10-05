"""
baloche_download.py

Etape 1 du pipeline BalFolkFriend cote Baloche : parcourt les pages de
style choisies sur baloche.onth.org, et pour chaque morceau trouve,
telecharge la MEILLEURE source disponible parmi :
    1. ABC        (utilisable directement)
    2. MIDI       (sera converti en ABC a l'etape 2, via midi2abc)
    3. MUSESCORE  (.mscz -- sera converti en ABC a l'etape 2, via
                   MuseScore en ligne de commande puis xml2abc.py)

Les autres sources (PDF, LILYPOND, AUDIO, IMAGE, TEF...) ne sont pas
telechargees pour l'instant.

Note sur les libelles : verifie empiriquement sur un echantillon, les
types de source sont rendus en MAJUSCULES sur les fiches Baloche pour
MUSESCORE / LILYPOND / AUDIO / IMAGE (et deja en majuscules pour
PDF / ABC / MIDI / TEF qui sont des sigles).

Sortie, dans --output-dir :
    raw/abc/<slug>.abc              (+ <slug>.abc.meta.json)
    raw/midi/<slug>.mid             (+ <slug>.mid.meta.json)
    raw/musescore/<slug>.mscz       (+ <slug>.mscz.meta.json)
    manifest.json                   (fiches deja traitees, pour reprise)

Installation:
    pip install requests beautifulsoup4

Exemple :
    python baloche_download.py --styles an-dro bourree scottish mazurka hanter-dro rond --output-dir ./BalFolkCorpus
"""

import argparse
import json
import re
import time
import unicodedata
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://baloche.onth.org"
HEADERS = {
    "User-Agent": (
        "BalFolkFriend-downloader/0.1 "
        "(projet personnel, usage non commercial)"
    )
}

SOURCE_EXT = {
    "ABC": ".abc",
    "MIDI": ".mid",
    "MUSESCORE": ".mscz",
    "PDF": ".pdf",
}
SOURCE_SUBDIR = {
    "ABC": "abc",
    "MIDI": "midi",
    "MUSESCORE": "musescore",
    "PDF": "pdf",
}
# Ordre de preference : on ne telecharge qu'UNE source par morceau.
# PDF est en dernier recours : convertible via Audiveris (OMR), mais la
# qualite est la moins fiable des quatre (a verifier a l'etape 2).
PRIORITY = ["ABC", "MIDI", "MUSESCORE", "PDF"]



def slugify(text):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text or "morceau"


def get_soup(url, session, delay):
    resp = session.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    time.sleep(delay)
    # resp.content (octets) et non resp.text : sans charset dans l'en-tete HTTP,
    # requests suppose ISO-8859-1 et produit du mojibake ("BourrÃ©e").
    return BeautifulSoup(resp.content, "html.parser")


def list_tune_urls_for_style(style_slug, session, delay, max_pages=200):
    tune_urls = []
    page = 1
    while page <= max_pages:
        url = f"{BASE_URL}/style/{style_slug}/"
        if page > 1:
            url = f"{BASE_URL}/style/{style_slug}/page/{page}/"
        try:
            soup = get_soup(url, session, delay)
        except requests.HTTPError:
            break

        links = soup.select('a[href*="/tune/"]')
        new_urls = []
        for a in links:
            href = a.get("href")
            if not href:
                continue
            full = urljoin(BASE_URL, href)
            if full not in tune_urls:
                new_urls.append(full)

        if not new_urls:
            break
        tune_urls.extend(new_urls)
        page += 1

    return tune_urls


FICHE_LABELS = {
    "Style": "style",
    "Tonalité": "tonalite",
    "Mode": "mode",
    "Mesure": "mesure",
    "Compositeur": "compositeurs",
    "Pays": "pays",
    "Région": "region",
    "Département": "departement",
    "Niveau": "niveau",
    "Ajouté le": "ajoute_le",
}


def _clean_value(v):
    v = (v or "").strip()
    return None if v in ("", "-", "–", "—") else v


def extract_fiche(soup):
    """Extrait les champs de la 'Fiche du morceau' a partir de la vraie structure
    de la page Baloche : chaque ligne est un '.meta-row' contenant un '.meta-key'
    (libelle, ex 'Pays') et un '.meta-val' (valeur, avec un ou plusieurs liens
    pour Style/Mesure/Compositeur/Pays/Région)."""
    fiche = {}
    for row in soup.select(".meta-row"):
        key_el = row.select_one(".meta-key")
        val_el = row.select_one(".meta-val")
        if not key_el:
            continue
        label = key_el.get_text(strip=True)
        field = FICHE_LABELS.get(label)
        if not field:
            continue
        if field == "compositeurs":
            links = val_el.find_all("a") if val_el else []
            fiche[field] = [a.get_text(strip=True) for a in links if a.get_text(strip=True)]
        else:
            fiche[field] = _clean_value(val_el.get_text(" ", strip=True)) if val_el else None
    for label, field in FICHE_LABELS.items():
        fiche.setdefault(field, [] if field == "compositeurs" else None)
    return fiche


_YT_RE = re.compile(
    r"https?://(?:www\.|m\.)?(?:youtube\.com/(?:watch\?(?:[^\"'\s<>]*?&)?v=|embed/|shorts/)|youtu\.be/)"
    r"([A-Za-z0-9_-]{11})"
)


def extract_youtube(soup):
    """Renvoie les liens YouTube (videos) presents dans la page (liens, iframes,
    donnees embarquees), normalises en https://www.youtube.com/watch?v=ID,
    sans doublon, dans l'ordre d'apparition."""
    html = str(soup).replace("\\/", "/").replace("&amp;", "&")
    seen, links = set(), []
    for m in _YT_RE.finditer(html):
        vid = m.group(1)
        if vid not in seen:
            seen.add(vid)
            links.append(f"https://www.youtube.com/watch?v={vid}")
    return links


def extract_sources(soup):
    """Renvoie la liste des {'type':..., 'href':...} trouves sur la fiche : chaque
    source est une carte '.bal-card.bal-card--interactive' contenant un badge de
    type ('.bal-badge', ex 'PDF'/'MIDI'/'MUSESCORE') et un lien 'a.btn-bal-dl'."""
    sources = []
    for card in soup.select(".bal-card.bal-card--interactive"):
        badge = card.select_one(".bal-badge")
        link = card.select_one("a.btn-bal-dl")
        if badge and link and link.get("href"):
            sources.append({
                "type": badge.get_text(strip=True),
                "href": urljoin(BASE_URL, link["href"]),
            })
    return sources


def download_file(url, dest_path, session, delay):
    resp = session.get(url, headers=HEADERS, timeout=30, stream=True)
    resp.raise_for_status()
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(dest_path, "wb") as f:
        for chunk in resp.iter_content(8192):
            f.write(chunk)
    time.sleep(delay)


def process_tune(tune_url, session, delay, output_dir, requested_style, priority=None):
    priority = priority or PRIORITY
    soup = get_soup(tune_url, session, delay)

    title_el = soup.find("h1")
    title = title_el.get_text(strip=True) if title_el else tune_url.rstrip("/").split("/")[-1]

    fiche = extract_fiche(soup)
    sources = extract_sources(soup)
    by_type = {s["type"]: s["href"] for s in sources}

    chosen_type = next((t for t in priority if t in by_type), None)
    # Nom de fichier = identifiant unique de la fiche (fin de l'URL) : deux morceaux
    # peuvent avoir le meme titre (ex: "Bourree trad"), l'un ecraserait l'autre.
    slug = tune_url.rstrip("/").split("/")[-1] or slugify(title)

    meta = {
        "title": title,
        "page_url": tune_url,
        "requested_style_slug": requested_style,
        "fiche": fiche,
        "youtube": extract_youtube(soup),
        "style": fiche.get("style"),
        "pays": fiche.get("pays"),
        "region": fiche.get("region"),
        "all_sources": sources,
        "chosen_source_type": chosen_type,
    }

    if chosen_type is None:
        meta["skipped_reason"] = "aucune source ABC/MIDI/MUSESCORE disponible"
        return meta, None

    ext = SOURCE_EXT[chosen_type]
    subdir = SOURCE_SUBDIR[chosen_type]
    dest = Path(output_dir) / "raw" / subdir / f"{slug}{ext}"

    if dest.exists():
        meta["skipped_reason"] = "deja telecharge"
        return meta, dest

    try:
        download_file(by_type[chosen_type], dest, session, delay)
    except requests.RequestException as e:
        meta["skipped_reason"] = f"erreur telechargement: {e}"
        return meta, None

    meta_path = dest.with_suffix(dest.suffix + ".meta.json")
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    return meta, dest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--styles", nargs="+", default=[])
    parser.add_argument("--tune-urls", nargs="+", default=[],
                         help="fiches precises a traiter (ex: pour un test sur un seul morceau)")
    parser.add_argument("--prefer", choices=["ABC", "MIDI", "MUSESCORE", "PDF"], default=None,
                         help="force ce type de source en premiere priorite (utile pour tester)")
    parser.add_argument("--output-dir", default="./BalFolkCorpus")
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--max-per-style", type=int, default=None,
                         help="limite pour un test rapide ; par defaut, tout le style")
    args = parser.parse_args()
    if not args.styles and not args.tune_urls:
        parser.error("donne au moins --styles ou --tune-urls")

    priority = PRIORITY
    if args.prefer:
        priority = [args.prefer] + [t for t in PRIORITY if t != args.prefer]

    session = requests.Session()
    output_dir = Path(args.output_dir)

    manifest_path = output_dir / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}

    counts = {"ABC": 0, "MIDI": 0, "MUSESCORE": 0, "PDF": 0, "skipped": 0}

    for style_slug in args.styles:
        print(f"\n=== Style: {style_slug} ===")
        urls = list_tune_urls_for_style(style_slug, session, args.delay)
        if args.max_per_style:
            urls = urls[: args.max_per_style]
        print(f"  {len(urls)} fiches trouvees")

        for i, tune_url in enumerate(urls, 1):
            if tune_url in manifest:
                continue
            try:
                try:
                    session.cookies.clear()
                    meta, dest = process_tune(tune_url, session, args.delay, output_dir, style_slug, priority)
                except Exception as e:
                    print(f'    ERREUR, morceau ignore : {tune_url} ({type(e).__name__}: {e})')
                    continue
            except requests.RequestException as e:
                print(f"  ! erreur sur {tune_url}: {e}")
                continue

            manifest[tune_url] = {
                "title": meta["title"],
                "chosen_source_type": meta.get("chosen_source_type"),
                "dest": str(dest) if dest else None,
            }

            if meta.get("chosen_source_type") and dest:
                counts[meta["chosen_source_type"]] += 1
                print(f"  [{i}/{len(urls)}] {meta['chosen_source_type']:10s} -> {meta['title']}")
            else:
                counts["skipped"] += 1
                print(f"  [{i}/{len(urls)}] SKIP ({meta.get('skipped_reason')}) -> {meta['title']}")

            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    for tune_url in args.tune_urls:
        print(f"\n=== Fiche: {tune_url} ===")
        try:
            try:
                session.cookies.clear()
                meta, dest = process_tune(tune_url, session, args.delay, output_dir, None, priority)
            except Exception as e:
                print(f'    ERREUR, morceau ignore : {tune_url} ({type(e).__name__}: {e})')
                continue
        except requests.RequestException as e:
            print(f"  ! erreur sur {tune_url}: {e}")
            continue
        print(json.dumps(meta["fiche"], ensure_ascii=False, indent=2))
        print(f"  sources: {[s['type'] for s in meta['all_sources']]}")
        print(f"  youtube: {meta['youtube']}")
        if meta.get("chosen_source_type") and dest:
            counts[meta["chosen_source_type"]] += 1
            print(f"  -> {meta['chosen_source_type']} telecharge: {dest}")
        else:
            counts["skipped"] += 1
            print(f"  SKIP ({meta.get('skipped_reason')})")

    print("\n=== Resume telechargement ===")
    for k, v in counts.items():
        print(f"{k:10s}: {v}")
    print(f"\nFichiers bruts dans: {output_dir / 'raw'}")


if __name__ == "__main__":
    main()
