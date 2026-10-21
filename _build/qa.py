#!/usr/bin/env python3
"""Automated QA for the generated site. Run after every build:  python3 _build/qa.py
Checks links, assets, metadata, headings, canonicals, sitemap, JSON-LD, word counts,
near-duplicate content, leftover tokens and colour contrast. Exits non-zero on failures."""
import os, re, json, sys, posixpath, itertools
from html.parser import HTMLParser
from xml.etree import ElementTree as ET
from difflib import SequenceMatcher

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CFG = json.load(open(os.path.join(HERE, "site.config.json")))
DOMAIN = CFG["domain"].rstrip("/")
fails, warns, passes = [], [], []

class P(HTMLParser):
    def __init__(s):
        super().__init__(); s.links=[]; s.assets=[]; s.h1=0; s.title=""; s._t=False; s.meta={}; s.canon=None
        s.ld=[]; s._ld=False; s.ids=[]; s.imgs_noalt=0; s.text=[]; s._skip=0; s._main=False; s.main_text=[]; s.labels_for=set(); s.inputs=[]
    def handle_starttag(s, tag, a):
        a = dict(a)
        if "id" in a: s.ids.append(a["id"])
        if tag == "a" and "href" in a: s.links.append(a["href"])
        if tag in ("link",) and a.get("rel") in ("stylesheet","icon","apple-touch-icon","preload"): s.assets.append(a["href"])
        if tag == "link" and a.get("rel") == "canonical": s.canon = a["href"]
        if tag == "script" and "src" in a: s.assets.append(a["src"])
        if tag == "script" and a.get("type") == "application/ld+json": s._ld=True; s.ld.append("")
        if tag == "img":
            s.assets.append(a.get("src",""));
            if "alt" not in a: s.imgs_noalt += 1
        if tag == "h1": s.h1 += 1
        if tag == "title": s._t = True
        if tag == "meta" and ("name" in a or "property" in a): s.meta[a.get("name") or a.get("property")] = a.get("content","")
        if tag in ("script","style"): s._skip += 1
        if tag == "main": s._main = True
        if tag == "label" and "for" in a: s.labels_for.add(a["for"])
        if tag in ("input","select","textarea") and a.get("type") not in ("hidden",): s.inputs.append(a.get("id"))
    def handle_endtag(s, tag):
        if tag == "title": s._t = False
        if tag == "script": s._ld=False
        if tag in ("script","style"): s._skip -= 1
        if tag == "main": s._main = False
    def handle_data(s, d):
        if s._t: s.title += d
        if s._ld: s.ld[-1] += d
        if not s._skip:
            s.text.append(d)
            if s._main: s.main_text.append(d)

def files():
    for dp, dn, fn in os.walk(ROOT):
        dn[:] = [d for d in dn if not d.startswith((".", "_", "node_modules"))]
        for f in fn:
            if f.endswith(".html"): yield os.path.relpath(os.path.join(dp, f), ROOT).replace(os.sep, "/")

pages = {}
for f in sorted(files()):
    p = P(); p.feed(open(os.path.join(ROOT, f), encoding="utf-8").read()); pages[f] = p

def resolve(src, link):
    link = link.split("#")[0].split("?")[0]
    if not link: return None
    if link.endswith("/") or link in (".", "./"):
        r = resolve(src, link.rstrip("/") + "/index.html" if link not in (".", "./") else "index.html")
        return r
    if link.startswith("/"):
        base = CFG.get("base_path","/"); rel = link[len(base):] if link.startswith(base) else link.lstrip("/")
    else:
        rel = posixpath.normpath(posixpath.join(posixpath.dirname(src), link))
    if rel.endswith("/") or rel in (".", ""): rel = (rel.rstrip("/") + "/index.html").lstrip("/") if rel not in (".", "") else "index.html"
    if rel.startswith("./"): rel = rel[2:]
    return rel

