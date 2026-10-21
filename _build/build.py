#!/usr/bin/env python3
"""
Roofing Website Template — static site generator.

Usage:  python3 _build/build.py
Reads:  _build/site.config.json, _build/content_*.py, _build/pages.py
Writes: the published site into the repository root (HTML pages, sitemap.xml, robots.txt, 404.html).

Per-client settings in site.config.json control the services offered ("services"), the brand colour
("accent"), the logo ("logo"), the client's own work photos ("photos"; see _build/photos.py), the
opening animation ("intro", "intro_scope"), the hero video ("hero_video") and the instant roof
estimate's pricing ("estimator").

Shared components (header, footer, CTA, schema, metadata) live in this file, so a change here updates
every page on the next build. Folders starting with "_" are never published.
"""
import json, os, re, html, posixpath, sys, math
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

from content_services import SERVICES as ALL_SERVICES
from content_cities import CITIES
from content_costs import COSTS, ASK
import pages as P
import photos as PH

CFG = json.load(open(os.path.join(HERE, "site.config.json"), encoding="utf-8"))
ALL_SVC = {s["slug"]: s for s in ALL_SERVICES}
# ---- services the client offers (config "services"; empty = all). Removing a slug drops its pages, menu and footer
# links, related-service links, sitemap entries and form options. Links to it inside other services' text become
# plain text and are listed in _build/removed-service-mentions.txt so those sentences can be reworded.
_wanted = CFG.get("services") or [s["slug"] for s in ALL_SERVICES]
_unknown = [x for x in _wanted if x not in ALL_SVC]
if _unknown:
    sys.exit(f"site.config.json: unknown service slug(s) {_unknown}. Valid: {[s['slug'] for s in ALL_SERVICES]}")
SERVICES = [s for s in ALL_SERVICES if s["slug"] in _wanted]
if not SERVICES:
    sys.exit("site.config.json: services is empty. List at least one service slug.")
SVC = {s["slug"]: s for s in SERVICES}
ALL_OFFERED = len(SERVICES) == len(ALL_SERVICES)
REMOVED_MENTIONS = {}
CITY = {c["slug"]: c for c in CITIES}
CATS = [
    ("systems", "Roof Systems", "Full replacements, metal, flat and new construction roofing, built from the deck up."),
    ("repair", "Repairs & Inspections", "Leaks, storm damage, inspections and the ventilation that keeps a roof healthy."),
    ("roofline", "Roofline & Skylights", "Gutters, soffit, fascia, skylights and the edges where water does its damage."),
]
CATS = [c for c in CATS if any(s["cat"] == c[0] for s in SERVICES)]

EST = dict(CFG.get("estimator") or {})
EST_ON = bool(EST.get("enabled", True))
INTRO_ON = bool(CFG.get("intro", True))
INTRO_SCOPE = CFG.get("intro_scope", "all")

def and_join(items):
    items = list(items)
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]

def related_of(s):
    return [r for r in s["related"] if r in SVC]

# ---- brand colour (config "accent", #rrggbb). Derived shades keep every text/background pair at WCAG AA.
def _rgb(h):
    h = h.lstrip("#"); return [int(h[i:i + 2], 16) for i in (0, 2, 4)]
def _lum(h):
    v = [x / 255 for x in _rgb(h)]
    v = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in v]
    return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2]
def contrast(a, b):
    la, lb = sorted((_lum(a), _lum(b)), reverse=True); return (la + 0.05) / (lb + 0.05)
def _mix(h, other, t):
    a, b = _rgb(h), _rgb(other); return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in zip(a, b))
def _darken_until(h, bg, target=4.5):
    t = 0.0
    while contrast(_mix(h, "#000000", t), bg) < target and t < 1:
        t += 0.02
    return _mix(h, "#000000", min(t, 1))

BG = "#0b0c0e"
ACCENT = (CFG.get("accent") or "#ff4d2d").strip()
if not re.fullmatch(r"#[0-9a-fA-F]{6}", ACCENT):
    sys.exit(f"site.config.json: accent must be a #rrggbb colour (got {ACCENT!r}).")
if contrast(ACCENT, BG) < 4.5 or contrast("#140b08", ACCENT) < 4.5:
    sys.exit(f"site.config.json: accent {ACCENT} is too dark: it is used as text on the dark page and behind dark button text "
             f"({contrast(ACCENT, BG):.1f}:1, needs 4.5:1). Pick a brighter version of the brand colour.")
ACCENT_2 = _mix(ACCENT, "#ffffff", 0.3)
ACCENT_ON_PAPER = _darken_until(ACCENT, "#ece9e4")

# ---- logo
LOGO_FILE = (CFG.get("logo") or "").strip()
if LOGO_FILE and not os.path.isfile(os.path.join(ROOT, LOGO_FILE.lstrip("/"))):
    sys.exit(f"site.config.json: logo file not found: {LOGO_FILE}")
LOGO_W, LOGO_H = 160, 44

def prep_logo():
    global LOGO_W, LOGO_H
    out = os.path.join(ROOT, "assets", "img", "client-logo.webp")
    if not LOGO_FILE:
        if os.path.exists(out): os.remove(out)
        return
    from PIL import Image
    im = Image.open(os.path.join(ROOT, LOGO_FILE.lstrip("/"))).convert("RGBA")
    im = im.crop(im.getchannel("A").getbbox() or (0, 0, im.width, im.height))
    if im.height > 240:
        im = im.resize((round(im.width * 240 / im.height), 240), Image.LANCZOS)
    im.save(out, "WEBP", quality=92, method=6)
    LOGO_W = max(1, round(im.width * LOGO_H / im.height))

PHOTOS = PH.load(CFG, ROOT, set(ALL_SVC), "site.config.json")
PHOTO_CLASSES = {"section": "section section--tight", "head": "sec-head", "kicker": "eyebrow", "h2": "display h-lg", "lead": "lead", "group_title": True}

BIZ = CFG["business_name"]
DOMAIN = CFG["domain"].rstrip("/")
BASE = CFG.get("base_path", "/")
PHONE = CFG["phone_display"]
TEL = CFG["phone_e164"]
CTA = CFG["cta_label"]
CITY_NAMES = [c["name"] for c in CITIES]

def city_list_text():
    return and_join(CITY_NAMES)

# ------------------------------------------------------------------ icons
UI = {
 "arrow": '<path d="M5 12h14M13 6l6 6-6 6"/>',
 "phone": '<path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1.9.4 1.8.7 2.7a2 2 0 0 1-.5 2.1L8 9.8a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.8.6 2.7.7a2 2 0 0 1 1.7 2z"/>',
 "chev": '<path d="M6 9l6 6 6-6"/>',
 "plus": '<path d="M12 5v14M5 12h14"/>',
 "pin": '<path d="M12 22s7-6.4 7-12a7 7 0 0 0-14 0c0 5.6 7 12 7 12z"/><circle cx="12" cy="10" r="2.5"/>',
 "star": '<path d="M2 15L12 6l10 9"/><path d="M6 15v4h12v-4"/>',
 "target": '<circle cx="12" cy="12" r="7"/><circle cx="12" cy="12" r="2"/><path d="M12 1v4M12 19v4M1 12h4M19 12h4"/>',
 "bolt": '<path d="M13 2L4 14h7l-1 8 9-12h-7z"/>',
 "check": '<path d="M4 12l5 5L20 6"/>',
}
SVC_ICONS = {
 "roof": ['M2 13L12 4l10 9', 'M5 11v9h14v-9', 'M7.5 14l4.5-4 4.5 4', 'M16 7V4h2v4.8'],
 "metal": ['M3 20h18', 'M4 20L12 5l8 15', 'M8.5 20L12 12l3.5 8', 'M12 5v15'],
 "flat": ['M2 9h20', 'M3 9v12h18V9', 'M3 9l1-3h16l1 3', 'M7 13h3v4H7z', 'M14 13h3v4h-3z'],
 "build": ['M5 21V3', 'M5 3h16', 'M5 7l4-4', 'M17 3v5', 'M15 8h4v3h-4z', 'M2 21h8'],
 "commercial": ['M4 21V5h10v16', 'M14 9h6v12', 'M2 21h20', 'M7 8h2M11 8h1M7 12h2M11 12h1M7 16h2M11 16h1M17 13h1M17 17h1'],
 "repair": ['M14 3l7 7-3 3-7-7z', 'M11 6l-8 8a2.1 2.1 0 0 0 3 3l8-8', 'M17.5 6.5l2-2'],
 "storm": ['M7 15a4 4 0 0 1-.4-8A5.5 5.5 0 0 1 17 7a4 4 0 0 1 0 8', 'M12.5 12l-2.5 4h4l-2.5 5'],
 "inspect": ['M2 12l8-7 8 7', 'M4 10.5V20h7', 'M13 16a3 3 0 1 0 6 0a3 3 0 1 0-6 0', 'M18.2 18.2L22 22'],
 "vent": ['M2 13L12 4l10 9', 'M5 11v9h14v-9', 'M8.5 15c1.2-1.2 2.3 1.2 3.5 0s2.3 1.2 3.5 0', 'M10 4.5V2h4v4.3'],
 "gutter": ['M2 6h20', 'M3 6v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V6', 'M17 11v8a2 2 0 0 0 2 2h2'],
 "soffit": ['M2 9l10-6 10 6', 'M4 9h16v4H4z', 'M7 13v2M10 13v2M13 13v2M16 13v2', 'M4 21V13M20 21V13'],
 "skylight": ['M2 14L12 4l10 10', 'M5 12v9h14v-9', 'M10 9.5l4-2.5v5l-4 2.5z'],
 "ice": ['M2 10L12 3l10 7', 'M4 10h16', 'M6 10v4M9 10v7M12 10v3M15 10v6M18 10v4'],
 "doc": ['M6 2h9l4 4v16H6z', 'M14 2v5h5', 'M9 12h7M9 16h7'],
 "home": ['M3 11l9-8 9 8', 'M5 9.5V21h14V9.5', 'M10 21v-6h4v6'],
 "sat": ['M3 3h18v18H3z', 'M6 16l6-8 6 8z', 'M12 8v8', 'M2 21L7 16'],
}

def ui(name, cls=""):
    c = f' class="{cls}"' if cls else ""
    return f'<svg{c} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">{UI[name]}</svg>'

def sicon(key, cls="svc-card__icon"):
    paths = "".join(f'<path pathLength="1" d="{d}"/>' for d in SVC_ICONS[key])
    return f'<svg class="{cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">{paths}</svg>'

LOGO_MARK = ('<svg class="brand__mark" viewBox="0 0 40 40" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">'
             '<path d="M3 21L20 6l17 15"/><path d="M9 28l11-9.5L31 28"/><path d="M13 35h14"/></svg>')

# ------------------------------------------------------------------ roof anatomy drawing (pinned sequence)
# A sloped roof plane in oblique view. Plane coordinates: u along the eave (0..1), v up the slope (0..1).
_A, _B, _D = (40, 380), (380, 452), (276, 168)
def _pt(u, v):
    return (_A[0] + u * (_B[0] - _A[0]) + v * (_D[0] - _A[0]), _A[1] + u * (_B[1] - _A[1]) + v * (_D[1] - _A[1]))
def _poly(u0, u1, v0, v1, dy=0):
    pts = [_pt(u0, v0), _pt(u1, v0), _pt(u1, v1), _pt(u0, v1)]
    return " ".join(f"{x:.1f},{y + dy:.1f}" for x, y in pts)
