"""Generate Infiny Box README assets: banner + boundary diagram, light and dark.

Geometry is written once; only the palette differs between themes, so the two
files can never drift apart. Palette is taken from wsl/terminal-profile.json --
the terminal scheme is the brand, there is no second source of truth.
"""
from pathlib import Path

OUT = Path(__file__).resolve().parent / "assets"

DARK = dict(
    bg="#0E1116", chrome="#161B22", line="#30363D", panel="#161B22",
    fg="#ECF2F8", text="#C9D1D9", muted="#768390", dim="#545D68",
    accent="#4FC3F7", blue="#539BF5", green="#57AB5A", red="#F47067",
    yellow="#C69026", inset="#0E1116",
)
LIGHT = dict(
    bg="#FFFFFF", chrome="#F6F8FA", line="#D0D7DE", panel="#F6F8FA",
    fg="#1F2328", text="#1F2328", muted="#656D76", dim="#8C959F",
    accent="#0969DA", blue="#0969DA", green="#1A7F37", red="#CF222E",
    yellow="#9A6700", inset="#FFFFFF",
)

MONO = ('ui-monospace,"Cascadia Mono","SFMono-Regular",'
        '"Menlo",Consolas,"DejaVu Sans Mono",monospace')


def head(w, h, title, desc, p):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-labelledby="t d">
<title id="t">{title}</title><desc id="d">{desc}</desc>
<style>
  text {{ font-family: {MONO}; }}
  .fg {{ fill: {p['fg']}; }} .tx {{ fill: {p['text']}; }}
  .mu {{ fill: {p['muted']}; }} .dm {{ fill: {p['dim']}; }}
  .ac {{ fill: {p['accent']}; }} .bl {{ fill: {p['blue']}; }}
  .gr {{ fill: {p['green']}; }} .rd {{ fill: {p['red']}; }}
  .b {{ font-weight: 700; }}