# 1 links + assets
broken = []; inbound = {f: 0 for f in pages}
for f, p in pages.items():
    for l in p.links:
        if l.startswith(("tel:", "mailto:", "http://", "https://", "#")): continue
        t = resolve(f, l)
        if t and not os.path.exists(os.path.join(ROOT, t)): broken.append(f"{f} -> {l}")
        elif t in inbound and t != f: inbound[t] += 1
    for a in p.assets:
        t = resolve(f, a)
        if t and not os.path.exists(os.path.join(ROOT, t)): broken.append(f"{f} asset -> {a}")
(fails if broken else passes).append(f"Internal links and assets: {len(broken)} broken" + ("" if not broken else ": " + "; ".join(broken[:10])))

# 2 orphans (pages with no incoming link from another page)
orph = [f for f, n in inbound.items() if n == 0 and f not in ("index.html", "404.html", "thank-you/index.html")]
(fails if orph else passes).append(f"Orphan pages (no incoming internal links): {len(orph)}" + (": " + ", ".join(orph) if orph else ""))
low = sorted((n, f) for f, n in inbound.items() if f not in ("404.html",))[:5]
passes.append("Lowest incoming-link counts: " + ", ".join(f"{f} ({n})" for n, f in low))

# 3 metadata
idx = {f: p for f, p in pages.items() if "noindex" not in p.meta.get("robots", "") or CFG.get("demo_mode")}
idx = {f: p for f, p in idx.items() if f not in ("404.html", "thank-you/index.html")}
def dupes(key):
    seen = {}
    for f, p in idx.items(): seen.setdefault(key(p).strip(), []).append(f)
    return {k: v for k, v in seen.items() if len(v) > 1}
for name, key in [("titles", lambda p: p.title), ("meta descriptions", lambda p: p.meta.get("description", ""))]:
    d = dupes(key); (fails if d else passes).append(f"Unique {name}: {len(idx)} indexable pages, {len(d)} duplicates")
missing_desc = [f for f, p in idx.items() if not p.meta.get("description")]
(fails if missing_desc else passes).append(f"Meta description present on all indexable pages ({len(missing_desc)} missing)")
long_t = [f"{f} ({len(p.title)})" for f, p in idx.items() if len(p.title) > 65]
(warns if long_t else passes).append(f"Titles over 65 characters: {len(long_t)}" + (": " + ", ".join(long_t[:8]) if long_t else ""))
long_d = [f"{f} ({len(p.meta['description'])})" for f, p in idx.items() if len(p.meta.get('description','')) > 160]
(warns if long_d else passes).append(f"Descriptions over 160 characters: {len(long_d)}" + (": " + ", ".join(long_d[:8]) if long_d else ""))
h1 = [f"{f} ({p.h1})" for f, p in pages.items() if p.h1 != 1]
(fails if h1 else passes).append(f"Exactly one H1 per page: {len(pages) - len(h1)}/{len(pages)}" + (": " + ", ".join(h1) if h1 else ""))
dupid = [f for f, p in pages.items() if len(p.ids) != len(set(p.ids))]
(fails if dupid else passes).append(f"No duplicate element IDs ({len(dupid)} pages with duplicates)")
noalt = sum(p.imgs_noalt for p in pages.values())
(fails if noalt else passes).append(f"Images missing alt attribute: {noalt}")
unl = [f"{f}:{i}" for f, p in pages.items() for i in p.inputs if i and i not in p.labels_for]
(fails if unl else passes).append(f"Form fields with an associated label: {len(unl)} unlabelled" + (": " + ", ".join(unl) if unl else ""))

# 4 canonicals
bad_c = []
for f, p in pages.items():
    if f == "404.html": continue
    exp = DOMAIN + "/" + (f[:-10] if f.endswith("index.html") else f)
    if p.canon != exp: bad_c.append(f"{f}: {p.canon}")
(fails if bad_c else passes).append(f"Canonical URLs match file paths on {DOMAIN}: {len(bad_c)} mismatches" + (": " + "; ".join(bad_c[:5]) if bad_c else ""))
og = [f for f, p in pages.items() if f != "404.html" and p.meta.get("og:url") != p.canon]
(fails if og else passes).append(f"og:url matches canonical on every page ({len(og)} mismatches)")

