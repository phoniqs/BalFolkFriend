import re
from itertools import groupby

# ---------------------------------------------------------------------------
# Table caractere <-> hauteur MIDI, telle que trouvee dans ff_config.rs
# ---------------------------------------------------------------------------
CHARS = ['a','b','c','d','e','f','g','h','i','j','k','l','m','n','o','p','q',
         'r','s','t','u','v','w','x','y','z','A','B','C','D','E','F','G','H',
         'I','J','K','L','M','N','O','P','Q','R','S','T','U','V']
MIDI_LOW = 48

PITCH_BASE = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}

# --- Armure (K:) : sept notes eventuellement alterees par defaut -----------
SHARP_ORDER = ['F', 'C', 'G', 'D', 'A', 'E', 'B']
FLAT_ORDER = ['B', 'E', 'A', 'D', 'G', 'C', 'F']

SIG_SHARPS = {0: [], 7: ['F'], 2: ['F', 'C'], 9: ['F', 'C', 'G'],
              4: ['F', 'C', 'G', 'D'], 11: ['F', 'C', 'G', 'D', 'A'],
              6: ['F', 'C', 'G', 'D', 'A', 'E']}
SIG_FLATS = {5: ['B'], 10: ['B', 'E'], 3: ['B', 'E', 'A'],
             8: ['B', 'E', 'A', 'D'], 1: ['B', 'E', 'A', 'D', 'G']}

# Decalage (en demi-tons, ajoute au ton final) pour retrouver la tonalite
# majeure "parente" de chaque mode, a partir de la tonique donnee.
MODE_TO_MAJOR_OFFSET = {
    'ion': 0, 'maj': 0, '': 0,
    'dor': 10, 'phr': 8, 'lyd': 7, 'mix': 5, 'aeo': 3, 'min': 3, 'm': 3,
    'loc': 1,
}


def key_signature(key_field):
    """Renvoie un set de lettres (A-G) alterees par defaut (+1 demi-ton si
    dieses, -1 si bemols), a partir du champ K: (ex: 'Ador', 'Gmix', 'D')."""
    if not key_field or key_field.strip().lower() in ('none', 'hp', 'exp'):
        return {}
    m = re.match(r'\s*([A-Ga-g])([#b]?)\s*([A-Za-z]*)', key_field)
    if not m:
        return {}
    root = m.group(1).upper()
    root_acc = m.group(2)
    mode = m.group(3).lower()[:3]
    tonic_pc = PITCH_BASE[root] + (1 if root_acc == '#' else -1 if root_acc == 'b' else 0)
    tonic_pc %= 12
    offset = MODE_TO_MAJOR_OFFSET.get(mode, 0)
    parent_pc = (tonic_pc + offset) % 12
    if parent_pc in SIG_SHARPS:
        return {letter: 1 for letter in SIG_SHARPS[parent_pc]}
    if parent_pc in SIG_FLATS:
        return {letter: -1 for letter in SIG_FLATS[parent_pc]}
    return {}


ACCIDENTAL_VAL = {'^': 1, '^^': 2, '=': 0, '_': -1, '__': -2}


def pitch_token_to_midi(text, key_sig):
    """text ex: '^^c,', '_B', "d'", 'F' -> hauteur MIDI absolue."""
    m = re.match(r"([\^=_]*)([A-Ga-g])([,']*)", text)
    acc_str, letter, oct_marks = m.group(1), m.group(2), m.group(3)

    base = PITCH_BASE[letter.upper()]
    # Octave ABC : 'C'..'B' = octave 4 (MIDI 60=C4 pour la lettre C
    #  majuscule), 'c'..'b' = octave 5.
    octave = 5 if letter.islower() else 4
    octave += oct_marks.count("'") - oct_marks.count(',')

    if acc_str:
        alter = ACCIDENTAL_VAL.get(acc_str, 0)
    else:
        alter = key_sig.get(letter.upper(), 0)

    midi = 12 * (octave + 1) + base + alter  # MIDI 60 = C4 (octave+1)*12+0
    return midi


