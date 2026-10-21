#!/usr/bin/env python3
"""Browser QA (headless Chromium via Playwright). Run after build.py and qa.py:

    pip install playwright && python3 _build/qa_browser.py [--axe path/to/axe.min.js]

Checks the opening animation (landing on any page, once per session, #hash and reduced-motion skips,
LCP/CLS), the hero, the pinned roof sequence, menus, forms and the instant estimate end to end.
Map services (Photon, OpenFreeMap vector tiles, Overpass, Esri tiles) are mocked with fixed test data, so the estimator maths is
checked exactly; the live services must still be checked on the deployed site (see LAUNCH-CHECKLIST.md).
With --axe, runs axe-core (WCAG 2.1 A/AA) on key pages. Exits non-zero on failures."""
import asyncio, functools, http.server, socketserver, threading, json, math, os, sys
from playwright.async_api import async_playwright

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
CFG = json.load(open(os.path.join(HERE, "site.config.json")))
E = CFG.get("estimator") or {}
AXE = sys.argv[sys.argv.index("--axe") + 1] if "--axe" in sys.argv else None
res = []
def rec(ok, msg, extra=""): res.append(("PASS" if ok else "FAIL", msg + (f"  [{extra}]" if extra and not ok else "")))

class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
    def handle(self):
        try: super().handle()
        except (ConnectionResetError, BrokenPipeError): pass
socketserver.TCPServer.allow_reuse_address = True
srv = socketserver.ThreadingTCPServer(("127.0.0.1", 8821), functools.partial(Q, directory=ROOT))
threading.Thread(target=srv.serve_forever, daemon=True).start()
B = "http://127.0.0.1:8821"
SVC_CITY = "/services/roof-repair/franklin/" if os.path.exists(os.path.join(ROOT, "services/roof-repair/franklin")) else None

# ---- estimator fixtures: a 16 m x 11 m building centred on the address point
LAT, LNG = 35.9251, -86.8689
mlat, mlng = 1 / 110574, 1 / (111320 * math.cos(math.radians(LAT)))
RECT = [(-8, -5.5), (8, -5.5), (8, 5.5), (-8, 5.5)]
GEOM = [{"lat": LAT + y * mlat, "lon": LNG + x * mlng} for x, y in RECT]; GEOM.append(GEOM[0])
OVER = {"elements": [{"type": "way", "id": 1, "geometry": GEOM}]}
PHOT = {"features": [{"geometry": {"coordinates": [LNG, LAT]}, "properties": {"housenumber": "123", "street": "Sample Street", "city": "Franklin", "state": "Tennessee", "countrycode": "CA"}}]}
TILE = open(os.path.join(HERE, "test-tile.png"), "rb").read()

# minimal Mapbox Vector Tile encoder for the fixture building (what OpenFreeMap serves)
def _v(n):
    out = b""
    while True:
        b = n & 127; n >>= 7
        if n: out += bytes([b | 128])
        else: return out + bytes([b])