def _line(u0, v0, u1, v1, dy=0):
    a, b = _pt(u0, v0), _pt(u1, v1)
    return f"M{a[0]:.1f} {a[1] + dy:.1f}L{b[0]:.1f} {b[1] + dy:.1f}"

def roof_layers_svg(label):
    # extend the plane to the right so the ridge reads clearly: u runs 0..1.55
    U = 1.55
    g = []
    # 0 rafters / trusses (always visible)
    raf = "".join(_line(u, -0.02, u, 1.0, 34) for u in [i * 0.11 for i in range(15)])
    g.append(f'<g class="anat-base"><path class="ln ln--dim" d="{raf}"/><polygon class="ln ln--dim ln--dash" points="{_poly(0, U, 0, 1, 34)}"/></g>')
    # 1 deck: sheathing with seams
    seams = "".join(_line(0, v, U, v, 26) for v in (0.34, 0.68)) + "".join(_line(u, a, u, a + 0.34, 26) for i, a in enumerate((0, 0.34, 0.68)) for u in [x + (0.2 if i % 2 else 0) for x in (0.4, 0.8, 1.2)] if u < U)
    g.append(f'<g class="layer" data-layer="1"><polygon class="anat-deck" points="{_poly(0, U, 0, 1, 26)}"/><path class="anat-seam" d="{seams}"/></g>')
    # 2 ice & water at the eave + valley strip
    g.append(f'<g class="layer" data-layer="2"><polygon class="anat-ice" points="{_poly(0, U, 0, 0.3, 18)}"/><path class="anat-ice-edge" d="{_line(0, 0.3, U, 0.3, 18)}"/></g>')
    # 3 underlayment + drip edge
    prints = "".join(_line(0, v, U, v, 10) for v in [0.36 + i * 0.09 for i in range(7)])
    g.append(f'<g class="layer" data-layer="3"><polygon class="anat-under" points="{_poly(0, U, 0.3, 1, 10)}"/><path class="anat-print" d="{prints}"/><path class="anat-drip" d="{_line(-0.01, -0.012, U + 0.01, -0.012, 10)}"/></g>')
    # 4 shingles: courses parallel to the eave, staggered tab cuts
    rows, cuts = [], []
    n = 11
    for i in range(n):
        v0, v1 = i / n * 0.95, (i + 1) / n * 0.95
        rows.append(_line(0, v1, U, v1, 0))
        off = 0.06 if i % 2 else 0
        cuts += [_line(u, v0, u, v0 + (v1 - v0) * 0.55, 0) for u in [off + k * 0.12 for k in range(14)] if 0 < u < U]
    g.append(f'<g class="layer" data-layer="4"><polygon class="anat-shingle" points="{_poly(0, U, 0, 0.95, 0)}"/><path class="anat-row" d="{"".join(rows)}"/><path class="anat-cut" d="{"".join(cuts)}"/><path class="anat-starter" d="{_line(0, 0.004, U, 0.004, 0)}"/></g>')
    # 5 ridge vent + cap
    caps = "".join(_line(u, 0.93, u, 1.02, 0) for u in [k * 0.08 for k in range(1, 20)] if u < U)
    g.append(f'<g class="layer" data-layer="5"><polygon class="anat-ridge" points="{_poly(0, U, 0.93, 1.02, 0)}"/><path class="anat-cap" d="{caps}"/></g>')
    # callouts (text appears with each layer)
    tags = [(1, "Deck", 0.5, 0.12, 26), (2, "Ice & water", 1.3, 0.12, 18), (3, "Underlayment", 1.1, 0.62, 10), (4, "Shingles", 0.6, 0.5, 0), (5, "Ridge vent", 1.0, 0.98, 0)]
    callouts = ""
    for n_, t, u, v, dy in tags:
        x, y = _pt(u, v); y += dy
        callouts += (f'<g class="anat-tag" data-layer="{n_}"><circle cx="{x:.1f}" cy="{y:.1f}" r="4"/>'
                     f'<path d="M{x:.1f} {y:.1f}L{x + 40:.1f} {y - 46:.1f}H{x + 60:.1f}"/><text x="{x + 66:.1f}" y="{y - 41:.1f}">0{n_} {t.upper()}</text></g>')
    return (f'<svg class="anatomy" viewBox="0 0 700 500" role="img" aria-label="{html.escape(label)}">'
            f'{"".join(g)}{callouts}</svg>')

# ------------------------------------------------------------------ opening animation (shingle courses + name)
def intro_markup():
    rows = ""
    for i in range(7):
        y = 292 - i * 34
        half = 250 - i * 34 * 250 / 236   # follow the gable slope
        x0, x1 = 300 - half, 300 + half
        tabs = "".join(f'<path d="M{x:.0f} {y + 6}v14"/>' for x in range(int(x0) + (18 if i % 2 else 34), int(x1), 32))
        rows += f'<g class="intro__row" style="--r:{i}"><rect x="{x0:.0f}" y="{y}" width="{x1 - x0:.0f}" height="30"/>{tabs}</g>'
    return f'''<div class="intro" aria-hidden="true">
<div class="intro__panel intro__panel--top"></div><div class="intro__panel intro__panel--bot"></div>
<div class="intro__inner"><div class="intro__stage">
<svg class="intro__roof" viewBox="0 0 600 340" focusable="false"><defs><clipPath id="intro-clip"><path d="M50 326L300 90L550 326Z"/></clipPath></defs>
<g clip-path="url(#intro-clip)">{rows}</g>
<path class="intro__gable" pathLength="1" d="M30 336L300 72L570 336"/><path class="intro__ridge" pathLength="1" d="M262 108L300 72L338 108"/></svg>
<p class="intro__name">{html.escape(BIZ)}</p>
<div class="intro__meta"><span>{html.escape(CFG["short_tagline"])} · {html.escape(CFG["region_label"])}</span><span class="intro__count">000</span></div>
<div class="intro__bar"><i></i></div>
</div></div></div>'''

# ------------------------------------------------------------------ url helpers
def url_of(path):
    if path == "index.html":
        return DOMAIN + "/"
    if path.endswith("/index.html"):
        return DOMAIN + "/" + path[:-len("index.html")]
    return DOMAIN + "/" + path

def href(from_path, to_path):
    from_dir = posixpath.dirname(from_path)
    if to_path.endswith("index.html"):
        target_dir = posixpath.dirname(to_path)
        rel = posixpath.relpath(target_dir or ".", from_dir or ".")
        return "./" if rel == "." else rel + "/"
    return posixpath.relpath(to_path, from_dir or ".")

def asset(from_path, a):
    return posixpath.relpath("assets/" + a, posixpath.dirname(from_path) or ".")

_VER = {}
def vasset(from_path, a):
    """Asset URL with a content hash (?v=...), so browsers fetch the new file as soon as it changes after a deploy."""
    if a not in _VER:
        import hashlib
        _VER[a] = hashlib.md5(open(os.path.join(ROOT, "assets", a), "rb").read()).hexdigest()[:8]
    return asset(from_path, a) + "?v=" + _VER[a]

PATH = {
 "home": "index.html",
 "services": "services/index.html",
 "areas": "service-areas/index.html",
 "about": "about/index.html",
 "faq": "faq/index.html",
 "contact": "contact/index.html",
 "estimate": "roof-estimate/index.html",
 "thanks": "thank-you/index.html",
 "privacy": "privacy-policy.html",
 "terms": "terms-and-conditions.html",
 "cookies": "cookie-policy.html",
}
def svc_path(slug): return f"services/{slug}/index.html"
def svc_city_path(slug, city): return f"services/{slug}/{city}/index.html"
def city_path(city): return f"service-areas/{city}/index.html"
def quote_path():
    """Where 'get a price' buttons go: the instant estimate when it's on, else the contact form."""
    return PATH["estimate"] if EST_ON else PATH["contact"]

def expand(text, here):
    """Replace {biz}/{phone} tokens and [[slug|anchor]] links."""
    text = text.replace("{biz}", html.escape(BIZ)).replace("{phone}", html.escape(PHONE))
    def link(m):
        key, anchor = m.group(1), m.group(2)
        if key == "estimate" and not EST_ON: target = PATH["contact"]
        elif key.startswith("area:"): target = city_path(key[5:])
        elif key in PATH: target = PATH[key]
        elif key in SVC: target = svc_path(key)
        elif key in ALL_SVC:
            start = max(text.rfind(". ", 0, m.start()), text.rfind(">", 0, m.start())) + 1
            ends = [i for i in (text.find(". ", m.end()), text.find("<", m.end())) if i != -1]
            sentence = re.sub(r"\[\[[a-z0-9:\-]+\|([^\]]+)\]\]", r"\1", text[start:(min(ends) + 1 if ends else len(text))]).strip().rstrip("<").strip()
            REMOVED_MENTIONS.setdefault(sentence, set()).add(ALL_SVC[key]["name"])
            return anchor
        else: raise SystemExit(f"Unknown link target [[{key}]]")
        return f'<a href="{href(here, target)}">{anchor}</a>'
    return re.sub(r"\[\[([a-z0-9:\-]+)\|([^\]]+)\]\]", link, text)

# ------------------------------------------------------------------ shared components
def nav_html(here, active):
    def a(key, label):
        cur = ' aria-current="page"' if active == key else ""
        return f'<li class="nav__item"><a class="nav__link" href="{href(here, PATH[key])}"{cur}>{label}</a></li>'
    cols = ""
    for cat, label, _ in CATS:
        items = "".join(f'<li><a href="{href(here, svc_path(s["slug"]))}">{sicon(s["icon"], "")}{s["name"]}</a></li>' for s in SERVICES if s["cat"] == cat)
        cols += f'<div><p class="mega__title">{label}</p><ul>{items}</ul></div>'
    cols += f'<div class="mega__all"><span class="muted">{len(SERVICES)} services across {city_list_text()}</span><a class="link-arrow" href="{href(here, PATH["services"])}">All services {ui("arrow")}</a></div>'
    areas = "".join(f'<li><a href="{href(here, city_path(c["slug"]))}">{ui("pin")}{c["name"]}, {CFG["province"]}</a></li>' for c in CITIES)
    areas += f'<li><a href="{href(here, PATH["areas"])}">{ui("arrow")}All service areas</a></li>'
    svc_cur = ' aria-current="page"' if active == "services" else ""
    area_cur = ' aria-current="page"' if active == "areas" else ""
    est = ""
    if EST_ON:
        cur = ' aria-current="page"' if active == "estimate" else ""
        est = f'<li class="nav__item"><a class="nav__link nav__link--est" href="{href(here, PATH["estimate"])}"{cur}><i aria-hidden="true"></i>Instant Estimate</a></li>'
    return f'''<nav class="nav" aria-label="Main">
<ul class="nav__list">
<li class="nav__item" data-dropdown><button class="nav__link" type="button" aria-expanded="false" aria-controls="mega-services"{svc_cur}>Services {ui("chev")}</button>
<div class="mega" id="mega-services">{cols}</div></li>
<li class="nav__item" data-dropdown><button class="nav__link" type="button" aria-expanded="false" aria-controls="mega-areas"{area_cur}>Service Areas {ui("chev")}</button>
<div class="mega mega--small" id="mega-areas"><div><p class="mega__title">Where we work</p><ul>{areas}</ul></div></div></li>
{est}{a("about", "About")}{a("faq", "FAQ")}{a("contact", "Contact")}
</ul>
<div class="nav__cta"><a class="nav__phone" href="tel:{TEL}">{ui("phone")}<span>{PHONE}</span><span class="visually-hidden"> (call us)</span></a>
<a class="btn btn--primary btn--sm" href="{href(here, PATH["contact"])}">{CTA}</a></div>
</nav>'''