</style>
'''


# ─────────────────────────────────────────────────────────── banner ──
def banner(p):
    W, H = 1280, 340
    s = head(W, H, "Infiny Box",
             "An AI terminal with a computer of its own. Its own Linux, its own "
             "root, its own web search. No model inside -- you bring your own.", p)

    # window frame + title bar
    s += f'<rect x="0" y="0" width="{W}" height="{H}" rx="12" fill="{p["bg"]}" stroke="{p["line"]}" stroke-width="2"/>\n'
    s += f'<path d="M12 0 H{W-12} A12 12 0 0 1 {W} 12 V46 H0 V12 A12 12 0 0 1 12 0 Z" fill="{p["chrome"]}"/>\n'
    s += f'<line x1="0" y1="46" x2="{W}" y2="46" stroke="{p["line"]}" stroke-width="2"/>\n'
    for i, c in enumerate((p["red"], p["yellow"], p["green"])):
        s += f'<circle cx="{28 + i*22}" cy="23" r="6" fill="{c}"/>\n'
    s += f'<text x="110" y="28" class="dm" font-size="14">root@infiny: ~</text>\n'

    # wordmark with a block cursor
    s += f'<rect x="84" y="106" width="11" height="56" fill="{p["accent"]}"/>\n'
    s += f'<text x="112" y="152" class="fg b" font-size="60" letter-spacing="5">INFINY BOX</text>\n'

    s += f'<text x="112" y="197" class="tx" font-size="22">An AI terminal with a computer of its own.</text>\n'
    s += f'<text x="112" y="227" class="mu" font-size="16">Its own Linux. Its own root. Its own web search.</text>\n'

    # install one-liner
    s += f'<rect x="84" y="256" width="452" height="44" rx="7" fill="{p["chrome"]}" stroke="{p["line"]}"/>\n'
    s += f'<text x="102" y="284" font-size="16"><tspan class="gr b">$</tspan><tspan class="tx" xml:space="preserve">  wsl --install --from-file infiny.wsl</tspan></text>\n'

    # pills, right-aligned
    pills = [("bring your own model", p["blue"]), ("nothing mounted", p["muted"]),
             ("Apache-2.0", p["muted"])]
    widths = [len(t) * 13 * 0.602 + 30 for t, _ in pills]
    x = W - 56 - sum(widths) - 2 * 12
    for (t, c), w in zip(pills, widths):
        s += f'<rect x="{x:.0f}" y="261" width="{w:.0f}" height="34" rx="17" fill="none" stroke="{p["line"]}" stroke-width="1.5"/>\n'
        s += f'<text x="{x + w/2:.0f}" y="283" font-size="13" fill="{c}" text-anchor="middle">{t}</text>\n'
        x += w + 12
    return s + "</svg>\n"


# ────────────────────────────────────────────────────────── boundary ──
def boundary(p):
    W, H = 1280, 560
    s = head(W, H, "What crosses the boundary and what does not",
             "Your machine on the left holds your files, your session and your "
             "model server. The Box on the right holds a root Linux with the "
             "agent, search and a browser. Nothing of yours is mounted and the "
             "Box cannot run programs on your side; the only crossing is the "
             "Box calling the model endpoint you pointed it at.", p)
    s += f'<rect x="0" y="0" width="{W}" height="{H}" fill="{p["bg"]}"/>\n'

    def panel(x, y, w, h, label):
        out = f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="none" stroke="{p["line"]}" stroke-width="2"/>\n'
        out += f'<rect x="{x+24}" y="{y-11}" width="{len(label)*12*0.602+24:.0f}" height="22" fill="{p["bg"]}"/>\n'
        out += f'<text x="{x+36}" y="{y+5}" class="mu b" font-size="12" letter-spacing="2.5">{label}</text>\n'
        return out

    def card(x, y, w, title, sub, accent=None, strike=False):
        out = f'<rect x="{x}" y="{y}" width="{w}" height="74" rx="8" fill="{p["panel"]}" stroke="{p["line"]}"/>\n'
        if accent:
            out += f'<rect x="{x}" y="{y}" width="4" height="74" rx="2" fill="{accent}"/>\n'
        cls = "dm" if strike else "tx"
        out += f'<text x="{x+22}" y="{y+30}" class="{cls} b" font-size="17">{title}</text>\n'
        out += f'<text x="{x+22}" y="{y+54}" class="dm" font-size="13">{sub}</text>\n'
        return out

    # left: your machine
    s += panel(48, 92, 400, 384, "YOUR MACHINE")
    s += card(76, 122, 344, "Your files", "C:\\  D:\\  ~/ — everything you have")
    s += card(76, 222, 344, "Your session", "browser logins, keys, ssh agent")
    s += card(76, 322, 344, "Your model server", "Ollama · LM Studio · llama.cpp · vLLM", p["blue"])
    s += f'<text x="98" y="424" class="bl" font-size="13">:11434 — bound to 0.0.0.0, by you</text>\n'

    # boundary band
    bx = 496
    s += f'<line x1="{bx+20}" y1="72" x2="{bx+20}" y2="496" stroke="{p["line"]}" stroke-width="2" stroke-dasharray="6 6"/>\n'
    s += f'<line x1="{bx+68}" y1="72" x2="{bx+68}" y2="496" stroke="{p["line"]}" stroke-width="2" stroke-dasharray="6 6"/>\n'
    s += f'<rect x="{bx+14}" y="238" width="60" height="94" fill="{p["bg"]}"/>\n'
    s += f'<text x="{bx+44}" y="285" class="mu b" font-size="13" letter-spacing="2.5" text-anchor="middle" transform="rotate(-90 {bx+44} 285)">WSL2 / DOCKER</text>\n'

    # right: the box
    s += panel(632, 92, 600, 384, "THE BOX")
    s += card(660, 122, 544, "root@infiny", "Debian 13, systemd, apt — a real machine", p["accent"])
    r = [("Hermes Agent", "reasoning, tools, approvals"),
         ("SearXNG :8080", "search, inside the Box"),
         ("Chromium", "renders JS pages, inside"),
         ("yazi · rg · fd · fzf", "the tooling you expect")]
    for i, (t, sub) in enumerate(r):
        cx = 660 + (i % 2) * 280
        cy = 222 + (i // 2) * 100
        s += f'<rect x="{cx}" y="{cy}" width="264" height="74" rx="8" fill="{p["panel"]}" stroke="{p["line"]}"/>\n'
        s += f'<text x="{cx+18}" y="{cy+30}" class="tx b" font-size="15">{t}</text>\n'
        s += f'<text x="{cx+18}" y="{cy+53}" class="dm" font-size="12">{sub}</text>\n'
    s += f'<text x="662" y="424" class="dm" font-size="13">host files mounted: none</text>\n'

    # crossings
    def blocked(y, label):
        out = f'<line x1="628" y1="{y}" x2="{bx+96}" y2="{y}" stroke="{p["red"]}" stroke-width="2" stroke-dasharray="5 5" opacity="0.85"/>\n'
        out += f'<line x1="452" y1="{y}" x2="{bx+4}" y2="{y}" stroke="{p["red"]}" stroke-width="2" stroke-dasharray="5 5" opacity="0.85"/>\n'
        c = bx + 44
        out += f'<circle cx="{c}" cy="{y}" r="13" fill="{p["bg"]}" stroke="{p["red"]}" stroke-width="2"/>\n'
        out += f'<path d="M{c-5} {y-5} L{c+5} {y+5} M{c+5} {y-5} L{c-5} {y+5}" stroke="{p["red"]}" stroke-width="2.2" stroke-linecap="round"/>\n'
        out += f'<text x="{c}" y="{y-24}" class="rd" font-size="12.5" text-anchor="middle">{label}</text>\n'
        return out

    # Labels here have to stay short: they sit in the 184px gutter between the
    # two panels, and anything longer runs underneath them. The sentence that
    # explains them lives on the closing line below.
    s += blocked(159, "not mounted")
    s += blocked(259, "interop off")

    # the one allowed crossing
    y = 359
    s += f'<path d="M628 {y} L456 {y}" stroke="{p["blue"]}" stroke-width="2.5" marker-end="url(#a)"/>\n'
    s += f'<defs><marker id="a" markerWidth="9" markerHeight="9" refX="8" refY="4.5" orient="auto"><path d="M0 0 L9 4.5 L0 9 z" fill="{p["blue"]}"/></marker></defs>\n'
    s += f'<text x="{bx+44}" y="{y-22}" class="bl b" font-size="12.5" text-anchor="middle">the one crossing</text>\n'

    # closing line
    s += f'<line x1="48" y1="500" x2="{W-48}" y2="500" stroke="{p["line"]}"/>\n'
    s += f'<text x="48" y="532" class="mu" font-size="15">Nothing of yours is reachable by default. Reaching further is a deliberate act — and the worst case is your files, not your session.</text>\n'
    return s + "</svg>\n"


# ──────────────────────────────────────────────────── social preview ──
def social(p):
    """1280x640 for GitHub's Settings -> Social preview.

    Read at thumbnail size in a feed, so it carries the name, one line of what
    it is, and nothing else. The install command and the pills from the banner
    are dropped: at the ~400px a Reddit card actually gets, they are texture
    rather than text.
    """
    W, H = 1280, 640
    s = head(W, H, "Infiny Box",
             "An AI terminal with a computer of its own. Bring your own model.", p)
    s += f'<rect x="0" y="0" width="{W}" height="{H}" fill="{p["bg"]}"/>\n'

    # Terminal chrome, so the card reads as a terminal before a word is read.
    s += f'<rect x="0" y="0" width="{W}" height="60" fill="{p["chrome"]}"/>\n'
    s += f'<line x1="0" y1="60" x2="{W}" y2="60" stroke="{p["line"]}" stroke-width="2"/>\n'
    for i, c in enumerate((p["red"], p["yellow"], p["green"])):
        s += f'<circle cx="{40 + i*28}" cy="30" r="8" fill="{c}"/>\n'
    s += f'<text x="146" y="37" class="dm" font-size="18">root@infiny: ~</text>\n'

    s += f'<rect x="90" y="218" width="16" height="86" fill="{p["accent"]}"/>\n'
    s += f'<text x="132" y="292" class="fg b" font-size="92" letter-spacing="6">INFINY BOX</text>\n'
    s += f'<text x="132" y="360" class="tx" font-size="34">An AI terminal with a computer of its own.</text>\n'
    s += f'<text x="132" y="406" class="mu" font-size="24">Its own Linux. Its own root. Its own web search.</text>\n'

    s += f'<line x1="90" y1="486" x2="{W-90}" y2="486" stroke="{p["line"]}"/>\n'
    # Two lines rather than one: naming the servers is what the audience scans
    # for, and "or any cloud API" is half the point of "no model inside" — a
    # single line long enough to hold both runs past the card.
    s += f'<text x="132" y="534" font-size="22"><tspan class="bl b">No model inside.</tspan><tspan class="mu" xml:space="preserve">  You bring your own.</tspan></text>\n'
    s += f'<text x="132" y="574" class="dm" font-size="20">Ollama · LM Studio · llama.cpp · vLLM · or any cloud API</text>\n'
    return s + "</svg>\n"


OUT.mkdir(parents=True, exist_ok=True)
for name, fn in (("banner", banner), ("boundary", boundary)):
    for theme, pal in (("dark", DARK), ("light", LIGHT)):
        f = OUT / f"{name}-{theme}.svg"
        f.write_text(fn(pal), encoding="utf-8")
        print(f"{f}  {f.stat().st_size:,} bytes")

# One theme only: a social card is a fixed image, not something the viewer's
# browser re-themes. Dark, because the product is a terminal.
f = OUT / "social-preview.svg"
f.write_text(social(DARK), encoding="utf-8")
print(f"{f}  {f.stat().st_size:,} bytes")