# 5 sitemap
try:
    tree = ET.parse(os.path.join(ROOT, "sitemap.xml"))
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    locs = [e.text for e in tree.findall(".//s:loc", ns)]
    expected = {p.canon for f, p in pages.items() if f not in ("404.html", "thank-you/index.html")}
    extra, missing = set(locs) - expected, expected - set(locs)
    ok = not extra and not missing and len(locs) == len(set(locs))
    (passes if ok else fails).append(f"sitemap.xml valid XML, {len(locs)} URLs; not-in-site {len(extra)}, missing {len(missing)}, duplicates {len(locs)-len(set(locs))}")
except Exception as e:
    fails.append(f"sitemap.xml invalid: {e}")
rb = open(os.path.join(ROOT, "robots.txt")).read()
(passes if f"Sitemap: {DOMAIN}/sitemap.xml" in rb and "Disallow: /\n" not in rb else fails).append("robots.txt allows crawling and references the canonical sitemap")

# 6 JSON-LD
bad_ld, types = [], {}
for f, p in pages.items():
    for block in p.ld:
        try:
            d = json.loads(block)
            for n in d.get("@graph", [d]): types[n.get("@type")] = types.get(n.get("@type"), 0) + 1
        except Exception as e: bad_ld.append(f"{f}: {e}")
(fails if bad_ld else passes).append(f"JSON-LD parses on all pages ({len(bad_ld)} errors). Types: " + ", ".join(f"{k} ×{v}" for k, v in sorted(types.items())))

# 7 word counts on service pages (main content article, excluding nav/hero/aside/CTA)
def article_words(f):
    src = open(os.path.join(ROOT, f), encoding="utf-8").read()
    m = re.search(r'<div class="prose" data-reveal="up">(.*?)</div>\s*<aside', src, re.S)
    body = m.group(1) if m else ""
    body = re.split(r"<h2>Where we offer", body)[0]
    return len(re.sub(r"<[^>]+>", " ", body).split())
svc_pages = [f for f in pages if re.fullmatch(r"services/[a-z\-]+/index\.html", f)]
wc = {f: article_words(f) for f in svc_pages}
out = [f"{f.split('/')[1]} ({n})" for f, n in wc.items() if not 500 <= n <= 600]
(fails if out else passes).append(f"Service pages with 500–600 words of main content: {len(wc)-len(out)}/{len(wc)} (range {min(wc.values())}–{max(wc.values())})" + (": " + ", ".join(out) if out else ""))
city_pages = [f for f in pages if re.fullmatch(r"services/[a-z\-]+/[a-z]+/index\.html", f)]
cwc = {f: len(re.sub(r"<[^>]+>", " ", re.search(r'<div class="prose" data-reveal="up">(.*?)</div>\s*<aside', open(os.path.join(ROOT, f)).read(), re.S).group(1)).split()) for f in city_pages}
passes.append(f"City service pages: {len(city_pages)} pages, {min(cwc.values())}–{max(cwc.values())} words of main content")

# 8 near-duplicate content between city pages
def body_text(f):
    return " ".join(re.sub(r"<[^>]+>", " ", re.search(r'<div class="prose" data-reveal="up">(.*?)</div>\s*<aside', open(os.path.join(ROOT, f)).read(), re.S).group(1)).split())
texts = {f: body_text(f) for f in city_pages}
def shingles(t, n=5):
    w = re.findall(r"[a-z0-9']+", t.lower()); return {" ".join(w[i:i+n]) for i in range(len(w)-n+1)}
sh = {f: shingles(t) for f, t in texts.items()}
best = max(((len(sh[a] & sh[b]) / len(sh[a] | sh[b]), a, b) for a, b in itertools.combinations(city_pages, 2)))
r, a, b = best
(warns if r > 0.5 else passes).append(f"Near-duplicate check (5-word shingle overlap) across all {len(city_pages)} city pages: highest {r:.0%} ({a} vs {b})")