def strip_non_musical(abc_body):
    """Retire tout ce qui n'affecte ni hauteur ni duree : accords guitare,
    annotations, decorations !x!, points de staccato isoles."""
    # Lignes qui ne sont pas de la musique : commentaires et directives
    #  (% et %%), champs d'information (w: paroles, W:, N:, Q:, P:, ...) et
    #  champs en ligne ([K:G]). Sans ce nettoyage, leurs lettres (a-g)
    #  seraient lues comme des notes et fausseraient le contour. Le
    #  (?![|:]) evite de confondre une note suivie d'une reprise ("A:|")
    #  avec un champ d'information.
    abc_body = re.sub(r'^[ \t]*%[^\n]*', '', abc_body, flags=re.MULTILINE)
    abc_body = re.sub(r'^[ \t]*[A-Za-z]:(?![|:])[^\n]*', '', abc_body, flags=re.MULTILINE)
    abc_body = re.sub(r'\[[A-Za-z]:[^\]\n]*\]', '', abc_body)
    abc_body = re.sub(r'"[^"]*"', '', abc_body)      # accords guitare "D" "Am" ...
    abc_body = re.sub(r'!\S*?!', '', abc_body)        # decorations !fff! etc.
    abc_body = re.sub(r'\{[^}]*\}', '', abc_body)     # notes d'agrement {ge}
    abc_body = re.sub(r'[\r\n]', ' ', abc_body)
    return abc_body


TOKEN_RE = re.compile(r"""
    (?P<tuplet>\(\d(?::\d)?(?::\d)?)     |  # triolet (3, (3:2 etc
    (?P<chord>\[[\^=_]*[A-Ga-g][,'^=_A-Ga-g]*\]\d*/?\d*)  | # accord [DA]6, [FA]2
    (?P<note>[\^=_]*[A-Ga-g][,']*\d*/*\d*)                | # note simple A2, ^c, d,
    (?P<rest>[zZxX]\d*/*\d*)                              | # silence
    (?P<broken>[><])                                      | # rythme pointe
    (?P<bar>\|:|:\||\|\]|\[\d|\||:)                        | # barres / reprises
    (?P<tie>-)                                             | # liaison
    (?P<skip>[./\s])                                         # points, slashs isoles, espaces
""", re.VERBOSE)


def parse_fraction(num, slashes, denom):
    if num and slashes:
        # ex: "3/2" -> 1.5 (et pas 3, piege precedent : le numerateur
        #  n'annule pas le denominateur quand les deux sont presents)
        d = float(denom) if denom else 2.0
        return float(num) / d
    if num:
        return float(num)
    if slashes:
        return 1 / float(denom) if denom else 1 / (2 ** len(slashes))
    return 1.0


NOTE_DUR_RE = re.compile(r"[\^=_]*([A-Ga-g])([,']*)(\d*)(/*)(\d*)")
CHORD_DUR_RE = re.compile(r"\](\d*)(/*)(\d*)")


def abc_to_events(abc_body, key_sig=None):
    """Renvoie une liste de (hauteur_MIDI_or_None, duree_en_unites_L).
    hauteur == None pour un silence (0 caractere produit)."""
    key_sig = key_sig or {}
    body = strip_non_musical(abc_body)
    events = []
    pending_tuplet = None  # (n, remaining)

    pos = 0
    tokens = []
    for m in TOKEN_RE.finditer(body):
        kind = m.lastgroup
        text = m.group()
        if kind in ('skip', 'tie', 'bar'):
            continue
        tokens.append((kind, text))

    # ratio "q" standard pour un triolet (n : n notes dans le temps de q
    TUPLET_Q = {2: 3, 3: 2, 4: 3, 5: 2, 6: 2, 7: 2, 8: 3, 9: 3}

    tuplet_remaining = 0
    tuplet_ratio = 1.0
    broken_pending = None  # '>' ou '<' en attente d'application

    i = 0
    while i < len(tokens):
        kind, text = tokens[i]
        if kind == 'tuplet':
            n = int(re.search(r'\d', text).group())
            if n == 0:
                # Pas un vrai triolet (ex: "(0" = annotation de doigte,
                #  corde a vide, courante dans les polskas) : on ignore.
                i += 1
                continue
            q = TUPLET_Q.get(n, n - 1 if n > 1 else 1)
            tuplet_remaining = n
            tuplet_ratio = q / n
            i += 1
            continue
        if kind == 'rest':
            m = re.match(r"[zZxX](\d*)(/*)(\d*)", text)
            dur = parse_fraction(m.group(1), m.group(2), m.group(3))
            events.append((None, dur))
            i += 1
            continue
        if kind in ('note', 'chord'):
            if kind == 'note':
                m = NOTE_DUR_RE.match(text)
                pitch = pitch_token_to_midi(text, key_sig)
                dur = parse_fraction(m.group(3), m.group(4), m.group(5))
            else:
                inner_tokens = re.findall(r"[\^=_]*[A-Ga-g][,']*", text)
                pitch = max(pitch_token_to_midi(t, key_sig) for t in inner_tokens)
                m = CHORD_DUR_RE.search(text)
                dur = parse_fraction(m.group(1), m.group(2), m.group(3))

            if tuplet_remaining > 0:
                dur *= tuplet_ratio
                tuplet_remaining -= 1

            if broken_pending == '>' and events:
                prev_pitch, prev_dur = events[-1]
                events[-1] = (prev_pitch, prev_dur * 1.5)
                dur *= 0.5
            elif broken_pending == '<' and events:
                prev_pitch, prev_dur = events[-1]
                events[-1] = (prev_pitch, prev_dur * 0.5)
                dur *= 1.5
            broken_pending = None

            events.append((pitch, dur))
            i += 1
            continue
        if kind == 'broken':
            broken_pending = text
            i += 1
            continue
        i += 1

    return events


