#!/usr/bin/env python3
"""Generates logo, favicons and the default social-share image from the brand config.
Needs Pillow, fontTools and brotli:  pip install pillow fonttools brotli
Run after changing the business name:  python3 _build/make_images.py"""
import json, os, io
from PIL import Image, ImageDraw, ImageFont
from fontTools.ttLib import TTFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CFG = json.load(open(os.path.join(HERE, "site.config.json")))
IMG = os.path.join(ROOT, "assets", "img")
os.makedirs(IMG, exist_ok=True)
ACCENT_HEX = (CFG.get("accent") or "#ff4d2d").strip()
BG, TEXT, MUTED, LINE = (11, 12, 14), (243, 240, 234), (170, 166, 160), (44, 44, 49)
ACCENT = tuple(int(ACCENT_HEX.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
LOGO_FILE = (CFG.get("logo") or "").strip()

def font(name, size):
    f = TTFont(os.path.join(ROOT, "assets", "fonts", name))
    f.flavor = None
    buf = io.BytesIO(); f.save(buf); buf.seek(0)
    return ImageFont.truetype(buf, size)

def mark(draw, x, y, s, w):
    """Roofing mark: two stacked roof chevrons (layers) over a ridge line."""
    k = s / 40
    P = lambda pts: [(x + a * k, y + b * k) for a, b in pts]
    draw.line(P([(3, 21), (20, 6), (37, 21)]), fill=ACCENT, width=w, joint="curve")
    draw.line(P([(9, 28), (20, 18.5), (31, 28)]), fill=ACCENT, width=w, joint="curve")
    draw.line(P([(13, 35), (27, 35)]), fill=ACCENT, width=w)

name = CFG["business_name"]
first, rest = name.split(" ")[0].upper(), " ".join(name.split(" ")[1:]).upper()

# favicon.svg
open(os.path.join(IMG, "favicon.svg"), "w").write(
 '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 40"><rect width="40" height="40" rx="6" fill="#0b0c0e"/>'
 '<g fill="none" stroke="' + ACCENT_HEX + '" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 21L20 8l15 13"/>'
 '<path d="M10.5 27.5L20 19.5l9.5 8"/><path d="M14 33.5h12"/></g></svg>')

for size, fname in [(32, "favicon-32.png"), (180, "apple-touch-icon.png"), (512, "icon-512.png")]:
    S = size * 4
    im = Image.new("RGB", (S, S), BG); d = ImageDraw.Draw(im)
    pad = S * 0.12
    mark(d, pad, pad, S - 2 * pad, max(2, int(S * 0.07)))
    im.resize((size, size), Image.LANCZOS).save(os.path.join(IMG, fname))

# logo.png (for schema): the client's logo when supplied, otherwise mark + wordmark on dark
W, H = 1200, 300
im = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(im)
mark(d, 40, 40, 220, 14)
d.text((300, 52), first, font=font("anton-latin-400-normal.woff2", 140), fill=TEXT)
d.text((306, 218), rest or CFG["short_tagline"].upper(), font=font("barlow-condensed-latin-600-normal.woff2", 44), fill=MUTED)
bbox = d.textbbox((300, 52), first, font=font("anton-latin-400-normal.woff2", 140))
im = im.crop((0, 0, min(W, max(bbox[2], 700) + 50), H))
if LOGO_FILE:
    src = Image.open(os.path.join(ROOT, LOGO_FILE.lstrip("/"))).convert("RGBA")
    src = src.crop(src.getchannel("A").getbbox() or (0, 0, src.width, src.height))
    if src.width > 1200:
        src = src.resize((1200, round(src.height * 1200 / src.width)), Image.LANCZOS)
    im = src
im.save(os.path.join(IMG, "logo.png"))

# og-default.png 1200x630
W, H = 1200, 630
im = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(im)
for x in range(0, W, 48): d.line([(x, 0), (x, H)], fill=(22, 22, 24))
for y in range(0, H, 48): d.line([(0, y), (W, y)], fill=(22, 22, 24))
d.rectangle([0, H - 14, W, H], fill=ACCENT)
mark(d, 70, 64, 84, 7)
d.text((176, 74), first, font=font("anton-latin-400-normal.woff2", 64), fill=TEXT)
big = font("anton-latin-400-normal.woff2", 132)
d.text((70, 210), "ROOFS BUILT", font=big, fill=TEXT)
d.text((70, 360), "FOR THE STORM.", font=big, fill=ACCENT)
d.text((74, 530), f"ROOFING  ·  INSTANT ROOF ESTIMATE  ·  {CFG['region_label'].upper()}", font=font("barlow-condensed-latin-600-normal.woff2", 34), fill=MUTED)
# roof layers on the right
for i, col in enumerate([(70, 56, 44), (30, 32, 37), (44, 48, 55), (34, 36, 41)]):
    dy = -i * 14
    d.polygon([(860, 300 + dy), (1010, 190 + dy), (1160, 300 + dy), (1010, 410 + dy)], fill=col)
d.line([(860, 258), (1010, 148), (1160, 258)], fill=ACCENT, width=5)
im.save(os.path.join(IMG, "og-default.png"), optimize=True)
print("Images written to assets/img/")