# 9 leftover tokens / placeholder text
tok = []
for f in pages:
    s = open(os.path.join(ROOT, f), encoding="utf-8").read()
    for pat in [r"\{biz\}", r"\{phone\}", r"\[\[", r"lorem", r"TODO", r"\bTBD\b", r"\[BUSINESS", r"undefined", r"\bNone\b"]:
        flags = re.I if pat in (r"lorem", r"TODO") else 0
        if re.search(pat, re.sub(r"<!--.*?-->", "", s, flags=re.S), flags): tok.append(f"{f}: {pat}")
(fails if tok else passes).append(f"No leftover template tokens or placeholder text ({len(tok)} found)" + (": " + "; ".join(tok[:8]) if tok else ""))
bad_claims = []
for f in pages:
    s = re.sub(r"<[^>]+>", " ", open(os.path.join(ROOT, f), encoding="utf-8").read()).lower()
    for pat in [r"\bbest\b", r"#1\b", r"number one", r"guarantee", r"award", r"\d+\+? years", r"satisfaction", r"cheapest", r"five[- ]star", r"5[- ]star"]:
        if re.search(pat, s): bad_claims.append(f"{f}: {pat}")
(warns if bad_claims else passes).append(f"Unsupported-claim scan (best, #1, guarantee, awards, years, star ratings): {len(bad_claims)} hits" + (": " + "; ".join(bad_claims[:6]) if bad_claims else ""))

# 9b demo banner follows demo_mode
has_bar = [f for f in pages if "Website demo:" in open(os.path.join(ROOT, f), encoding="utf-8").read()]
if CFG.get("demo_mode"):
    (passes if len(has_bar) == len(pages) else fails).append(f"Website demo banner on every page while demo_mode is on ({len(has_bar)}/{len(pages)})")
else:
    (passes if not has_bar else fails).append(f"No demo banner when demo_mode is off ({len(has_bar)} pages still show it)")

# 10 legal links in footer
nl = [f for f, p in pages.items() if not all(any(l.endswith(x) for l in p.links) for x in ("privacy-policy.html", "terms-and-conditions.html", "cookie-policy.html"))]
(fails if nl else passes).append(f"Footer links to Privacy, Terms and Cookie pages on every page ({len(nl)} missing)")

# 11 contrast
def lum(h):
    h = h.lstrip("#"); c = [int(h[i:i+2], 16) / 255 for i in (0, 2, 4)]
    c = [x / 12.92 if x <= .03928 else ((x + .055) / 1.055) ** 2.4 for x in c]
    return .2126 * c[0] + .7152 * c[1] + .0722 * c[2]
def cr(a, b):
    la, lb = sorted([lum(a), lum(b)], reverse=True); return (la + .05) / (lb + .05)
# the client's colours as actually written into the pages by build.py
_style = re.search(r"--accent:(#[0-9a-fA-F]{6});--accent-2:(#[0-9a-fA-F]{6});--accent-paper:(#[0-9a-fA-F]{6})",
                   open(os.path.join(ROOT, "index.html"), encoding="utf-8").read())
ACC, ACC_PAPER = (_style.group(1), _style.group(3)) if _style else ("#ff4d2d", "#b5280f")
pairs = [("body text", "#f2efe9", "#0b0c0e"), ("muted text", "#a9a5a0", "#0b0c0e"), ("muted on card", "#a9a5a0", "#17181c"),
         ("accent text", ACC, "#0b0c0e"), ("accent on card", ACC, "#17181c"), ("button text on accent", "#0b0c0e", ACC), ("paper text", "#131416", "#ece9e4"),
         ("paper muted", "#55524e", "#ece9e4"), ("paper eyebrow", ACC_PAPER, "#ece9e4"), ("CTA band text", "#140b08", ACC),
         ("form error", "#ff8a8a", "#17181c"), ("prose text", "#d6d2cb", "#0b0c0e"), ("estimate status ok", "#9fe0b0", "#17181c"), ("estimate status error", "#ff9e8c", "#17181c"), ("demo note", "#151100", "#ffd54a")]