MIDI_HIGH = 95


def render_contour_string(events):
    out = []
    for pitch, dur in events:
        if pitch is None:
            continue
        n_chars = int(dur + 0.5)  # arrondi au plus proche, PAS round() qui
                                    # arrondit 0.5 vers le bas (round-half-even)
        if n_chars <= 0:
            continue
        clamped = max(MIDI_LOW, min(MIDI_HIGH, pitch))
        out.append(CHARS[clamped - MIDI_LOW] * n_chars)
    return ''.join(out)


def abc_to_contour(abc_body, key_field):
    key_sig = key_signature(key_field)
    events = abc_to_events(abc_body, key_sig)
    return render_contour_string(events)


def events_to_char_count(events):
    total = 0.0
    for pitch, dur in events:
        if pitch is not None:
            total += dur
    return total


def run_self_test(samples):
    print(f"{'nom':40s} {'notes':>6s} {'dur_calc':>9s} {'len_reel':>9s} {'ecart':>7s}")
    for s in samples:
        events = abc_to_events(s['abc'])
        calc = events_to_char_count(events)
        real_len = len(s['contour'])
        n_notes = sum(1 for p, _ in events if p is not None)
        ecart = calc - real_len
        flag = "" if abs(ecart) < 0.01 else "  <-- ECART"
        print(f"{s['name'][:40]:40s} {n_notes:6d} {calc:9.2f} {real_len:9d} {ecart:7.2f}{flag}")


if __name__ == '__main__':
    samples = [
        {
            "name": "40344 reel simple",
            "abc": "BccB AFEF|A2BA F2E2|BccB AFEF|AFEF A2 A2|"
                   "BccB AFEF|A2BA F2E2|BccB AFEF|AFEF A2 A2|"
                   "A2Bc ecBc|ecBc AFED|A2Bc ecBc|AFEF A2 A2|"
                   "A2Bc ecBc|ecBc AFED|A2Bc ecBc|AFEF A2 A2|",
            "contour": "xzzxvsqsvvxvssqqxzzxvsqsvsqsvvvvxzzxvsqsvvxvssqqxzzxvsqsvsqsvvvvvvxzCzxzCzxzvsqovvxzCzxzvsqsvvvvvvxzCzxzCzxzvsqovvxzCzxzvsqsvvvv",
        },
        {
            "name": "5478 reel avec liaisons",
            "abc": "ABBA GEDE|G2AG EGDG|ABBA GEDE|GEDE G2GA|"
                   "ABBA GEDE|G2AG EGDG|ABBA GEDE|GEDE G2GD|"
                   "G2AB dBAB|dBAB AGED|G2AB dBAB|AGED G2GD|"
                   "G2AB dBAB|dBAB AGED|G2AB dBAB|AGED G2GA|",
            "contour": "vxxvtqoqttvtqtotvxxvtqoqtqoqtttvvxxvtqoqttvtqtotvxxvtqoqtqoqtttottvxAxvxAxvxvtqottvxAxvxvtqotttottvxAxvxAxvxvtqottvxAxvxvtqotttv",
        },
        {
            "name": "935 reel avec triolets (3Bce)",
            "abc": "|:DEEE GEGA|B3B BAGB|AAAB AGFG|(3Bce dB AGFA|"
                   "DEEE GEGA|B3B BAGB|AAAB AGFG|1 EGAE GAEG:|2 EGAG ABcd||",
            "contour": "oqqqtqtvxxxxxvtxvvvxvtstxzAxvtsvoqqqtqtvxxxxxvtxvvvxvtstxtvqtvqtoqqqtqtvxxxxxvtxvvvxvtstxCAxvtsv",
        },
    ]
    run_self_test(samples)