def mobile_nav_html(here):
    groups = ""
    for cat, label, _ in CATS:
        items = "".join(f'<li><a href="{href(here, svc_path(s["slug"]))}">{s["name"]}</a></li>' for s in SERVICES if s["cat"] == cat)
        groups += f'<li><p class="mobile-nav__group">{label}</p><ul>{items}</ul></li>'
    groups += f'<li><a href="{href(here, PATH["services"])}">All services →</a></li>'
    areas = "".join(f'<li><a href="{href(here, city_path(c["slug"]))}">{c["name"]}</a></li>' for c in CITIES)
    est = f'<li><a class="mobile-nav__est" href="{href(here, PATH["estimate"])}">Instant Estimate</a></li>' if EST_ON else ""
    return f'''<div class="mobile-nav" id="mobile-nav">
<ul>
<li><a href="{href(here, PATH["home"])}">Home</a></li>
{est}
<li><details><summary>Services {ui("plus")}</summary><ul>{groups}</ul></details></li>
<li><details><summary>Service Areas {ui("plus")}</summary><ul>{areas}<li><a href="{href(here, PATH["areas"])}">All service areas →</a></li></ul></details></li>
<li><a href="{href(here, PATH["about"])}">About</a></li>
<li><a href="{href(here, PATH["faq"])}">FAQ</a></li>
<li><a href="{href(here, PATH["contact"])}">Contact</a></li>
</ul>
<div class="mobile-nav__cta"><a class="btn btn--primary" href="{href(here, PATH["contact"])}">{CTA} {ui("arrow")}</a><a class="btn btn--ghost" href="tel:{TEL}">{ui("phone")} Call {PHONE}</a></div>
</div>'''

def brand_inner(here):
    if LOGO_FILE:
        return f'<img class="brand__logo" src="{asset(here, "img/client-logo.webp")}" alt="{html.escape(BIZ)}" width="{LOGO_W}" height="{LOGO_H}" decoding="async">'
    return f'{LOGO_MARK}<span class="brand__name">{html.escape(BIZ.split(" ")[0])}<small>{html.escape(" ".join(BIZ.split(" ")[1:]) or CFG["short_tagline"])}</small></span>'

def header_html(here, active):
    return f'''<div class="progress" aria-hidden="true"></div>
<header class="site-header">
<div class="wrap">
<a class="brand" href="{href(here, PATH["home"])}" aria-label="{html.escape(BIZ)} home">{brand_inner(here)}</a>
{nav_html(here, active)}
<button class="burger" type="button" aria-expanded="false" aria-controls="mobile-nav" aria-label="Open menu"><span></span><span></span><span></span></button>
</div>
</header>
{mobile_nav_html(here)}'''

def hours_text():
    return [f'{h["label"]}: {fmt_time(h["open"])}–{fmt_time(h["close"])}' for h in CFG.get("hours") or []]

def fmt_time(t):
    hh, mm = map(int, t.split(":"))
    suf = "a.m." if hh < 12 else "p.m."
    h12 = hh % 12 or 12
    return f"{h12}:{mm:02d} {suf}" if mm else f"{h12} {suf}"

def cta_band(here, title="Let's put a real roof over your head.", text=None):
    text = text or ("Get a ballpark in about a minute with the instant estimate, or book an inspection for a written, itemized quote." if EST_ON
                    else "Book an inspection and we'll give you a written, itemized quote before any work begins.")
    second = (f'<a class="btn btn--ghost" href="{href(here, PATH["estimate"])}">{ui("target")} Instant estimate</a>' if EST_ON
              else f'<a class="btn btn--ghost" href="tel:{TEL}">{ui("phone")} {PHONE}</a>')
    return f'''<section class="cta-band" aria-labelledby="cta-title">
<div class="cta-band__rows" aria-hidden="true"></div>
<div class="wrap">
<div><h2 class="display" id="cta-title" data-reveal="rise">{title}</h2><p data-reveal="up">{text}</p></div>
<div class="btn-row" data-reveal="up"><a class="btn btn--primary" href="{href(here, PATH["contact"])}">{CTA} {ui("arrow")}</a>{second}<a class="cta-band__tel" href="tel:{TEL}">or call {PHONE}</a></div>
</div>
</section>'''

def footer_html(here):
    cols = ""
    for cat, label, _ in CATS:
        items = "".join(f'<li><a href="{href(here, svc_path(s["slug"]))}">{s["name"]}</a></li>' for s in SERVICES if s["cat"] == cat)
        cols += f'<div class="footer__col"><h2>{label}</h2><ul>{items}</ul></div>'
    areas = "".join(f'<li><a href="{href(here, city_path(c["slug"]))}">{c["name"]}</a></li>' for c in CITIES)
    company = (f'<li><a href="{href(here, PATH["about"])}">About</a></li>'
               + (f'<li><a href="{href(here, PATH["estimate"])}">Instant Roof Estimate</a></li>' if EST_ON else "")
               + f'<li><a href="{href(here, PATH["services"])}">All Services</a></li>'
               f'<li><a href="{href(here, PATH["areas"])}">Service Areas</a></li><li><a href="{href(here, PATH["faq"])}">FAQ</a></li><li><a href="{href(here, PATH["contact"])}">Contact</a></li>')
    hours = "<br>".join(hours_text())
    links = [("Google Business Profile", CFG.get("google_business_profile_url"))] + [(p.get("name"), p.get("url")) for p in CFG.get("social_profiles", [])]
    links = [(n, u) for n, u in links if u]
    profiles = ("<li><span>Find us</span>" + " · ".join(f'<a href="{html.escape(u)}" rel="noopener">{html.escape(n)}</a>' for n, u in links) + "</li>") if links else ""
    return f'''<footer class="site-footer">
<div class="wrap">
<div class="footer__grid">
<div class="footer__brand">
<a class="brand" href="{href(here, PATH["home"])}" aria-label="{html.escape(BIZ)} home">{brand_inner(here)}</a>
<p>Roofing for homes and businesses in {city_list_text()}, {CFG["province"]}.</p>
<ul class="footer__contact">
<li><span>Call</span><a href="tel:{TEL}">{PHONE}</a></li>
<li><span>Email</span><a href="mailto:{CFG["email"]}">{CFG["email"]}</a></li>
<li><span>Hours</span>{hours}</li>
{profiles}
</ul>
</div>
{cols}
<div class="footer__col"><h2>Service Areas</h2><ul>{areas}</ul><h2 class="mt-2">Company</h2><ul>{company}</ul></div>
</div>
<p class="footer__huge" aria-hidden="true">{html.escape(BIZ.split(" ")[0])}</p>
<div class="footer__bottom">
<p>© {date.today().year} {html.escape(CFG["legal_name"])}. All rights reserved.</p>
<ul><li><a href="{href(here, PATH["privacy"])}">Privacy Policy</a></li><li><a href="{href(here, PATH["terms"])}">Terms &amp; Conditions</a></li><li><a href="{href(here, PATH["cookies"])}">Cookie Policy</a></li></ul>
</div>
</div>
</footer>
<div class="callbar"><a class="btn btn--ghost" href="tel:{TEL}">{ui("phone")} Call</a><a class="btn btn--primary" href="{href(here, quote_path())}">{"Instant Estimate" if EST_ON else CTA}</a></div>'''

def crumbs_html(here, trail):
    items = []
    for label, p in trail:
        items.append(f'<li><span aria-current="page">{label}</span></li>' if p is None else f'<li><a href="{href(here, p)}">{label}</a></li>')
    return f'<nav class="crumbs" aria-label="Breadcrumb"><ol>{"".join(items)}</ol></nav>'

def crumbs_schema(trail, here):
    lst = [{"@type": "ListItem", "position": i, "name": html.unescape(re.sub("<[^>]+>", "", label)), "item": url_of(p if p else here)} for i, (label, p) in enumerate(trail, 1)]
    return {"@type": "BreadcrumbList", "itemListElement": lst}

def business_ref():
    return {"@type": "RoofingContractor", "@id": DOMAIN + "/#business", "name": BIZ, "url": DOMAIN + "/", "telephone": TEL}

def business_entity():
    e = {
        "@type": "RoofingContractor",
        "@id": DOMAIN + "/#business",
        "name": BIZ,
        "url": DOMAIN + "/",
        "logo": DOMAIN + "/assets/img/logo.png",
        "image": DOMAIN + "/assets/img/og-default.png",
        "telephone": TEL,
        "email": CFG["email"],
        "areaServed": [{"@type": "City", "name": f'{c["name"]}, {CFG["province"]}'} for c in CITIES],
        "knowsAbout": [s["name"] for s in SERVICES],
    }
    if CFG.get("legal_name") and CFG["legal_name"] != BIZ:
        e["legalName"] = CFG["legal_name"]
    a = CFG.get("address")
    if a:
        e["address"] = {"@type": "PostalAddress", "streetAddress": a["street"], "addressLocality": a["city"], "addressRegion": a["region"], "postalCode": a["postal"], "addressCountry": CFG["country"]}
    if CFG.get("hours"):
        e["openingHoursSpecification"] = [{"@type": "OpeningHoursSpecification", "dayOfWeek": h["days"], "opens": h["open"], "closes": h["close"]} for h in CFG["hours"]]
    same = [u for u in [CFG.get("google_business_profile_url")] + [p.get("url") for p in CFG.get("social_profiles", [])] if u]
    if same:
        e["sameAs"] = same
    return e

PAGES = []

def demo_bar():
    if not CFG.get("demo_mode"):
        return ""
    return ('<aside class="demo-bar" aria-label="Website demo notice">Website demo: the business name, phone, email, service areas and estimate pricing on this site are '
            'samples, not a real company.</aside>')