low = [f"{n} {cr(a,b):.1f}:1" for n, a, b in pairs if cr(a, b) < 4.5]
(fails if low else passes).append("Text contrast ≥ 4.5:1 for all key colour pairs: " + ", ".join(f"{n} {cr(a,b):.1f}" for n, a, b in pairs))

# 12 services the client does not offer leave no pages and no links behind
_all = [d for d in os.listdir(os.path.join(ROOT, "services")) if os.path.isdir(os.path.join(ROOT, "services", d))]
_offered = CFG.get("services") or _all
_gone = [d for d in _all if d not in _offered]
(fails if _gone else passes).append(f"Only offered services have pages ({len(_all)} service folders, {len(_gone)} not offered: {', '.join(_gone)})")
import importlib.util as _ilu, sys as _sys
_sys.path.insert(0, HERE)
from content_services import SERVICES as _a
_removed = [x["slug"] for x in _a if x["slug"] not in _offered]
_dead = sorted({f for f, p in pages.items() for l in p.links if any(f"services/{r}/" in posixpath.normpath(posixpath.join(posixpath.dirname(f), l)) + "/" for r in _removed)})
(fails if _dead else passes).append(f"No links to services that are not offered ({len(_dead)} pages with such links{': ' + ', '.join(_dead[:4]) if _dead else ''})")
_review = os.path.join(HERE, "removed-service-mentions.txt")
if os.path.exists(_review):
    _n = sum(1 for l in open(_review, encoding="utf-8") if l.startswith("- "))
    fails.append(f"{_n} sentence(s) still mention services this client does not offer; reword them (see _build/removed-service-mentions.txt)")
else:
    passes.append("No sentences mention services this client does not offer")


# 13 opening animation: on every indexable page per config, never on 404/thank-you
_intro_on = CFG.get("intro", True); _scope = CFG.get("intro_scope", "all")
_want = {f for f, p in pages.items() if _intro_on and f not in ("404.html", "thank-you/index.html") and (_scope == "all" or f == "index.html")}
_got = {f for f in pages if 'class="intro"' in open(os.path.join(ROOT, f), encoding="utf-8").read()}
_chk = {f for f in pages if 'sessionStorage.getItem("rf-intro")' in open(os.path.join(ROOT, f), encoding="utf-8").read()}
(passes if _got == _want and _chk == _want else fails).append(f"Opening animation overlay + once-per-session check on exactly the {len(_want)} intended pages (never 404 or thank-you)" + ("" if _got == _want and _chk == _want else ": " + ", ".join(sorted(_got ^ _want)[:5])))

# 14 instant estimate wiring
_est = (CFG.get("estimator") or {})
if _est.get("enabled", True):
    _ep = os.path.join(ROOT, "roof-estimate", "index.html")
    _src = open(_ep, encoding="utf-8").read() if os.path.exists(_ep) else ""
    _cfg = re.search(r'<script type="application/json" id="est-config">(.*?)</script>', _src, re.S)
    ok = bool(_cfg)
    try:
        _j = json.loads(_cfg.group(1)) if _cfg else {}
        ok = ok and _j.get("price_per_square") == _est.get("price_per_square") and len(_j.get("pitches", [])) >= 2
    except Exception:
        ok = False
    for need in ("vendor/leaflet/leaflet.js", "js/estimate.js", 'id="est-lead"', 'name="_next"', "Estimate shown"):
        ok = ok and need in _src
    (passes if ok else fails).append("Instant estimate page: config (price per square, pitches) written from site.config.json, Leaflet + estimate.js loaded, lead form with estimate fields")
    _hero = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
    (passes if 'action="roof-estimate/"' in _hero and 'name="address"' in _hero else fails).append("Home hero address box submits to the instant estimate (works without JavaScript)")

for l in passes: print("PASS ", l)
for l in warns: print("WARN ", l)
for l in fails: print("FAIL ", l)
print(f"\n{len(passes)} passed, {len(warns)} warnings, {len(fails)} failed")
sys.exit(1 if fails else 0)
