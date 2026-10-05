import os, re, sys
sys.stdout.reconfigure(encoding="utf-8")
RAW = r"BalFolkCorpus\raw\abc"

def read(p):
    b = open(p, "rb").read()
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        return b.decode("cp1252", errors="replace")

def extract(txt):
    m = re.search(r"^%<!--[ \t]*\r?$", txt, re.M)
    start = m.end() if m else 0
    e = re.search(r"^%-->", txt[start:], re.M)
    body = txt[start:start + e.start()] if e else txt[start:]
    body = re.sub(r"^%%beginsvg.*?^%%endsvg[^\n]*\n?", "", body, flags=re.M | re.S)
    x = re.search(r"^X:", body, re.M)
    if not x or not re.search(r"^K:", body, re.M):
        return None
    return body[x.start():].replace("\r\n", "\n").strip() + "\n"

def is_html(txt):
    return txt[:300].lstrip().lower().startswith(("<!doctype html", "<html"))

mode = sys.argv[1] if len(sys.argv) > 1 else "test"
if mode == "test":
    t = read(os.path.join(RAW, "a-grenade.abc"))
    print(extract(t) or "ECHEC : pas de X:/K: trouve")
else:
    ok = bad = 0
    fails = []
    for n in sorted(os.listdir(RAW)):
        if not n.endswith(".abc"):
            continue
        p = os.path.join(RAW, n)
        t = read(p)
        if not is_html(t):
            continue
        r = extract(t)
        if r:
            open(p, "w", encoding="utf-8", newline="\n").write(r)
            ok += 1
        else:
            bad += 1
            fails.append(n)
    print("extraits :", ok, "| echecs :", bad)
    for n in fails[:10]:
        print("  ", n)