def page(path, *, title, desc, body, active=None, crumbs=None, schema=None, noindex=False, og_type="website", head_extra="", scripts_extra="", body_class=""):
    full_title = title if BIZ in title else f"{title} | {BIZ}"
    if len(full_title) > 65 and BIZ not in title:
        full_title = title
    robots = "noindex, follow" if (noindex or CFG.get("demo_mode")) else "index, follow"
    graph = list(schema or [])
    if crumbs:
        graph.append(crumbs_schema(crumbs, path))
    ld = ""
    if graph:
        ld = '<script type="application/ld+json">' + json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/") + "</script>"
    canonical = url_of(path) if path != "404.html" else DOMAIN + "/404.html"
    verify = f'<meta name="google-site-verification" content="{html.escape(CFG["google_site_verification"])}">' if CFG.get("google_site_verification") else ""
    # Opening animation: plays on whichever indexable page a visitor opens first in a browser session (e.g. a service
    # page from Google), then never again that session. Skipped when the URL has a #hash, for reduced motion, on the
    # 404 and thank-you pages, and everywhere when config "intro" is false ("intro_scope": "home" = home page only).
    intro_here = INTRO_ON and not noindex and (INTRO_SCOPE == "all" or path == "index.html")
    if intro_here:
        boot = ('<script>(function(d){d.className=d.className.replace("no-js","js");try{if(sessionStorage.getItem("rf-intro")||location.hash.length>1||'
                'matchMedia("(prefers-reduced-motion: reduce)").matches)d.className+=" no-intro"}catch(e){d.className+=" no-intro"}})(document.documentElement)</script>')
    else:
        boot = '<script>document.documentElement.className=document.documentElement.className.replace("no-js","js");</script>'
    html_cls = "no-js" + (" has-demo" if CFG.get("demo_mode") else "") + ("" if intro_here else " no-intro")
    out = f'''<!doctype html>
<html lang="en-CA" class="{html_cls}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(full_title)}</title>
<meta name="description" content="{html.escape(desc)}">
<meta name="robots" content="{robots}">
<link rel="canonical" href="{canonical}">
{verify}
<meta property="og:type" content="{og_type}">
<meta property="og:site_name" content="{html.escape(BIZ)}">
<meta property="og:title" content="{html.escape(full_title)}">
<meta property="og:description" content="{html.escape(desc)}">
<meta property="og:url" content="{canonical}">
<meta property="og:image" content="{DOMAIN}/assets/img/og-default.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="{html.escape(BIZ)} — roofing in {html.escape(CFG["region_label"])}">
<meta property="og:locale" content="en_CA">
<meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="{BG}">
<link rel="icon" href="{asset(path, "img/favicon.svg")}" type="image/svg+xml">
<link rel="icon" href="{asset(path, "img/favicon-32.png")}" sizes="32x32" type="image/png">
<link rel="apple-touch-icon" href="{asset(path, "img/apple-touch-icon.png")}">
<link rel="preload" href="{asset(path, "fonts/anton-latin-400-normal.woff2")}" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="{asset(path, "fonts/barlow-latin-400-normal.woff2")}" as="font" type="font/woff2" crossorigin>
{head_extra}
<link rel="stylesheet" href="{vasset(path, "css/main.css")}">
<style>:root{{--accent:{ACCENT};--accent-2:{ACCENT_2};--accent-paper:{ACCENT_ON_PAPER}}}</style>
{boot}
{ld}
</head>
<body{f' class="{body_class}"' if body_class else ""}>
<a class="skip-link" href="#main">Skip to content</a>
{demo_bar()}
{intro_markup() if intro_here else ""}
{header_html(path, active)}
<main id="main">
{body}
</main>
{footer_html(path)}
<script src="{vasset(path, "js/main.js")}" defer></script>
{scripts_extra}
</body>
</html>
'''
    out = re.sub(r"\n{2,}", "\n", out)
    dest = os.path.join(ROOT, path)
    os.makedirs(os.path.dirname(dest) or ROOT, exist_ok=True)
    with open(dest, "w", encoding="utf-8") as f:
        f.write(out)
    PAGES.append({"path": path, "url": canonical if path != "404.html" else None, "title": full_title, "noindex": noindex})

def page_hero(here, *, eyebrow, h1, lead, crumbs, ctas=True, mark_icon=None, est_cta=True, compact=False):
    mark = sicon(mark_icon, "page-hero__mark") if mark_icon else ""
    btns = ""
    if ctas:
        second = (f'<a class="btn btn--ghost" href="{href(here, PATH["estimate"])}">{ui("target")} Instant estimate</a>' if (EST_ON and est_cta)
                  else f'<a class="btn btn--ghost" href="tel:{TEL}">{ui("phone")} {PHONE}</a>')
        btns = f'<div class="btn-row intro-fade" style="--d:500ms"><a class="btn btn--primary" href="{href(here, PATH["contact"])}">{CTA} {ui("arrow")}</a>{second}</div>'
    return f'''<section class="page-hero{" page-hero--compact" if compact else ""}">
<div class="page-hero__rows" aria-hidden="true"></div>
<div class="wrap">
<div class="intro-fade">{crumbs_html(here, crumbs)}</div>
<p class="eyebrow intro-fade" style="--d:100ms">{eyebrow}</p>
<h1 class="display" data-split>{h1}</h1>
<p class="lead intro-fade" style="--d:350ms">{lead}</p>
{btns}
</div>
{mark}
</section>'''

def svc_card(here, s, n, heading="h3", target=None):
    t = target or svc_path(s["slug"])
    return (f'<a class="svc-card" href="{href(here, t)}" data-reveal="up"><div class="svc-card__top">{sicon(s["icon"])}<span class="svc-card__no">{n:02d}</span></div>'
            f'<{heading}>{s["name"]}</{heading}><p>{s["short"]}</p><span class="svc-card__go">View service {ui("arrow")}</span></a>')

def faq_html(faqs):
    return '<div class="faq">' + "".join(
        f'<details><summary>{html.escape(q)}<i aria-hidden="true"></i></summary><div class="faq__a"><p>{html.escape(a)}</p></div></details>' for q, a in faqs) + "</div>"

def est_card(here):
    if not EST_ON:
        return ""
    return f'''<div class="aside-card aside-card--sat" data-reveal="up"><p class="mono accent">Instant estimate</p><h2>Price your roof from space</h2><p>Type your address, check the outline on the satellite view and get a ballpark reshingle price in about a minute.</p>
<a class="btn btn--ghost" href="{href(here, PATH["estimate"])}">{ui("target")} Measure my roof</a></div>'''

def aside_html(here, s=None, city=None):
    hours = "<br>".join(hours_text())
    quote = f'''<div class="aside-card aside-card--accent" data-reveal="up"><h2>Get a roof quote</h2><p>Tell us what's going on and we'll set up an inspection and a written, itemized quote.</p>
<a class="btn btn--primary" href="{href(here, PATH["contact"])}">{CTA} {ui("arrow")}</a><a class="btn btn--ghost" href="tel:{TEL}">{ui("phone")} {PHONE}</a></div>'''
    blocks = [quote, est_card(here)]
    if s:
        rel = "".join(f'<li><a href="{href(here, svc_path(r) if not city else svc_city_path(r, city["slug"]))}">{SVC[r]["name"]}{" in " + city["name"] if city else ""}{ui("arrow")}</a></li>' for r in related_of(s))
        if rel:
            blocks.append(f'<div class="aside-card" data-reveal="up"><h2>Related services</h2><ul class="aside-list">{rel}</ul></div>')
        cl = "".join(f'<li><a href="{href(here, svc_city_path(s["slug"], c["slug"]))}"{" aria-current=\"page\"" if city and c["slug"] == city["slug"] else ""}>{s["name"]} in {c["name"]}{ui("arrow")}</a></li>' for c in CITIES)
        blocks.append(f'<div class="aside-card" data-reveal="up"><h2>Service areas</h2><ul class="aside-list">{cl}</ul></div>')
    blocks.append(f'<div class="aside-card" data-reveal="up"><h2>Hours</h2><p class="muted" style="margin:0">{hours}<br>{CFG.get("hours_note","")}</p></div>')
    return '<aside class="aside" aria-label="Roofing help">' + "".join(b for b in blocks if b) + "</aside>"

# ------------------------------------------------------------------ pages
def build_service(s):
    here = svc_path(s["slug"])
    cat_label = dict((c, l) for c, l, _ in CATS)[s["cat"]]
    crumbs = [("Home", PATH["home"]), ("Services", PATH["services"]), (s["name"], None)]
    cities = "".join(f'<a class="chip" href="{href(here, svc_city_path(s["slug"], c["slug"]))}">{ui("pin")}{s["name"]} in {c["name"]}</a>' for c in CITIES)
    who = "property owners and businesses" if s["slug"] == "commercial-roofing" else "homeowners"
    content = f'''{page_hero(here, eyebrow=cat_label, h1=s["h1"], lead=s["lead"], crumbs=crumbs, mark_icon=s["icon"])}
<section class="section section--tight">
<div class="wrap article">
<div class="prose" data-reveal="up">
{expand(s["body"], here)}
<h2>What affects the cost of {s["name"].lower()}</h2>
{COSTS[s["slug"]]}
<h2>{s["name"]} questions</h2>
{faq_html(s["faqs"])}
<h2>Where we offer {s["name"].lower()}</h2>
<p>We provide {s["name"].lower()} for {who} in {city_list_text()}. See what to expect in your area:</p>
<div class="chips">{cities}</div>
</div>
{aside_html(here, s)}
</div>
</section>
{PH.gallery(PH.for_service(PHOTOS, s["slug"]), lambda x: asset(here, x[len("/assets/"):]), f"{s['name']} we have done", kicker="Our work", limit=3, classes=PHOTO_CLASSES)}
{cta_band(here)}'''
    schema = [{
        "@type": "Service", "@id": url_of(here) + "#service", "name": s["name"], "serviceType": s["name"],
        "description": s["desc"], "url": url_of(here), "provider": business_ref(),
        "areaServed": [{"@type": "City", "name": f'{c["name"]}, {CFG["province"]}'} for c in CITIES],
    }]
    page(here, title=s["title"], desc=s["desc"], body=content, active="services", crumbs=crumbs, schema=schema)

def build_service_city(s, c):
    here = svc_city_path(s["slug"], c["slug"])
    crumbs = [("Home", PATH["home"]), ("Services", PATH["services"]), (s["name"], svc_path(s["slug"])), (c["name"], None)]
    labels = re.findall(r"<li><strong>([^<]+)</strong>", s["body"])
    included = "".join(f"<li>{l}</li>" for l in labels)
    audience = "businesses" if s["slug"] == "commercial-roofing" else "homes"
    others = [x for x in CITIES if x["slug"] != c["slug"]]
    other_links = " and ".join(f'<a href="{href(here, svc_city_path(s["slug"], o["slug"]))}">{s["name"].lower()} in {o["name"]}</a>' for o in others)
    rel_links = ", ".join(f'<a href="{href(here, svc_city_path(r, c["slug"]))}">{SVC[r]["name"].lower()}</a>' for r in related_of(s))
    rel_sentence = (f"Property owners planning {s['name'].lower()} in {c['name']} often look at related work too, including {rel_links}. " if rel_links else "")
    est_line = (f' Want a ballpark first? Try the <a href="{href(here, PATH["estimate"])}">instant roof estimate</a> with your {c["name"]} address.' if EST_ON and s["cat"] == "systems" and s["slug"] != "commercial-roofing" else "")
    body = f'''<h2>{s["name"]} for {c["name"]} {audience}</h2>
<p>{c["short"]} {s["cities"][c["slug"]]}</p>
<h2>What's included</h2>
<p>{s["short"]} Depending on your roof, the work can include:</p>
<ul>{included}</ul>
<p>Full details, how the work runs and common questions are on our main <a href="{href(here, svc_path(s["slug"]))}">{s["name"].lower()} page</a>.{est_line}</p>
<h2>Local conditions in {c["name"]}</h2>
<p>{c["cat"][s["cat"]]}</p>
<h2>Questions to ask before you hire</h2>
<p>Whoever you hire for {s["name"].lower()} in {c["name"]}, get clear answers to these before signing:</p>
<ul>{"".join(f"<li>{q}</li>" for q in ASK[s["slug"]])}</ul>
<h2>Permits and approvals</h2>
<p>{c["permits"]}</p>
<h2>More from {html.escape(BIZ)} in {c["name"]}</h2>
<p>{rel_sentence}We also provide {other_links}. See every service we offer on our <a href="{href(here, city_path(c["slug"]))}">{c["name"]} service area page</a>.</p>'''
    content = f'''{page_hero(here, eyebrow=f'{c["name"]}, {CFG["province"]}', h1=f'{s["name"]} in {c["name"]}', lead=f'{s["name"]} for {c["name"]} {audience}, inspected in person, priced in writing and finished with photos of the work.', crumbs=crumbs, mark_icon=s["icon"])}
<section class="section section--tight">
<div class="wrap article">
<div class="prose" data-reveal="up">{expand(body, here)}</div>
{aside_html(here, s, c)}
</div>
</section>
{cta_band(here, title=f"{s['name']} in {c['name']}? Let's talk.")}'''
    desc = f'{s["name"]} in {c["name"]}, {CFG["province"]}: {s["short"][0].lower() + s["short"][1:]}'
    if len(desc) > 158:
        desc = desc[:155].rsplit(" ", 1)[0] + "…"
    schema = [{
        "@type": "Service", "@id": url_of(here) + "#service", "name": f'{s["name"]} in {c["name"]}, {CFG["province"]}',
        "serviceType": s["name"], "url": url_of(here), "provider": business_ref(),
        "areaServed": {"@type": "City", "name": f'{c["name"]}, {CFG["province"]}'},
    }]
    page(here, title=f'{s["name"]} in {c["name"]}, {CFG["province"]}', desc=desc, body=content, active="services", crumbs=crumbs, schema=schema)

