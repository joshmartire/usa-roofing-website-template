# -*- coding: utf-8 -*-
"""
Client work photos, shared by every Rank Boss template (same file in each repo).

Add photos in the template's config file:

    "photos": [
      {"file": "assets/img/client/job-1.jpg",
       "alt": "Black SUV with full front PPF in Windsor",
       "services": ["paint-protection-film"],
       "caption": "Full front PPF, Windsor"}
    ]

  file      path from the repo root (JPG, PNG or WEBP, any size, phone photos are fine)
  alt       required: what the photo shows, for screen readers and Google Images
  services  optional: service slugs the photo belongs to; it is then also shown on those service pages
  caption   optional: short line shown under the photo

Only the client's own photos of real jobs belong here. Never present stock photos as the client's work.

Each photo is turned upright, resized to 800 and 1600 px wide WEBP copies in assets/img/work/, and re-encoded
without its EXIF data, so phone GPS locations and camera details are never published. With no photos configured,
no photo sections appear anywhere and nothing is invented.
"""
import hashlib
import html
import os
import shutil
import sys

WIDTHS = (800, 1600)
OUT_DIR = "assets/img/work"


def _esc(s):
    return html.escape(str(s), quote=True)


def load(cfg, root, known_slugs, cfg_name="config"):
    """Validate the photos list in the config. Returns a list of dicts (empty when no photos are set)."""
    raw = cfg.get("photos") or []
    if not isinstance(raw, list):
        sys.exit(f"{cfg_name}: photos must be a list of {{file, alt, services, caption}} entries.")
    items = []
    for i, p in enumerate(raw):
        if not isinstance(p, dict):
            sys.exit(f"{cfg_name}: photos[{i}] must be an object with at least file and alt.")
        f = str(p.get("file") or "").strip()
        alt = str(p.get("alt") or "").strip()
        if not f:
            sys.exit(f"{cfg_name}: photos[{i}] has no file.")
        if not alt:
            sys.exit(f"{cfg_name}: photos[{i}] ({f}) needs alt text describing what the photo shows.")
        src = os.path.join(root, f.lstrip("/"))
        if not os.path.isfile(src):
            sys.exit(f"{cfg_name}: photos[{i}] file not found: {f}")
        svcs = p.get("services") or []
        if isinstance(svcs, str):
            svcs = [svcs]
        unknown = [s for s in svcs if s not in known_slugs]
        if unknown:
            sys.exit(f"{cfg_name}: photos[{i}] has unknown service slug(s) {unknown}. Valid: {sorted(known_slugs)}")
        items.append({"src": src, "alt": alt, "services": list(svcs), "caption": str(p.get("caption") or "").strip()})
    return items


def process(items, root):
    """Write the resized, EXIF-free WEBP copies. Clears old ones so removed photos are not published."""
    out = os.path.join(root, OUT_DIR)
    shutil.rmtree(out, ignore_errors=True)
    if not items:
        return items
    try:
        from PIL import Image, ImageOps
    except ImportError:
        sys.exit("photos are set in the config but Pillow is missing: pip install Pillow")
    os.makedirs(out, exist_ok=True)
    for it in items:
        data = open(it["src"], "rb").read()
        h = hashlib.md5(data).hexdigest()[:10]
        im = Image.open(it["src"])
        im = ImageOps.exif_transpose(im).convert("RGB")
        it["files"] = {}
        for w in WIDTHS:
            cp = im if im.width <= w else im.resize((w, round(im.height * w / im.width)), Image.LANCZOS)
            name = f"{h}-{w}.webp"
            cp.save(os.path.join(out, name), "WEBP", quality=80, method=6)  # no exif= argument, so no metadata is written
            it["files"][w] = (name, cp.width, cp.height)
    return items


def for_service(items, slug):
    return [it for it in items if slug in it["services"]]


DEFAULT_CLASSES = {"section": "work-section", "head": "section-head", "kicker": "kicker", "h2": "", "lead": "lead", "group_title": False}


def gallery(items, u, heading, lead="", kicker="Our work", limit=6, section_class=None, classes=None):
    """A responsive photo grid section, or an empty string when there is nothing to show.
    classes lets a template use its own section, heading and eyebrow class names."""
    cl = dict(DEFAULT_CLASSES, **(classes or {}))
    if section_class:
        cl["section"] = section_class
    items = items[:limit]
    if not items:
        return ""
    figs = []
    for it in items:
        small, big = it["files"][WIDTHS[0]], it["files"][WIDTHS[-1]]
        cap = f"<figcaption>{_esc(it['caption'])}</figcaption>" if it["caption"] else ""
        figs.append(
            f'<figure class="work-photo"><img src="{u("/" + OUT_DIR + "/" + small[0])}" '
            f'srcset="{u("/" + OUT_DIR + "/" + small[0])} {small[1]}w, {u("/" + OUT_DIR + "/" + big[0])} {big[1]}w" '
            f'sizes="(max-width: 700px) 100vw, (max-width: 1100px) 50vw, 33vw" width="{small[1]}" height="{small[2]}" '
            f'alt="{_esc(it["alt"])}" loading="lazy" decoding="async">{cap}</figure>')
    lead_html = f'<p class="{cl["lead"]}">{_esc(lead)}</p>' if lead else ""
    h2c = f' class="{cl["h2"]}"' if cl["h2"] else ""
    return (f'<section class="{cl["section"]}"><div class="wrap">'
            + (f'<div class="{cl["head"]}"><div><p class="{cl["kicker"]}">{_esc(kicker)}</p><h2{h2c}>{_esc(heading)}</h2></div>{lead_html}</div>'
               if cl["group_title"] else
               f'<div class="{cl["head"]}"><p class="{cl["kicker"]}">{_esc(kicker)}</p><h2{h2c}>{_esc(heading)}</h2>{lead_html}</div>')
            + f'<div class="work-grid">{"".join(figs)}</div></div></section>')


def sitemap_images(items):
    """URLs of the large copies, for an optional image sitemap or social sharing."""
    return [OUT_DIR + "/" + it["files"][WIDTHS[-1]][0] for it in items]


CSS = """
/* ---- client work photos (added by _build/photos.py; shared across Rank Boss templates) ---- */
.work-section{padding:clamp(48px,7vw,88px) 0}
.work-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}
.work-photo{margin:0;border:1px solid var(--line,#2a2f38);border-radius:var(--r,14px);overflow:hidden;background:var(--card,#12151b)}
.work-photo img{display:block;width:100%;height:auto;aspect-ratio:4/3;object-fit:cover}
.work-photo figcaption{padding:10px 14px;font-size:.92rem;color:var(--muted,#9aa3b0)}
@media (max-width:1100px){.work-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (max-width:700px){.work-grid{grid-template-columns:1fr}}
/* ---- end client work photos ---- */
"""


def ensure_css(css_path):
    """Append the gallery styles to the template stylesheet once (idempotent)."""
    with open(css_path, encoding="utf-8") as f:
        css = f.read()
    start = "/* ---- client work photos"
    if start in css:
        head = css[:css.index(start)].rstrip("\n")
        tail_marker = "/* ---- end client work photos ---- */"
        tail = css[css.index(tail_marker) + len(tail_marker):] if tail_marker in css else ""
        css = head + "\n" + CSS.strip("\n") + "\n" + tail.lstrip("\n")
    else:
        css = css.rstrip("\n") + "\n" + CSS.lstrip("\n")
    with open(css_path, "w", encoding="utf-8") as f:
        f.write(css)