def _k(f, t): return _v(f << 3 | t)
def _ld(f, data): return _k(f, 2) + _v(len(data)) + data
def _zz(n): return (n << 1) ^ (n >> 31)
def mvt_tile(rings_ll, lat, lng, z=14, empty=False):
    n = 2 ** z
    tx = int((lng + 180) / 360 * n); ty = int((1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2 * n)
    feats = b""
    for ring in ([] if empty else rings_ll):
        pts = []
        for la, ln in ring:
            px = (ln + 180) / 360 * n; py = (1 - math.log(math.tan(math.radians(la)) + 1 / math.cos(math.radians(la))) / math.pi) / 2 * n
            pts.append((round((px - tx) * 4096), round((py - ty) * 4096)))
        geom, cx, cy = [], 0, 0
        geom.append(1 | (1 << 3)); geom += [_zz(pts[0][0] - cx), _zz(pts[0][1] - cy)]; cx, cy = pts[0]
        geom.append(2 | ((len(pts) - 1) << 3))
        for x, y in pts[1:]: geom += [_zz(x - cx), _zz(y - cy)]; cx, cy = x, y
        geom.append(7 | (1 << 3))
        packed = b"".join(_v(g) for g in geom)
        feats += _ld(2, _k(3, 0) + _v(3) + _ld(4, packed))
    layer = _k(15, 0) + _v(2) + _ld(1, b"building") + feats + _ld(3, b"render_height") + _k(5, 0) + _v(4096)
    other = _k(15, 0) + _v(2) + _ld(1, b"boundary") + _ld(4, _ld(1, b"x")) + _k(5, 0) + _v(4096)
    return _ld(3, other) + _ld(3, layer)
TILEJSON = json.dumps({"tiles": ["https://tiles.openfreemap.org/planet/test/{z}/{x}/{y}.pbf"], "maxzoom": 14})
RECT_LL = [[(LAT + y * mlat, LNG + x * mlng) for x, y in RECT]]
MVT = mvt_tile(RECT_LL, LAT, LNG)
MVT_EMPTY = mvt_tile(RECT_LL, LAT, LNG, empty=True)

def expected(pitch_id="standard", storey="1", layers="1", manual=None):
    fp_m2 = 16 * 11; fp = fp_m2 * 10.7639; per = 2 * (16 + 11) * 3.28084; o = E["overhang_ft"]
    if manual: fp = manual; per = 4 * math.sqrt(fp) * 1.15
    p = next(x for x in E["pitches"] if x["id"] == pitch_id); s = next(x for x in E["storeys"] if x["id"] == storey)
    surf = (fp + per * o + 4 * o * o) * math.sqrt(1 + (p["rise"] / 12) ** 2)
    raw = surf / 100; sq = raw * (1 + E["waste_pct"] / 100)
    mid = sq * E["price_per_square"] * p["price_mult"] * s["price_mult"] + (raw * E["extra_layer_per_square"] if layers == "2" else 0)
    mid = max(mid, E["minimum_job"]); r = E["range_pct"] / 100; rt = E["round_to"]
    lo = math.floor(max(mid * (1 - r), E["minimum_job"]) / rt) * rt; hi = math.ceil(mid * (1 + r) / rt) * rt
    return f"${lo:,}", f"${hi:,}"

def money(t): return int(t.replace("$", "").replace(",", ""))
def close(got, exp, tol=0.04): return all(abs(money(g) - money(e)) <= money(e) * tol for g, e in zip(got, exp))

PERF = """window.__cls=0;window.__lcp=0;
new PerformanceObserver(l=>{for(const e of l.getEntries()){if(!e.hadRecentInput)window.__cls+=e.value}}).observe({type:'layout-shift',buffered:true});
new PerformanceObserver(l=>{const e=l.getEntries();window.__lcp=e[e.length-1].startTime}).observe({type:'largest-contentful-paint',buffered:true});"""

async def main():
    async with async_playwright() as pw:
        br = await pw.chromium.launch()
        async def fresh(w=1440, h=900, ofm="ok", **kw):
            ctx = await br.new_context(viewport={"width": w, "height": h}, **kw)
            ctx._seen = []
            async def route(r):
                u = r.request.url
                if "openfreemap" in u:
                    ctx._seen.append("ofm")
                    if ofm == "down": await r.fulfill(status=503, body="down", headers={"Access-Control-Allow-Origin": "*"})
                    elif u.endswith("/planet"): await r.fulfill(status=200, content_type="application/json", body=TILEJSON, headers={"Access-Control-Allow-Origin": "*"})
                    else: await r.fulfill(status=200, content_type="application/x-protobuf", body=MVT_EMPTY if ofm == "empty" else MVT, headers={"Access-Control-Allow-Origin": "*"})
                    return
                if "overpass" in u: ctx._seen.append("overpass")
                if "photon.komoot.io" in u or "nominatim" in u: await r.fulfill(status=200, content_type="application/json", body=json.dumps(PHOT), headers={"Access-Control-Allow-Origin": "*"})
                elif "overpass" in u: await r.fulfill(status=200, content_type="application/json", body=json.dumps(OVER), headers={"Access-Control-Allow-Origin": "*"})
                elif "arcgisonline" in u: await r.fulfill(status=200, content_type="image/png", body=TILE, headers={"Access-Control-Allow-Origin": "*"})
                elif u.startswith(B): await r.continue_()
                else: await r.abort()
            await ctx.route("**/*", route)
            await ctx.add_init_script(PERF)
            pg = await ctx.new_page(); pg._errs = []
            pg.on("pageerror", lambda e: pg._errs.append(str(e)))
            return ctx, pg
        gone = "(()=>{const i=document.querySelector('.intro');return !i||!i.isConnected})()"
        noint = "document.documentElement.classList.contains('no-intro')&&!document.querySelector('.intro')"

        # 1 intro on the home page, then not again
        intro_on = CFG.get("intro", True)
        for w, h, tag in ((1440, 900, "desktop"), (390, 844, "mobile")):
            ctx, pg = await fresh(w, h)
            await pg.goto(B + "/", wait_until="domcontentloaded")
            info = await pg.evaluate("(()=>{const i=document.querySelector('.intro');if(!i)return null;const s=getComputedStyle(i);const r=i.getBoundingClientRect();return {pos:s.position,disp:s.display,ah:i.getAttribute('aria-hidden'),foc:i.querySelectorAll('a,button,input,[tabindex]').length,cover:r.width>=innerWidth-1&&r.height>=innerHeight-1}})()")
            rec(bool(info) == intro_on and (not info or (info["pos"] == "fixed" and info["disp"] != "none" and info["ah"] == "true" and info["foc"] == 0 and info["cover"])),
                f"Home ({tag}): opening animation covers the screen, is aria-hidden and has nothing focusable", str(info))
            await pg.wait_for_function(gone, timeout=8000)
            t = await pg.evaluate("performance.now()")
            rec(t < 4200, f"Home ({tag}): animation removes itself within 4.2 s ({t:.0f} ms)")
            await pg.wait_for_timeout(900)
            st = await pg.evaluate("({h1:getComputedStyle(document.querySelector('h1')).opacity,ready:document.documentElement.classList.contains('is-ready'),store:sessionStorage.getItem('rf-intro'),cls:window.__cls,lcp:window.__lcp,btn:(()=>{const b=document.querySelector('.hero .btn--primary').getBoundingClientRect();const e=document.elementFromPoint(b.left+b.width/2,b.top+b.height/2);return !!e&&!!e.closest('.btn')})()})")
            rec(st["h1"] == "1" and st["ready"] and st["btn"], f"Home ({tag}): hero visible and quote button clickable after the animation", str(st))
            rec(st["cls"] < 0.1 and st["lcp"] < 2500, f"Home ({tag}): CLS {st['cls']:.3f} (<0.1), LCP {st['lcp']:.0f} ms locally (<2500)")
            await pg.goto(B + "/services/", wait_until="domcontentloaded")
            rec(await pg.evaluate(noint), f"Home ({tag}): next page in the same session does not replay the animation")
            rec(not pg._errs, f"Home ({tag}): no JavaScript errors", "; ".join(pg._errs[:3]))
            await ctx.close()

        # 2 first landing on a deep page (e.g. from Google)
        if SVC_CITY:
            for w, h, tag in ((390, 844, "mobile"), (1440, 900, "desktop")):
                ctx, pg = await fresh(w, h)
                await pg.goto(B + SVC_CITY, wait_until="domcontentloaded")
                has = await pg.evaluate("!!document.querySelector('.intro')&&getComputedStyle(document.querySelector('.intro')).display!=='none'")
                rec(has == (intro_on and CFG.get("intro_scope", "all") == "all"), f"First landing on a service + city page ({tag}) plays the opening animation")
                h1 = await pg.evaluate("getComputedStyle(document.querySelector('h1')).opacity")
                rec(h1 == "1", f"Service page ({tag}): headline is opaque from first paint (animation never hides text from crawlers)")
                await pg.wait_for_function(gone, timeout=8000); await pg.wait_for_timeout(900)
                st = await pg.evaluate("({cls:window.__cls,lcp:window.__lcp})")
                rec(st["cls"] < 0.1 and st["lcp"] < 2500, f"Service page ({tag}): CLS {st['cls']:.3f}, LCP {st['lcp']:.0f} ms locally")
                await pg.goto(B + "/", wait_until="domcontentloaded")
                rec(await pg.evaluate(noint), f"After landing on a service page ({tag}), the home page does not replay it")
                await ctx.close()
        ctx, pg = await fresh()
        await pg.goto(B + "/contact/#form", wait_until="domcontentloaded")
        rec(await pg.evaluate(noint), "A URL with a #hash skips the opening animation")
        await pg.goto(B + "/404.html", wait_until="domcontentloaded")
        rec(await pg.evaluate("!document.querySelector('.intro')"), "404 page never shows the opening animation")
        await ctx.close()
        ctx, pg = await fresh(reduced_motion="reduce")
        await pg.goto(B + "/", wait_until="domcontentloaded"); await pg.wait_for_timeout(400)
        st = await pg.evaluate("({noint:document.documentElement.classList.contains('no-intro'),vid:!!document.querySelector('.hero__video')&&!!document.querySelector('.hero__video').getAttribute('src'),seq:getComputedStyle(document.querySelector('.sequence')).height})")
        rec(st["noint"] and not st["vid"] and int(float(st["seq"][:-2])) < 3000, "Reduced motion: no opening animation, no hero video, roof sequence shown static", str(st))
        await ctx.close()
        # tap skips
        ctx, pg = await fresh()
        await pg.goto(B + "/about/", wait_until="domcontentloaded"); await pg.wait_for_timeout(300)
        await pg.mouse.click(700, 450)
        await pg.wait_for_function(gone, timeout=2500)
        t = await pg.evaluate("performance.now()")
        rec(t < 2600, f"A tap skips the opening animation (gone at {t:.0f} ms)")
        await ctx.close()

        # 3 hero video + pinned sequence + menus
        ctx, pg = await fresh()
        await pg.goto(B + "/", wait_until="load"); await pg.wait_for_function(gone, timeout=8000); await pg.wait_for_timeout(1500)
        v = await pg.evaluate("(()=>{const v=document.querySelector('.hero__video');return v?{src:v.currentSrc||v.src,muted:v.muted,inline:v.playsInline}:null})()")
        rec(not CFG.get("hero_video", True) or (v and "hero-1600.mp4" in v["src"] and v["muted"] and v["inline"]), "Hero video loads after first paint (desktop file), muted and inline", str(v))
        await pg.evaluate("document.documentElement.style.scrollBehavior='auto'")
        y = await pg.evaluate("(()=>{const s=document.querySelector('.sequence');return s.offsetTop+(s.offsetHeight-innerHeight)*0.99})()")
        await pg.evaluate(f"scrollTo(0,{y})"); await pg.wait_for_timeout(500)
        st = await pg.evaluate("({l:[...document.querySelectorAll('.anatomy .layer')].map(e=>+getComputedStyle(e).getPropertyValue('--l')),act:[...document.querySelectorAll('.sequence__step')].findIndex(e=>e.classList.contains('is-active'))})")
        rec(all(x >= 0.99 for x in st["l"]) and st["act"] == len(st["l"]) - 1, "Roof anatomy sequence: all layers placed and last step active at the end of the pinned scroll", str(st))
        await pg.evaluate("scrollTo(0,0)"); await pg.wait_for_timeout(300)
        await pg.focus(".nav__item[data-dropdown] button"); await pg.keyboard.press("Enter"); await pg.wait_for_timeout(400)
        op = await pg.evaluate("document.querySelector('.nav__item[data-dropdown]').classList.contains('is-open')")
        await pg.keyboard.press("Escape"); await pg.wait_for_timeout(200)
        cl = await pg.evaluate("!document.querySelector('.nav__item.is-open')&&document.activeElement.matches('button.nav__link')")
        rec(op and cl, "Services menu opens with the keyboard and Escape closes it, returning focus")
        await ctx.close()
        ctx, pg = await fresh(390, 844)
        await pg.goto(B + "/faq/#x", wait_until="load"); await pg.wait_for_timeout(600)
        await pg.click(".burger"); await pg.wait_for_timeout(800)
        rec(await pg.evaluate("document.getElementById('mobile-nav').classList.contains('is-open')"), "Mobile menu opens")
        await ctx.close()

        # 3b dropdown menus stay inside the window at common desktop widths
        for w in (1062, 1280, 1440, 1920):
            ctx, pg = await fresh(w, 900)
            await pg.goto(B + "/services/#x", wait_until="load"); await pg.wait_for_timeout(800)
            bad = []
            # open, close and reopen repeatedly (including mid-animation) the way a visitor's mouse does
            for rnd in range(3):
                for i, sel in enumerate(("#mega-services", "#mega-areas")):
                    await pg.hover(f".nav__item[data-dropdown]:nth-of-type({i + 1}) button"); await pg.wait_for_timeout(650 if rnd != 1 else 120)
                    if rnd == 1: await pg.wait_for_timeout(600)
                    r = await pg.evaluate(f"(()=>{{const r=document.querySelector('{sel}').getBoundingClientRect();return [Math.round(r.left),Math.round(r.right),document.documentElement.clientWidth,document.documentElement.scrollWidth]}})()")
                    if r[0] < 0 or r[1] > r[2] or r[3] > r[2]: bad.append(f"round {rnd} {sel} {r}")
                    await pg.mouse.move(w / 2, 700); await pg.wait_for_timeout(250 if rnd == 1 else 700)
            rec(not bad, f"Desktop {w}px: Services and Service Areas dropdowns open fully inside the window, every time they are reopened", "; ".join(bad))
            await ctx.close()
        # 4 contact form validation
        ctx, pg = await fresh()
        await pg.goto(B + "/contact/#f", wait_until="load")
        await pg.click(".contact-panel button[type=submit]"); await pg.wait_for_timeout(200)
        st = await pg.evaluate("({msg:document.querySelector('.contact-panel .form__status').textContent,inv:document.querySelectorAll('.contact-panel [aria-invalid=true]').length,url:location.pathname})")
        rec(st["inv"] >= 5 and "fix" in st["msg"] and st["url"] == "/contact/", "Quote form blocks an empty submission with field errors and a summary", str(st))
        await ctx.close()

        # 5 instant estimate end to end (mocked map services)
        if E.get("enabled", True):
            for w, h, tag in ((1440, 900, "desktop"), (390, 844, "mobile")):
                ctx, pg = await fresh(w, h)
                await pg.goto(B + "/roof-estimate/#t", wait_until="load"); await pg.wait_for_timeout(500)
                third = await pg.evaluate("performance.getEntriesByType('resource').filter(e=>!e.name.startsWith(location.origin)).length")
                rec(third == 0, f"Estimate ({tag}): no third-party requests until the visitor searches", str(third))
                await pg.fill("#est-address", "123 Sample"); await pg.wait_for_timeout(700)
                n = await pg.evaluate("document.querySelectorAll('#est-suggest li').length")
                await pg.keyboard.press("ArrowDown"); await pg.keyboard.press("Enter")
                await pg.wait_for_selector("#est-result:not([hidden])", timeout=8000); await pg.wait_for_timeout(1000)
                got = await pg.evaluate("[document.getElementById('est-low').textContent,document.getElementById('est-high').textContent]")
                rec(n >= 1 and close(got, expected()) and "ofm" in ctx._seen and "overpass" not in ctx._seen, f"Estimate ({tag}): address suggestions by keyboard, outline decoded from the vector tile, price {got[0]}–{got[1]} within 4% of the exact outline (tile precision ~0.45 m)", f"{n} {got} vs {expected()} {ctx._seen}")
                await pg.click('label.opt--pitch:has(input[value="steep"])'); await pg.click('label.opt:has(input[name="storeys"][value="2"])'); await pg.click('label.opt:has(input[name="layers"][value="2"])')
                await pg.wait_for_timeout(900)
                got = await pg.evaluate("[document.getElementById('est-low').textContent,document.getElementById('est-high').textContent]")
                rec(close(got, expected("steep", "2", "2")), f"Estimate ({tag}): steep, 2-storey, 2-layer adjustments applied", f"{got} vs {expected('steep','2','2')}")
                await pg.evaluate("document.getElementById('est-map').scrollIntoView({block:'center'})"); await pg.wait_for_timeout(400)
                b = await pg.evaluate("(()=>{const v=document.querySelectorAll('.est-vtx')[1].getBoundingClientRect();return [v.x+v.width/2,v.y+v.height/2]})()")
                before = await pg.evaluate("document.getElementById('est-fp').textContent")
                await pg.mouse.move(*b); await pg.mouse.down(); await pg.mouse.move(b[0] + 30, b[1], steps=6); await pg.mouse.up(); await pg.wait_for_timeout(600)
                after = await pg.evaluate("[document.getElementById('est-fp').textContent,document.getElementById('est-source').textContent]")
                rec(after[0] != before and "traced" in after[1], f"Estimate ({tag}): dragging a corner re-measures the outline", f"{before} -> {after}")
                await pg.click("#est-reset"); await pg.wait_for_timeout(500)
                rec(await pg.evaluate("document.getElementById('est-fp').textContent") == before, f"Estimate ({tag}): Reset restores the detected outline")
                await pg.fill("#est-manual-area", "1500") if await pg.evaluate("document.querySelector('.est-manual').open=true") else None
                await pg.click("#est-manual-go"); await pg.wait_for_timeout(1100)
                got = await pg.evaluate("[document.getElementById('est-low').textContent,document.getElementById('est-high').textContent,document.getElementById('est-source').textContent]")
                rec(got[2] == "Size you entered" and tuple(got[:2]) == expected("steep", "2", "2", manual=1500), f"Estimate ({tag}): typed footprint (keyboard alternative to the map) gives exactly the config maths: {got[0]}–{got[1]}", f"{got} vs {expected('steep','2','2',1500)}")
                await pg.click("#est-lead-open"); await pg.wait_for_timeout(700)
                await pg.click("#est-lead button[type=submit]"); await pg.wait_for_timeout(200)
                st = await pg.evaluate("({inv:document.querySelectorAll('#est-lead [aria-invalid=true]').length,est:document.getElementById('lead-estimate-shown').value,addr:document.getElementById('lead-property-address').value})")
                rec(st["inv"] == 3 and st["est"].startswith("$") and "Sample Street" in st["addr"], f"Estimate ({tag}): lead form validates and carries the address, measurements and price shown", str(st))
                rec(not pg._errs, f"Estimate ({tag}): no JavaScript errors", "; ".join(pg._errs[:3]))
                await ctx.close()
            # OpenFreeMap down -> Overpass fallback still finds the outline
            ctx, pg = await fresh(ofm="down")
            await pg.goto(B + "/roof-estimate/?address=123%20Sample", wait_until="load")
            await pg.wait_for_selector("#est-result:not([hidden])", timeout=12000); await pg.wait_for_timeout(900)
            got = await pg.evaluate("[document.getElementById('est-low').textContent,document.getElementById('est-high').textContent]")
            rec(close(got, expected(), 0.005) and "overpass" in ctx._seen, "Estimate: if the OpenFreeMap tile service is down, the Overpass fallback finds the same outline", f"{got} {ctx._seen}")
            await ctx.close()
            # hand-off from the home hero
            ctx, pg = await fresh()
            await pg.goto(B + "/#x", wait_until="load")
            await pg.fill("#hero-address", "123 Sample Street, Franklin"); await pg.click(".addr__go")
            await pg.wait_for_selector("#est-result:not([hidden])", timeout=9000)
            rec("/roof-estimate/" in pg.url, "Home hero address box hands the address to the estimate and it runs automatically")
            await ctx.close()
            # no building found -> draw mode
            ctx, pg = await fresh(ofm="empty")
            await ctx.unroute("**/*")
            async def route2(r):
                if "openfreemap" in r.request.url:
                    u = r.request.url
                    if u.endswith("/planet"): await r.fulfill(status=200, content_type="application/json", body=TILEJSON, headers={"Access-Control-Allow-Origin": "*"})
                    else: await r.fulfill(status=200, content_type="application/x-protobuf", body=MVT_EMPTY, headers={"Access-Control-Allow-Origin": "*"})
                    return
                u = r.request.url
                if "photon" in u: await r.fulfill(status=200, content_type="application/json", body=json.dumps(PHOT), headers={"Access-Control-Allow-Origin": "*"})
                elif "overpass" in u: await r.fulfill(status=200, content_type="application/json", body='{"elements":[]}', headers={"Access-Control-Allow-Origin": "*"})
                elif "arcgisonline" in u: await r.fulfill(status=200, content_type="image/png", body=TILE)
                elif u.startswith(B): await r.continue_()
                else: await r.abort()
            await ctx.route("**/*", route2)
            await pg.goto(B + "/roof-estimate/?address=123%20Sample", wait_until="load")
            await pg.wait_for_selector(".is-drawing", timeout=9000); await pg.wait_for_timeout(800)
            box = await pg.evaluate("(()=>{const r=document.getElementById('est-map').getBoundingClientRect();return [r.x+r.width/2,r.y+r.height/2]})()")
            for dx, dy in ((-60, -40), (60, -40), (60, 40), (-60, 40)):
                await pg.mouse.click(box[0] + dx, box[1] + dy); await pg.wait_for_timeout(150)
            await pg.click("#est-redraw"); await pg.wait_for_timeout(600)
            st = await pg.evaluate("({res:!document.getElementById('est-result').hidden,src:document.getElementById('est-source').textContent,draw:document.querySelector('.is-drawing')!==null})")
            rec(st["res"] and not st["draw"] and "traced" in st["src"], "Estimate: with no building outline, the visitor can trace the roof corners and get a price", str(st))
            await ctx.close()

        # 6 axe-core
        if AXE:
            src = open(AXE).read()
            for path in ["/", "/services/", "/services/roof-replacement/", SVC_CITY or "/", "/service-areas/franklin/", "/roof-estimate/", "/contact/", "/faq/", "/privacy-policy.html", "/404.html"]:
                ctx, pg = await fresh()
                await pg.goto(B + path + "#a", wait_until="load"); await pg.wait_for_timeout(1500)
                # reveal everything as a reader scrolling the page would see it (scroll-fill words included)
                await pg.evaluate("document.querySelectorAll('[data-reveal]').forEach(e=>e.classList.add('is-in'));document.querySelectorAll('.fw').forEach(e=>e.classList.add('on'))"); await pg.wait_for_timeout(1300)
                await pg.add_script_tag(content=src)
                v = await pg.evaluate("axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa','best-practice']}}).then(r=>r.violations.map(v=>v.id+'('+v.nodes.length+')'))")
                rec(not v, f"axe-core WCAG 2.1 A/AA + best practice on {path}: {len(v)} violations", ", ".join(v))
                await ctx.close()
        await br.close()

asyncio.run(main())
for s, m in res: print(s, m)
f = sum(1 for s, _ in res if s == "FAIL")
print(f"\n{len(res) - f} passed, {f} failed")
srv.shutdown()
sys.exit(1 if f else 0)