def svc_groups(here, heading="h3", city=None, head_tag="h2"):
    groups, n = "", 0
    for i, (cat, label, blurb) in enumerate(CATS, 1):
        cards = ""
        for s in SERVICES:
            if s["cat"] == cat:
                n += 1
                cards += svc_card(here, s, n, heading=heading, target=svc_city_path(s["slug"], city["slug"]) if city else None)
        title = f"{label} in {city['name']}" if city else label
        text = city["cat"][cat] if city else blurb
        groups += (f'<div class="svc-group"><div class="svc-group__head" data-reveal="up"><span class="svc-group__num">0{i}</span><div><{head_tag} class="display h-md">{title}</{head_tag}>'
                   f'<p class="muted" style="margin:6px 0 0">{text}</p></div></div><div class="svc-grid" data-stagger>{cards}</div></div>')
    return groups

def build_services_hub():
    here = PATH["services"]
    crumbs = [("Home", PATH["home"]), ("Services", None)]
    content = f'''{page_hero(here, eyebrow="What we do", h1="Roofing Services", lead=f"{len(SERVICES)} roofing service{'s' if len(SERVICES) != 1 else ''} for homes and businesses in {city_list_text()}, from full replacements to the gutters and skylights around them.", crumbs=crumbs, mark_icon="roof")}
<section class="section section--tight"><div class="wrap">{svc_groups(here)}</div></section>
{cta_band(here)}'''
    items = [{"@type": "ListItem", "position": i, "url": url_of(svc_path(s["slug"])), "name": s["name"]} for i, s in enumerate(SERVICES, 1)]
    names = [x["name"].lower() for x in SERVICES]
    desc = f"Roofing services in {city_list_text()}, {CFG['province']}: " + (", ".join(names[:5]) + " and more." if len(names) > 5 else and_join(names) + ".")
    if len(desc) > 158:
        desc = f"Roofing services in {city_list_text()}, {CFG['province']}: " + ", ".join(names[:3]) + " and more."
    page(here, title="Roofing Services", desc=desc, body=content, active="services", crumbs=crumbs, schema=[{"@type": "ItemList", "itemListElement": items}])

def build_city_hub(c):
    here = city_path(c["slug"])
    crumbs = [("Home", PATH["home"]), ("Service Areas", PATH["areas"]), (c["name"], None)]
    hub = "".join(f"<p>{p}</p>" for p in c["hub"])
    others = " · ".join(f'<a href="{href(here, city_path(o["slug"]))}">{o["name"]}</a>' for o in CITIES if o["slug"] != c["slug"])
    content = f'''{page_hero(here, eyebrow=f'Service area · {c["region"]}', h1=f'Roofing in {c["name"]}, {CFG["province"]}', lead=c["intro"], crumbs=crumbs, mark_icon="home")}
<section class="section section--tight"><div class="wrap">
<div class="hub-intro prose"><div data-reveal="up">{hub}</div><div data-reveal="up"><h2 class="h-sm" style="margin-top:0">Permits in {c["name"]}</h2><p>{c["permits"]}</p><p>Also serving: {others}</p></div></div>
{svc_groups(here, city=c)}
</div></section>
{cta_band(here, title=f"Roofing in {c['name']}? We're close by.")}'''
    page(here, title=c["title"], desc=c["desc"], body=content, active="areas", crumbs=crumbs)

def build_areas_hub():
    here = PATH["areas"]
    crumbs = [("Home", PATH["home"]), ("Service Areas", None)]
    cards = "".join(f'''<a class="area-card" href="{href(here, city_path(c["slug"]))}" data-reveal="up"><span class="area-card__no" aria-hidden="true">0{i}</span><div><h2>{c["name"]}</h2><p>{c["intro"]}</p><span class="svc-card__go">{len(SERVICES)} service{"s" if len(SERVICES) != 1 else ""} in {c["name"]} {ui("arrow")}</span></div></a>''' for i, c in enumerate(CITIES, 1))
    content = f'''{page_hero(here, eyebrow=CFG["region_label"], h1="Service Areas", lead=f"We roof homes and businesses in {city_list_text()}. Each area page covers local housing, weather exposure, permits and every service we offer there.", crumbs=crumbs, mark_icon="home")}
<section class="section section--tight"><div class="wrap"><div class="areas" data-stagger>{cards}</div>
<div class="prose mt-3" data-reveal="up"><p>Just outside these communities? <a href="{href(here, PATH["contact"])}">Contact us</a> with your address and what you need, and we'll let you know whether we can help.</p></div></div></section>
{cta_band(here)}'''
    page(here, title=f"Service Areas: {city_list_text()}", desc=f"Roofing in {city_list_text()}, {CFG['province']}: local housing, weather, permits and every roofing service we offer in your area.", body=content, active="areas", crumbs=crumbs)

def hero_est_form(here, compact=False):
    """Address box that hands off to the instant estimate (works without JavaScript: plain GET form)."""
    if not EST_ON:
        return ""
    return f'''<form class="addr" action="{href(here, PATH["estimate"])}" method="get" role="search" aria-label="Instant roof estimate">
<label class="addr__label" for="hero-address">Your property address</label>
<div class="addr__row">{ui("pin", "addr__pin")}<input class="addr__input" id="hero-address" name="address" type="text" autocomplete="street-address" placeholder="e.g. 123 Main St, Franklin" required>
<button class="btn btn--primary addr__go" type="submit"><span>Measure my roof</span>{ui("arrow")}</button></div>
</form>'''

def sat_teaser_svg():
    """Illustration for the home estimate section: a top-down hip roof being traced and measured."""
    return '''<svg class="sat" viewBox="0 0 520 420" role="img" aria-label="Illustration of a roof outline traced on a satellite view, with measurements">
<defs><pattern id="sat-grass" width="8" height="8" patternUnits="userSpaceOnUse"><rect width="8" height="8" fill="#16201a"/><circle cx="2" cy="3" r="1" fill="#1d2b22"/><circle cx="6" cy="6" r="1" fill="#1a251e"/></pattern>
<linearGradient id="sat-scan" x1="0" x2="1"><stop offset="0" stop-color="var(--accent)" stop-opacity="0"/><stop offset="1" stop-color="var(--accent)" stop-opacity=".35"/></linearGradient>
<clipPath id="sat-clip"><rect width="520" height="420" rx="10"/></clipPath></defs>
<g clip-path="url(#sat-clip)">
<rect width="520" height="420" fill="url(#sat-grass)"/>
<path d="M0 330H520V380H0Z" fill="#2a2c30"/><path d="M0 355H520" stroke="#4a4c50" stroke-dasharray="18 14" stroke-width="2"/>
<path d="M300 330V250H350V330Z" fill="#33363b"/>
<circle cx="90" cy="110" r="46" fill="#1f3326"/><circle cx="120" cy="80" r="30" fill="#24402c"/><circle cx="455" cy="95" r="38" fill="#1f3326"/>
<g class="sat__house"><path d="M150 90H420V250H150Z" fill="#3a3d43"/><path d="M150 90L215 170H355L420 90M150 250L215 170M420 250L355 170" stroke="#55585f" stroke-width="2" fill="none"/>
<path d="M150 90L215 170L150 250Z" fill="#33363c"/><path d="M420 90L355 170L420 250Z" fill="#41444a"/><path d="M150 250H420L355 170H215Z" fill="#2e3136"/></g>
<rect class="sat__scan" x="-180" y="0" width="180" height="420" fill="url(#sat-scan)"/>
<path class="sat__trace" pathLength="1" d="M146 86H424V254H146Z" fill="none" stroke="var(--accent)" stroke-width="3"/>
<g class="sat__pts" fill="#0b0c0e" stroke="var(--accent)" stroke-width="3"><circle cx="146" cy="86" r="6"/><circle cx="424" cy="86" r="6"/><circle cx="424" cy="254" r="6"/><circle cx="146" cy="254" r="6"/></g>
<g class="sat__dims" font-family="Barlow Condensed, sans-serif" font-weight="600" font-size="15" letter-spacing="2" fill="#f2efe9">
<path d="M146 66H424M146 60V72M424 60V72" stroke="#f2efe9" stroke-width="1.5"/><text x="285" y="56" text-anchor="middle">48 FT</text>
<path d="M444 86V254M438 86H450M438 254H450" stroke="#f2efe9" stroke-width="1.5"/><text x="458" y="175">30 FT</text></g>
<g class="sat__chip"><rect x="20" y="20" width="168" height="34" rx="4" fill="#0b0c0e" opacity=".85"/><text x="34" y="43" font-family="Barlow Condensed, sans-serif" font-weight="600" font-size="15" letter-spacing="2" fill="var(--accent)">EXAMPLE · NOT A QUOTE</text></g>
</g></svg>'''

