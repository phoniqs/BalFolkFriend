import os, re, sys
sys.stdout.reconfigure(encoding="utf-8")
DIRS = [r"BalFolkCorpus\raw\abc", r"BalFolkCorpus\corpus"]

INFO_RE = re.compile(r"^[A-Za-z]:")


def read(p):
    b = open(p, "rb").read()
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        return b.decode("cp1252", errors="replace")


def systems_from_music(lines):
    """xml2abc coupe les lignes toutes les N mesures (commentaires %9, %17) et
    marque les fins de systeme par $. On rejoint les lignes et on recoupe aux
    $ : une ligne ABC = une portee de la partition d'origine. Un |: place en
    fin de systeme (reprise qui ouvre la portee suivante) est remonte en tete
    de la ligne suivante."""
    text = " ".join(l.strip() for l in lines if l.strip())
    parts = [p.strip() for p in text.split("$")]
    parts = [p for p in parts if p]
    out, carry = [], ""
    for p in parts:
        if carry:
            p = carry + " " + p
            carry = ""
        if p.endswith("|:"):
            p = p[:-2].rstrip()
            carry = "|:"
        out.append(p)
    if carry:
        if out:
            out[-1] += " |:"
        else:
            out.append("|:")
    return out


def strip_staccato(line):
    """Supprime les points de staccato (".c3" -> "c3"), hors annotations entre
    guillemets : Audiveris prend souvent le point de prolongation ou un point
    de reprise pour un staccato."""
    return re.sub(r'("[^"]*")|\.(?=[\^=_]*[A-Ga-g])', lambda m: m.group(1) or "", line)


def fix_voltas(text):
    """Un crochet "1" qui n'est jamais ferme par un "2" avant le "1" suivant est
    parasite (typiquement le trait long qui suit un nom d'accord, lu comme un
    crochet de reprise) : on le retire pour que la lecture ne saute pas de
    mesures."""
    toks = list(re.finditer(r":\|2|\|2|\[2|\|1|\[1", text))
    remove, open_tok = [], None
    for m in toks:
        if m.group().endswith("1"):
            if open_tok is not None:
                remove.append(open_tok)
            open_tok = m
        else:
            open_tok = None
    for m in reversed(remove):
        text = text[:m.start()] + ("|" if m.group().startswith("|") else "") + text[m.end():]
    return text


def clean(t, from_omr=False):
    t = t.replace("\r\n", "\n").lstrip("\ufeff")
    x = re.search(r"^X:", t, re.M)
    if x:
        t = t[x.start():]
    m = re.search(r"^(?:%--!?>|</?(?:body|html)\b)", t, re.M | re.I)
    if m:
        t = t[:m.start()]
    dollar = bool(re.search(r"^I:linebreak\s+\$", t, re.M))
    lines = []
    for line in t.split("\n"):
        if re.match(r"^\s*%(?!%)", line):
            continue
        if re.match(r"^[CN]:\s*(%.*)?$", line):
            continue
        if dollar and line.startswith("I:linebreak"):
            continue
        if not line.startswith("%%"):
            line = re.sub(r"\s+%(?!%).*$", "", line)
        lines.append(line.rstrip())
    voices = set()
    for l in lines:
        mv = re.match(r"^V:\s*(\S+)", l)
        if mv:
            voices.add(mv.group(1))
    if len(voices) == 1:
        lines = [l for l in lines if not l.startswith("V:")]

    if from_omr:
        # Conversions Audiveris : depuis que le texte est lu (OCR), il invente des
        #  paroles (w:) a partir de chiffres de tablature, des arpeges et des
        #  textes au-dessus de la portee ("^C r r"). Le contour les ignore deja ;
        #  on les retire pour que la partition affichee dans l'appli reste propre.
        lines = [l for l in lines if not re.match(r"^w:", l)]
        lines = [re.sub(r'"\^[^"]*"', "", l.replace("!arpeggio!", "")) for l in lines]
        # Accents, tenuto et "wedge" : presque toujours des lectures erronees (ligatures,
        #  points de prolongation) et ils encombrent la partition affichee.
        lines = [re.sub(r"!(?:tenuto|wedge|>)!", "", l) for l in lines]
        # Titres : seul le premier T: (celui de la fiche Baloche) est fiable ; les
        #  suivants viennent de l'OCR (chiffres de tablature, "El", "g#"...).
        k0 = next((i for i, l in enumerate(lines) if re.match(r"^K:", l)), len(lines))
        seen_t, filtered = False, []
        for i, l in enumerate(lines):
            if i < k0 and l.startswith("T:"):
                if seen_t:
                    continue
                seen_t = True
            filtered.append(l)
        lines = filtered

    # K:none (aucune alteration lue) -> K:C
    lines = [re.sub(r"^K:\s*none\b", "K:C", l) for l in lines]

    # En-tete = jusqu'a K: inclus ; le reste est le corps (musique, V:, %%)
    k = next((i for i, l in enumerate(lines) if re.match(r"^K:", l)), None)
    if k is None:
        return "\n".join(lines).strip() + "\n"
    header, body = lines[:k + 1], lines[k + 1:]

    out, buf = [], []

    def flush():
        if buf:
            if dollar:
                out.extend(systems_from_music(buf))
            else:
                out.extend(l for l in buf if l.strip())
            buf.clear()

    for l in body:
        if l.startswith("%%") or INFO_RE.match(l):
            flush()
            out.append(l)
        else:
            buf.append(strip_staccato(l))
    flush()
    if from_omr:
        out = fix_voltas("\n".join(out)).split("\n")
    return "\n".join(header + out).strip() + "\n"


mode = sys.argv[1] if len(sys.argv) > 1 else "test"
if mode == "test":
    p = sys.argv[2] if len(sys.argv) > 2 else r"BalFolkCorpus\corpus\a-grenade.abc"
    print(clean(read(p), "--omr" in sys.argv))
else:
    n = 0
    ignores = []
    for d in DIRS:
        for name in os.listdir(d):
            if not name.endswith(".abc"):
                continue
            p = os.path.join(d, name)
            from_omr = False
            mp = p[:-4] + ".meta.json"
            if os.path.exists(mp):
                try:
                    import json
                    from_omr = str(json.load(open(mp, encoding="utf-8")).get("conversion", "")).startswith("audiveris")
                except Exception:
                    pass
            txt = clean(read(p), from_omr)
            if "K:" not in txt:
                ignores.append(p)
                continue
            with open(p, "w", encoding="utf-8", newline="\n") as f:
                f.write(txt)
            n += 1
    print("nettoyes :", n, "| ignores (sans K:) :", len(ignores))
    for p in ignores[:10]:
        print("  ", p)