def build_home():
    here = PATH["home"]
    p = P.home(CFG, CITIES, SERVICES, ALL_OFFERED)
    areas = "".join(f'<a href="{href(here, city_path(c["slug"]))}">{c["name"]}</a>' for c in CITIES)
    marquee_items = "".join(f'<span class="marquee__item">{s["name"]}</span>{ui("star", "marquee__star")}' for s in SERVICES)
    layer_steps = "".join(f'<li class="sequence__step{" is-active" if i == 0 else ""}"><h3><span>0{i+1}</span>{t}</h3><p>{d}</p></li>' for i, (t, d) in enumerate(p["layers"]))
    feats = "".join(f'<div class="feature" data-reveal="up"><p class="feature__no" aria-hidden="true">0{i+1}</p><h3>{t}</h3><p>{d}</p></div>' for i, (t, d) in enumerate(p["features"]))
    procs = "".join(f'<li class="proc" data-reveal="up"><span class="proc__no" aria-hidden="true">0{i+1}</span><h3>{t}</h3><p>{d}</p></li>' for i, (t, d) in enumerate(p["process"] if EST_ON else p["process"][1:]))
    area_cards = "".join(f'''<a class="area-card" href="{href(here, city_path(c["slug"]))}" data-reveal="up"><span class="area-card__no" aria-hidden="true">0{i}</span><div><h3>{c["name"]}</h3><p>{c["short"]}</p><span class="svc-card__go">Roofing in {c["name"]} {ui("arrow")}</span></div></a>''' for i, c in enumerate(CITIES, 1))
    foot = "".join(f'<div data-reveal="up"><h3>{t}</h3><p>{d}</p></div>' for t, d in p["statement_points"])
    tags = "".join(f'<li>{ui("check")}{t}</li>' for t in p["tags"])
    video = ""
    if CFG.get("hero_video", True):
        video = (f'<video class="hero__video" muted loop playsinline preload="none" aria-hidden="true" tabindex="-1" '
                 f'data-src-sm="{asset(here, "video/hero-540.mp4")}" data-src-lg="{asset(here, "video/hero-1600.mp4")}"></video>')
    if EST_ON:
        hero_side = f'''<div class="hero__est intro-fade" style="--d:450ms">
<div class="hero__est-head"><span class="hero__live"><i></i>Instant estimate</span><span class="mono muted">Satellite measured</span></div>
<p class="hero__est-title">Price your roof<br><span class="accent">from space.</span></p>
<p class="hero__est-text">Type your address, check the outline on the satellite view and see a ballpark reshingle price in about a minute.</p>
{hero_est_form(here)}
<ul class="hero__est-steps"><li><b>01</b>Find</li><li><b>02</b>Trace</li><li><b>03</b>Price</li></ul>
</div>'''
        est_section = f'''<section class="section est-teaser" aria-labelledby="est-title">
<div class="wrap est-teaser__grid">
<div><p class="eyebrow">Instant roof estimate</p><h2 class="display h-xl" id="est-title" data-reveal="rise">Measure it<br><span class="outline">from space.</span></h2>
<p class="lead mt-1" data-reveal="up">No waiting for a callback to find out if a new roof is in your budget. Our estimate tool finds your house on satellite imagery, traces the roof and works out a ballpark price for a full reshingle.</p>
<ol class="est-teaser__steps" data-stagger><li data-reveal="up"><b>01</b><span><strong>Enter your address.</strong> We find your home on a satellite map.</span></li>
<li data-reveal="up"><b>02</b><span><strong>Check the outline.</strong> The building outline is drawn for you; drag the corners if it needs a tweak.</span></li>
<li data-reveal="up"><b>03</b><span><strong>Pick the pitch.</strong> Tell us how steep the roof is and how many stories, and the price range updates instantly.</span></li></ol>
<div class="btn-row mt-2" data-reveal="up"><a class="btn btn--primary" href="{href(here, PATH["estimate"])}">{ui("target")} Get my instant estimate</a></div>
<p class="fine mt-1" data-reveal="up">A ballpark, not a quote. Your written price is confirmed after an on-site inspection.</p></div>
<div class="est-teaser__art" data-reveal="scale">{sat_teaser_svg()}</div>
</div></section>'''
    else:
        hero_side = f'<div class="hero__est hero__est--plain intro-fade" style="--d:450ms"><p class="hero__est-title">Leaking now?</p><p class="hero__est-text">Call and we\'ll get it looked at.</p><a class="btn btn--primary" href="tel:{TEL}">{ui("phone")} {PHONE}</a></div>'
        est_section = ""
    storm_ok = "storm-damage-repair" in SVC
    storm = f'''<section class="storm" aria-labelledby="storm-title">
<div class="storm__rain" aria-hidden="true"></div><div class="storm__flash" aria-hidden="true"></div>
<div class="wrap storm__grid">
<div><p class="eyebrow">After the storm</p><h2 class="display h-xl" id="storm-title" data-reveal="rise">Wind took<br>your shingles?</h2></div>
<div data-reveal="up"><p class="lead">Missing shingles, lifted ridge caps and branches through the roof. We inspect it, photograph the damage for your insurer and get it watertight.</p>
<div class="btn-row mt-2"><a class="btn btn--primary" href="tel:{TEL}">{ui("phone")} Call {PHONE}</a><a class="btn btn--ghost" href="{href(here, svc_path("storm-damage-repair"))}">Storm damage repair {ui("arrow")}</a></div></div>
</div></section>''' if storm_ok else ""
    content = f'''<section class="hero" aria-labelledby="hero-title">
<div class="hero__media" aria-hidden="true">
<img class="hero__poster" src="{asset(here, "video/poster.webp")}" srcset="{asset(here, "video/poster-800.webp")} 800w, {asset(here, "video/poster.webp")} 1600w" sizes="100vw" width="1600" height="900" alt="" fetchpriority="high" decoding="async">
{video}<div class="hero__shade"></div><div class="hero__lines"></div>
</div>
<div class="wrap hero__grid">
<div class="hero__copy">
<h1 id="hero-title"><span class="eyebrow intro-fade" style="--d:0ms">{p["eyebrow"]}</span><span class="display hero__title" data-split style="--base-delay:150ms"><span class="line">Roofs built</span> <span class="line">for the</span> <span class="line accent">storm.</span></span></h1>
<p class="lead intro-fade" style="--d:650ms">{p["lead"]}</p>
<div class="btn-row intro-fade" style="--d:800ms"><a class="btn btn--primary" href="{href(here, PATH["contact"])}">{CTA} {ui("arrow")}</a><a class="btn btn--ghost" href="tel:{TEL}">{ui("phone")} {PHONE}</a></div>
<p class="hero__areas intro-fade" style="--d:950ms"><span>Serving</span>{areas}</p>
</div>
{hero_side}
</div>
<ul class="hero__tags intro-fade" style="--d:1100ms">{tags}</ul>
<div class="scroll-cue" aria-hidden="true"><span>Scroll</span><i></i></div>
</section>
<div class="marquee" aria-hidden="true"><div class="marquee__track"><div class="marquee__group">{marquee_items}</div><div class="marquee__group">{marquee_items}</div></div></div>
<section class="section statement" aria-labelledby="statement-title">
<div class="wrap">
<h2 class="eyebrow" id="statement-title">{p["statement_eyebrow"]}</h2>
<p class="fill-text" data-fill>{p["statement"]}</p>
<div class="statement__foot" data-stagger>{foot}</div>
</div>
</section>
<section class="sequence" aria-labelledby="seq-title">
<div class="sequence__sticky"><div class="wrap sequence__grid">
<div><p class="eyebrow">Anatomy of a roof</p><h2 class="display h-lg" id="seq-title">Five layers.<br>Zero shortcuts.</h2>
<div class="sequence__steps"><span class="sequence__rail" aria-hidden="true"></span><ol>{layer_steps}</ol></div></div>
<div class="sequence__art"><span class="sequence__pct" aria-hidden="true">00%</span>{roof_layers_svg("Roof cross-section built up layer by layer: deck, ice and water shield, underlayment, shingles and ridge vent")}</div>
</div></div>
</section>
<section class="section" aria-labelledby="services-title">
<div class="wrap">
<div class="sec-head"><div><p class="eyebrow">What we do</p><h2 class="display h-xl" id="services-title" data-reveal="rise">Every roof.<br><span class="outline">Every layer.</span></h2></div><p class="lead" data-reveal="up">{p["services_lead"]}</p></div>
{svc_groups(here, heading="h4", head_tag="h3")}
<p class="mt-3 center" data-reveal="up"><a class="btn btn--ghost" href="{href(here, PATH["services"])}">Browse all services {ui("arrow")}</a></p>
</div>
</section>
{est_section}
{storm}
{PH.gallery(PHOTOS, lambda x: asset(here, x[len("/assets/"):]), f"Recent roofs from {BIZ}", f"Real projects from around {CFG['region_label']}.", classes=PHOTO_CLASSES)}
<section class="section section--tight" aria-labelledby="proc-title">
<div class="wrap">
<div class="sec-head"><div><p class="eyebrow">How it works</p><h2 class="display h-lg" id="proc-title" data-reveal="rise">From first look<br>to last nail.</h2></div></div>
<ol class="procs" data-stagger>{procs}</ol>
</div>
</section>
<section class="section" aria-labelledby="why-title">
<div class="wrap">
<div class="sec-head"><div><p class="eyebrow">How we work</p><h2 class="display h-xl" id="why-title" data-reveal="rise">No guesswork.<br><span class="outline">No runaround.</span></h2></div><p class="lead" data-reveal="up">{p["why_lead"]}</p></div>
<div class="features" data-stagger>{feats}</div>
</div>
</section>
<section class="section section--tight" aria-labelledby="areas-title" style="border-top:1px solid var(--line)">
<div class="wrap">
<div class="sec-head"><div><p class="eyebrow">Where we work</p><h2 class="display h-xl" id="areas-title" data-reveal="rise">Local to<br><span class="outline">{html.escape(CFG["region_label"])}.</span></h2></div><p class="lead" data-reveal="up">Every area page covers local housing, weather exposure and permits, along with every service we offer there.</p></div>
<div class="areas" data-stagger>{area_cards}</div>
</div>
</section>
<section class="section" aria-labelledby="faq-title">
<div class="wrap article" style="grid-template-columns:minmax(0,.8fr) minmax(0,1.2fr)">
<div><p class="eyebrow">Questions</p><h2 class="display h-lg" id="faq-title" data-reveal="rise">Straight<br>answers.</h2><p class="lead mt-1" data-reveal="up">What homeowners ask us most, before they commit to anything.</p><p class="mt-2"><a class="link-arrow" href="{href(here, PATH["faq"])}">All FAQs {ui("arrow")}</a></p></div>
<div data-reveal="up">{faq_html(p["faqs"] if EST_ON else p["faqs"][1:])}</div>
</div>
</section>
{cta_band(here)}'''
    website = {"@type": "WebSite", "@id": DOMAIN + "/#website", "url": DOMAIN + "/", "name": BIZ, "publisher": {"@id": DOMAIN + "/#business"}, "inLanguage": "en-CA"}
    head = f'<link rel="preload" as="image" href="{asset(here, "video/poster.webp")}" imagesrcset="{asset(here, "video/poster-800.webp")} 800w, {asset(here, "video/poster.webp")} 1600w" imagesizes="100vw" fetchpriority="high">'
    page(here, title=f"{BIZ} | Roofing Company, {CFG['region_label']}", desc=p["desc"], body=content, active="home", schema=[business_entity(), website], head_extra=head, body_class="home")

def build_estimate():
    if not EST_ON:
        return
    here = PATH["estimate"]
    crumbs = [("Home", PATH["home"]), ("Instant Roof Estimate", None)]
    e = EST
    pitches = "".join(f'''<label class="opt opt--pitch"><input type="radio" name="pitch" value="{x["id"]}"{" checked" if x["id"] == e.get("default_pitch", "standard") else ""}>
<span class="opt__box"><svg viewBox="0 0 60 34" aria-hidden="true" focusable="false"><path d="M4 30L30 {30 - round(min(x["rise"], 14) * 2.1)}L56 30" /></svg><b>{html.escape(x["label"])}</b><small>{html.escape(x["hint"])}</small></span></label>''' for x in e["pitches"])
    storeys = "".join(f'<label class="opt"><input type="radio" name="storeys" value="{x["id"]}"{" checked" if i == 0 else ""}><span class="opt__box"><b>{html.escape(x["label"])}</b></span></label>' for i, x in enumerate(e["storeys"]))
    layers = ('<label class="opt"><input type="radio" name="layers" value="1" checked><span class="opt__box"><b>1 layer</b></span></label>'
              '<label class="opt"><input type="radio" name="layers" value="2"><span class="opt__box"><b>2 layers</b></span></label>'
              '<label class="opt"><input type="radio" name="layers" value="unsure"><span class="opt__box"><b>Not sure</b></span></label>')
    def fld(id_, label, inp, req=True, full=False):
        r = ' <span class="req" aria-hidden="true">*</span>' if req else ' <span class="muted">(optional)</span>'
        return f'<div class="field{" full" if full else ""}"><label for="{id_}">{label}{r}</label>{inp}<span class="field__error" id="{id_}-error" aria-live="polite"></span></div>'
    hidden = "".join(f'<input type="hidden" name="{n}" id="lead-{n.replace(" ", "-").lower()}" value="">' for n in ["Property address", "Coordinates", "Measured footprint (sq ft)", "Roof surface (sq ft)", "Squares incl. waste", "Pitch", "Stories", "Old layers", "Measurement source", "Estimate shown"])
    sample = '<p class="est-sample" role="note">Demo pricing: the price per square on this demo site is a sample, set by each roofing company.</p>' if CFG.get("demo_mode") else ""
    cfg_js = {k: e[k] for k in ("price_per_square", "range_pct", "waste_pct", "extra_layer_per_square", "overhang_ft", "minimum_job", "round_to", "currency", "pitches", "storeys", "map_center", "search_bias", "google_solar_api_key")}
    cfg_js["contact_url"] = href(here, PATH["contact"])
    tool = f'''<section class="est" id="estimator" aria-labelledby="est-tool-title">
<div class="wrap">
<h2 class="visually-hidden" id="est-tool-title">Roof estimate tool</h2>
<noscript><div class="est-noscript"><p><strong>The instant estimate needs JavaScript.</strong> You can still <a href="{href(here, PATH["contact"])}">request a quote</a> or call <a href="tel:{TEL}">{PHONE}</a>.</p></div></noscript>
<div class="est__grid" data-estimator>
<div class="est__panel">
<form class="est-search" id="est-search" role="search" autocomplete="off" novalidate>
<p class="est__step"><b>01</b> Find your roof</p>
<label class="field-label" for="est-address">Property address</label>
<div class="est-search__row combo">
<input id="est-address" name="address" type="text" placeholder="e.g. 123 Main St, Franklin" autocomplete="street-address" role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="est-suggest" aria-describedby="est-status">
<button class="btn btn--primary" type="submit">{ui("target")}<span>Find</span></button>
<ul class="combo__list" id="est-suggest" role="listbox" aria-label="Address suggestions" hidden></ul>
</div>
<p class="est-status" id="est-status" role="status" aria-live="polite">Start with your address. Nothing is sent to us until you choose to.</p>
</form>
<div class="est-details" id="est-details" hidden>
<p class="est__step"><b>02</b> Tell us about the roof</p>
<fieldset class="opts opts--pitch"><legend>How steep is it?</legend>{pitches}</fieldset>
<div class="est-two">
<fieldset class="opts"><legend>Stories</legend>{storeys}</fieldset>
<fieldset class="opts"><legend>Old shingle layers</legend>{layers}</fieldset>
</div>
<details class="est-manual"><summary>Outline wrong, or no map? Enter the size instead</summary>
<label class="field-label" for="est-manual-area">House footprint, including attached garage (sq ft)</label>
<div class="est-manual__row"><input id="est-manual-area" type="number" min="200" max="20000" step="10" inputmode="numeric" placeholder="e.g. 1600"><button class="btn btn--ghost btn--sm" type="button" id="est-manual-go">Use this size</button></div>
<p class="fine">Use the ground-floor area under the roof, not total living space. A two-story 2,400 sq ft home usually has about a 1,200 sq ft footprint.</p>
</details>
</div>
<div class="est-result" id="est-result" hidden>
<p class="est__step"><b>03</b> Your ballpark</p>
<p class="est-result__label">Estimated full reshingle</p>
<p class="est-result__price" aria-live="polite"><span id="est-low">$0</span><i>–</i><span id="est-high">$0</span></p>
<dl class="est-result__facts"><div><dt>Roof surface</dt><dd id="est-area">—</dd></div><div><dt>Squares (incl. waste)</dt><dd id="est-squares">—</dd></div><div><dt>Measured by</dt><dd id="est-source">—</dd></div></dl>
<p class="fine">Includes tear-off, ice and water protection at the eaves, synthetic underlayment, architectural shingles, ridge vent and disposal. Rotted decking, chimneys, skylights and extra work are confirmed after an inspection.</p>
{sample}
<button class="btn btn--primary est-result__go" type="button" id="est-lead-open">Lock in an inspection {ui("arrow")}</button>
</div>
<form class="form est-lead" id="est-lead" action="{html.escape(CFG["form_endpoint"])}" method="POST" data-validate novalidate hidden>
<p class="est__step"><b>04</b> Send it to us</p>
<p class="form__status" role="alert"></p>
<input type="hidden" name="_subject" value="New instant roof estimate — {html.escape(BIZ)} website">
<input type="hidden" name="_next" value="{url_of(PATH["thanks"])}">
<input type="hidden" name="_template" value="table">
{hidden}
<div class="hp" aria-hidden="true"><label for="hp-est">Leave this field empty</label><input class="hp-input" id="hp-est" type="text" name="_honey" tabindex="-1" autocomplete="off"></div>
{fld("lead-name", "Full name", '<input id="lead-name" name="name" type="text" autocomplete="name" required data-label="full name" aria-describedby="lead-name-error">')}
{fld("lead-phone", "Phone", '<input id="lead-phone" name="phone" type="tel" autocomplete="tel" required data-label="phone number" aria-describedby="lead-phone-error">')}
{fld("lead-email", "Email", '<input id="lead-email" name="email" type="email" autocomplete="email" required data-label="email address" aria-describedby="lead-email-error">', full=True)}
{fld("lead-notes", "Anything we should know?", '<textarea id="lead-notes" name="message" rows="3" aria-describedby="lead-notes-error" placeholder="Leaks, skylights, timing, how you heard about us…"></textarea>', req=False, full=True)}
<p class="form__privacy">We use your details only to follow up on this estimate and arrange an inspection. See our <a href="{href(here, PATH["privacy"])}">Privacy Policy</a>.</p>
<div class="full"><button class="btn btn--primary" type="submit">Send my estimate {ui("arrow")}</button></div>
</form>
</div>
<div class="est__map">
<div class="est-map" id="est-map" role="region" aria-label="Satellite map of your roof. Drag the corner handles to adjust the outline."></div>
<div class="est-map__idle" id="est-idle" aria-hidden="true"><div class="est-map__radar"><i></i></div><p>Satellite view appears here</p></div>
<div class="est-map__scan" id="est-scan" aria-hidden="true"><i></i><p>Measuring roof</p></div>
<div class="est-map__tools" id="est-tools" hidden>
<button class="tool" type="button" id="est-redraw">{SVC_ICON_BTN("redraw")}Redraw outline</button>
<button class="tool" type="button" id="est-reset">{SVC_ICON_BTN("reset")}Reset</button>
</div>
<div class="est-map__readout" id="est-readout" hidden><span><b id="est-fp">—</b> sq ft footprint</span><span><b id="est-pts">0</b> corners</span></div>
<p class="est-map__hint" id="est-hint" hidden></p>
</div>
</div>
</div>
<script type="application/json" id="est-config">{json.dumps(cfg_js).replace("</", "<\\/")}</script>
</section>'''
    explain = f'''<section class="section section--tight"><div class="wrap article">
<div class="prose" data-reveal="up">
<h2>How the instant estimate works</h2>
<p>When you enter your address, the tool finds your property on a satellite map and looks up the outline of the building from OpenStreetMap's building data. That outline is the footprint of the house. We add the roof overhang around the edges, then use the pitch you choose to convert the flat footprint into the actual sloped surface of the roof, because a steep roof has much more area than the ground it covers.</p>
<p>Roofers price by the <strong>square</strong>, which is 100 square feet of roof surface. The tool adds a waste allowance for cuts at hips, valleys, rakes and starter courses, then multiplies by {html.escape(BIZ)}'s price per square for a standard asphalt shingle reshingle, with adjustments for steep roofs, taller homes and extra layers of old shingles.</p>
<h2>What the price includes</h2>
<ul>
<li><strong>Tear-off</strong> of one layer of existing shingles and disposal.</li>
<li><strong>Ice and water protection</strong> at the eaves and in the valleys.</li>
<li><strong>Synthetic underlayment</strong> and drip edge.</li>
<li><strong>Architectural asphalt shingles</strong>, starter strips and ridge caps.</li>
<li><strong>Ridge vent</strong> and new pipe flashings.</li>
</ul>
<h2>Why the final price can differ</h2>
<p>Satellite images can be a few years old, trees can hide parts of a roof and building outlines aren't always exact. Some costs also can't be seen from above: soft or rotted decking, extra layers, chimney and wall flashing, skylights, ventilation upgrades and difficult access. That's why the estimate is a range, and why your actual price is confirmed in a written quote after we inspect the roof in person. For metal, flat or commercial roofs, <a href="{href(here, PATH["contact"])}">contact us</a> for a quote.</p>
<h2>Instant estimate questions</h2>
{faq_html([
("Is the instant estimate a quote?", "No. It's a ballpark based on satellite measurements and the details you choose. Your actual price comes in a written quote after an on-site inspection."),
("What if the outline on the map is wrong?", "Drag the corner handles to match your roof, tap Redraw outline to trace it yourself, or enter your home's footprint in square feet instead."),
("Do you see my address when I use the tool?", "Not unless you send us the estimate. The address is used to find your roof on the map, and nothing is sent to us until you submit the form."),
])}
</div>
{aside_html(here)}
</div></section>'''
    content = f'''{page_hero(here, eyebrow="Instant roof estimate", h1="Instant Roof Estimate", lead="Find your house on the satellite map, check the roof outline, pick the pitch and see a ballpark price for a full reshingle.", crumbs=crumbs, ctas=False, mark_icon="sat", compact=True)}
{tool}
{explain}
{cta_band(here, title="Ready for the real number?", text="Book an inspection and we'll confirm the price in a written, itemized quote.")}'''
    head = f'<link rel="stylesheet" href="{vasset(here, "vendor/leaflet/leaflet.css")}">'
    scripts = f'<script src="{vasset(here, "vendor/leaflet/leaflet.js")}" defer></script>\n<script src="{vasset(here, "js/estimate.js")}" defer></script>'
    schema = [{"@type": "WebApplication", "name": f"{BIZ} Instant Roof Estimate", "url": url_of(here), "applicationCategory": "UtilitiesApplication", "operatingSystem": "Any",
               "offers": {"@type": "Offer", "price": "0", "priceCurrency": e.get("currency", "USD")}, "provider": business_ref()}]
    page(here, title="Instant Roof Estimate: Satellite Roof Price", desc=f"Get a ballpark roof replacement price in a minute: enter your address, check your roof on satellite imagery and pick the pitch.",
         body=content, active="estimate", crumbs=crumbs, schema=schema, head_extra=head, scripts_extra=scripts, body_class="page-estimate")

def SVC_ICON_BTN(kind):
    d = {"redraw": '<path d="M4 20l4-1L19 8l-3-3L5 16z"/><path d="M14 7l3 3"/>', "reset": '<path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 4v5h5"/>'}[kind]
    return f'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">{d}</svg>'

def build_simple(key, *, title, desc, eyebrow, h1, lead, inner, mark="home", active=None, noindex=False, aside=True, schema=None, cta=True, hero_ctas=True):
    here = PATH[key]
    crumbs = [("Home", PATH["home"]), (h1, None)]
    side = aside_html(here) if aside else ""
    grid = "article" if aside else ""
    content = f'''{page_hero(here, eyebrow=eyebrow, h1=h1, lead=lead, crumbs=crumbs, mark_icon=mark, ctas=hero_ctas)}
<section class="section section--tight"><div class="wrap {grid}"><div class="prose" data-reveal="up">{expand(inner(here), here)}</div>{side}</div></section>
{cta_band(here) if cta else ""}'''
    page(here, title=title, desc=desc, body=content, active=active, crumbs=crumbs, noindex=noindex, schema=schema)

def build_contact():
    here = PATH["contact"]
    crumbs = [("Home", PATH["home"]), ("Contact", None)]
    svc_opts = "".join(f'<option>{s["name"]}</option>' for s in SERVICES) + "<option>Not sure / something else</option>"
    city_opts = "".join(f'<option>{c["name"]}</option>' for c in CITIES) + "<option>Another area</option>"
    def fld(id_, label, inp, req=True, full=False, hint=""):
        r = ' <span class="req" aria-hidden="true">*</span>' if req else ' <span class="muted">(optional)</span>'
        h = f'<span class="field__hint" id="{id_}-hint">{hint}</span>' if hint else ""
        return f'<div class="field{" full" if full else ""}"><label for="{id_}">{label}{r}</label>{inp}{h}<span class="field__error" id="{id_}-error" aria-live="polite"></span></div>'
    form = f'''<form class="form" action="{html.escape(CFG["form_endpoint"])}" method="POST" data-validate novalidate>
<p class="form__status" role="alert"></p>
<input type="hidden" name="_subject" value="New roof quote request — {html.escape(BIZ)} website">
<input type="hidden" name="_next" value="{url_of(PATH["thanks"])}">
<input type="hidden" name="_template" value="table">
<div class="hp" aria-hidden="true"><label for="hp-field">Leave this field empty</label><input class="hp-input" id="hp-field" type="text" name="_honey" tabindex="-1" autocomplete="off"></div>
{fld("name", "Full name", '<input id="name" name="name" type="text" autocomplete="name" required data-label="full name" aria-describedby="name-error">')}
{fld("phone", "Phone", '<input id="phone" name="phone" type="tel" autocomplete="tel" required data-label="phone number" aria-describedby="phone-error">')}
{fld("email", "Email", '<input id="email" name="email" type="email" autocomplete="email" required data-label="email address" aria-describedby="email-error">')}
{fld("city", "Property location", f'<select id="city" name="city" required data-label="property location" aria-describedby="city-error"><option value="">Select an area</option>{city_opts}</select>')}
{fld("service", "What do you need?", f'<select id="service" name="service" required data-label="type of work" aria-describedby="service-error"><option value="">Select a service</option>{svc_opts}</select>', full=True)}
{fld("message", "Tell us about your roof", '<textarea id="message" name="message" required data-label="roof details" aria-describedby="message-hint message-error"></textarea>', full=True, hint="What's happening (leak, age, storm damage), the type of roof, and roughly when you'd like the work done.")}
<p class="form__privacy">We use the information you submit only to respond to your request and prepare a quote. See our <a href="{href(here, PATH["privacy"])}">Privacy Policy</a>.</p>
<div class="full"><button class="btn btn--primary" type="submit">Send request {ui("arrow")}</button></div>
</form>'''
    hours = "<br>".join(hours_text())
    est_tip = (f'<div class="aside-card aside-card--sat mt-2"><p class="mono accent">Want a number first?</p><h2>Instant estimate</h2><p>See a ballpark reshingle price for your address before you send anything.</p><a class="btn btn--ghost" href="{href(here, PATH["estimate"])}">{ui("target")} Measure my roof</a></div>' if EST_ON else "")
    content = f'''{page_hero(here, eyebrow="Contact", h1="Get a Roof Quote", lead="Tell us what's going on with your roof. We'll follow up to set up an inspection and a written, itemized quote.", crumbs=crumbs, ctas=False, mark_icon="roof")}
<section class="section section--tight"><div class="wrap contact-grid">
<div class="contact-panel" data-reveal="up"><h2 class="display h-md" style="margin-bottom:24px">Your roof</h2>{form}</div>
<div data-reveal="up"><ul class="info-list">
<li><span>Call</span><a href="tel:{TEL}">{PHONE}</a></li>
<li><span>Email</span><a class="info-list__email" href="mailto:{CFG["email"]}">{CFG["email"]}</a></li>
<li><span>Hours</span><p style="margin:0">{hours}<br><span class="muted">{CFG.get("hours_note","")}</span></p></li>
<li><span>Service area</span><p style="margin:0">{" · ".join(f'<a class="info-list__link" href="{href(here, city_path(c["slug"]))}">{c["name"]}</a>' for c in CITIES)}</p></li>
</ul>
<div class="prose mt-2"><h2 class="h-sm">What happens next</h2><ol><li><strong>We review your request</strong> and follow up by phone or email.</li><li><strong>Inspection.</strong> We check the roof, flashing, ventilation and attic, and take photos.</li><li><strong>Written quote.</strong> You receive an itemized quote to review on your own time.</li></ol></div>
{est_tip}
</div>
</div></section>'''
    schema = [{"@type": "ContactPage", "url": url_of(here), "name": f"Contact {BIZ}", "about": {"@id": DOMAIN + "/#business"}}]
    page(here, title="Contact & Roof Quote", desc=f"Request a roof quote from {BIZ}. Call {PHONE} or send details about your roof replacement, repair, storm damage or gutter project.", body=content, active="contact", crumbs=crumbs, schema=schema)

def build_404():
    here = "404.html"
    global href, asset
    rel_href, rel_asset = href, asset
    def abs_href(_from, to):
        if to == "index.html": return BASE
        if to.endswith("index.html"): return BASE + to[:-len("index.html")]
        return BASE + to
    href = abs_href
    asset = lambda _f, a: BASE + "assets/" + a  # vasset() builds on asset(), so the 404 gets root-based versioned URLs
    links = "".join(f'<li><a href="{abs_href(None, svc_path(s["slug"]))}">{s["name"]}</a></li>' for s in SERVICES[:10])
    content = f'''<section class="notfound"><div class="wrap">
<p class="notfound__code" aria-hidden="true">404</p>
<h1 class="display h-lg mt-1">This page blew off the roof.</h1>
<p class="lead mt-1">The page you're looking for may have moved or no longer exists. Try one of these instead:</p>
<div class="btn-row mt-2"><a class="btn btn--primary" href="{BASE}">Back to home {ui("arrow")}</a><a class="btn btn--ghost" href="{abs_href(None, PATH["services"])}">All services</a><a class="btn btn--ghost" href="{abs_href(None, PATH["contact"])}">Contact us</a></div>
<div class="prose mt-3"><h2 class="h-sm">Popular services</h2><ul style="columns:2;max-width:640px">{links}</ul></div>
</div></section>'''
    page(here, title="Page Not Found", desc="The page you're looking for couldn't be found.", body=content, noindex=True)
    href, asset = rel_href, rel_asset

def write_sitemap_robots():
    urls = [p for p in PAGES if p["url"] and not p["noindex"]]
    xml = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    xml += [f"  <url><loc>{html.escape(p['url'])}</loc></url>" for p in urls]
    xml.append("</urlset>")
    open(os.path.join(ROOT, "sitemap.xml"), "w", encoding="utf-8").write("\n".join(xml) + "\n")
    open(os.path.join(ROOT, "robots.txt"), "w", encoding="utf-8").write(f"User-agent: *\nAllow: /\nDisallow: /thank-you/\n\nSitemap: {DOMAIN}/sitemap.xml\n")
    return len(urls)

def write_cname():
    host = re.sub(r"^https?://", "", DOMAIN).strip("/")
    cname = os.path.join(ROOT, "CNAME")
    if "example.com" in host or host.endswith(".pages.dev"):
        if os.path.exists(cname): os.remove(cname)
        return None
    open(cname, "w").write(host + "\n")
    return host

def main():
    import shutil
    for d in ("services", "service-areas", "roof-estimate"):
        shutil.rmtree(os.path.join(ROOT, d), ignore_errors=True)
    prep_logo()
    PH.process(PHOTOS, ROOT)
    PH.ensure_css(os.path.join(ROOT, "assets", "css", "main.css"))
    try:
        import runpy
        runpy.run_path(os.path.join(HERE, "make_images.py"), run_name="__main__")
    except ImportError as e:
        print(f"WARNING: brand images not regenerated ({e}). pip install pillow fonttools brotli")
    build_home()
    build_estimate()
    build_services_hub()
    for s in SERVICES:
        build_service(s)
        for c in CITIES:
            build_service_city(s, c)
    build_areas_hub()
    for c in CITIES:
        build_city_hub(c)
    for key, spec in P.simple_pages(CFG, CITIES, SERVICES, city_list_text(), ALL_OFFERED).items():
        build_simple(key, **spec)
    build_contact()
    build_404()
    n = write_sitemap_robots()
    host = write_cname()
    json.dump([{"path": p["path"], "url": p["url"], "title": p["title"], "indexable": bool(p["url"]) and not p["noindex"]} for p in PAGES],
              open(os.path.join(HERE, "page-inventory.json"), "w"), indent=1)
    print(f"Built {len(PAGES)} pages, {n} URLs in sitemap.xml. CNAME: {host or 'not written (demo or example domain)'}")
    if CFG.get("demo_mode"):
        print("WARNING: demo_mode is ON. Every page has noindex and the demo banner. Set demo_mode to false at launch.")
    review = os.path.join(HERE, "removed-service-mentions.txt")
    if REMOVED_MENTIONS:
        with open(review, "w", encoding="utf-8") as f:
            f.write("Sentences that mention services this client does NOT offer. The links were turned into plain text,\n"
                    "but the wording may still imply the service is offered. Reword or remove each one in _build/content_*.py\n"
                    "or _build/pages.py, then rebuild until this file is gone.\n\n")
            for sent, names in sorted(REMOVED_MENTIONS.items()):
                f.write(f"- [{', '.join(sorted(names))}] {sent}\n")
        print(f"CLIENT REVIEW: {len(REMOVED_MENTIONS)} sentence(s) mention services this client does not offer. See _build/removed-service-mentions.txt")
    elif os.path.exists(review):
        os.remove(review)
    if not LOGO_FILE:
        print("CLIENT INPUT NEEDED: no client logo file (config 'logo'); the built-in mark and business name are used.")
    if not PHOTOS:
        print("CLIENT INPUT NEEDED: no work photos (config 'photos'); photo sections are hidden.")
    for k in ["domain", "phone_display", "email", "form_endpoint"]:
        if "example" in str(CFG[k]) or "555-01" in str(CFG[k]):
            print(f"WARNING: {k} still has a sample value: {CFG[k]}")
    if EST_ON:
        print(f"Instant estimate: ${EST['price_per_square']}/square (±{EST['range_pct']}%), minimum ${EST['minimum_job']}. "
              f"{'Google Solar key set.' if EST.get('google_solar_api_key') else 'No Google Solar key: outline + pitch measurement.'}"
              + (" CLIENT INPUT NEEDED: set the client's real price per square." if CFG.get("demo_mode") else ""))

if __name__ == "__main__":
    main()
