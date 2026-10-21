# Launch Checklist, Test Report & Technical Notes

Template build: October 21, 2026. Sample business "Hammerline Roofing" with placeholder contact details and **sample estimate pricing**. Not ready to index until the client items below are done and `demo_mode` is `false`.

## 1. Test report

### Passed (verified by running tests, not by reading code)

**Static QA** (`python3 _build/qa.py`, output in `_build/qa-latest.txt`): 30 passed, 0 failed.
- 67 pages; 0 broken internal links or assets; 0 orphan pages.
- 65 indexable pages: unique titles and descriptions, titles ≤ 65 characters, one H1 per page, no duplicate IDs, every form field labelled.
- Canonical and `og:url` match the file path on every page. `sitemap.xml` is valid with 65 URLs, exactly matching the indexable inventory. `robots.txt` points to it.
- JSON-LD parses everywhere: RoofingContractor ×1, WebSite ×1, Service ×52, BreadcrumbList ×65, ItemList ×1, ContactPage ×1, WebApplication ×1.
- All 13 service pages have 500–600 words of main content (505–562). The 39 city pages have 300+ words each. The highest overlap between any two city pages is 35%.
- Contrast ≥ 4.5:1 on all key colour pairs (lowest 4.6). No template tokens left. Legal links in every footer. Demo banner on every page.
- Opening animation overlay is on exactly the 65 indexable pages and never on the 404 or thank-you page. The estimate page carries the config pricing.

**Browser QA** (`python3 _build/qa_browser.py --axe axe.min.js`, headless Chromium at 1440×900 and 390×844, output in `_build/qa-browser-latest.txt`): 58 passed, 0 failed.
- Opening animation: covers the screen, aria-hidden, nothing focusable. It ends by itself in ~3.5 s, and a tap skips it. It plays on a **first landing on a service page** and doesn't replay on the next page or the home page. It's skipped for a `#hash`, never shows on the 404, and is off for reduced motion.
- Headline opaque from first paint. Local CLS ≤ 0.06 and LCP < 300 ms on home and service pages, desktop and phone.
- Hero video loads after first paint (muted, inline). It's skipped for reduced motion and data saver.
- Roof anatomy sequence completes all 5 layers. Menus work by keyboard (Escape returns focus) and on mobile. The quote form blocks empty submissions.
- **Instant estimate** (map services mocked with fixed data):
  - No third-party requests until the visitor searches.
  - Keyboard address suggestions, outline decoded from a vector tile, price within 4% of the exact outline.
  - Pitch, storey and layer adjustments apply.
  - Dragging a corner re-measures, and Reset restores the outline.
  - The typed footprint gives **exactly** the config maths.
  - If the tile service is down, the Overpass fallback finds the outline.
  - With no building found, the visitor can trace the corners.
  - The home hero address hands off to the estimate.
  - The lead form validates and carries the address, measurements and range.
  - No JS errors.
- axe-core (WCAG 2.1 A/AA + best practice): 0 violations on home, services hub, a service page, a city page, a city hub, the estimate page, contact, FAQ, privacy and 404. The scroll-fill statement is scanned in its scrolled (filled) state; before scrolling, its unfilled words are intentionally dim.

**Live services checked from a real website origin (Oct 21, 2026):**
- Photon address search works with CORS and found real Windsor and Tecumseh addresses.
- Nominatim fallback works.
- Esri World Imagery tiles load (200).
- OpenFreeMap tiles load in ~150 ms with CORS. The decoder found the right house for real addresses in Tecumseh and Windsor (Sandwich St and Kildare Rd).
- **The public Overpass server was at capacity during testing** (502 "all workers busy"), which is why OpenFreeMap is the primary outline source and Overpass only a fallback.

### Not tested yet (needs the deployed site or client accounts)
- The full estimator against live services on the deployed URL (each service was checked individually; run one real address end to end after deploy).
- Form delivery: needs the client's email in `form_endpoint` and FormSubmit activation.
- Live domain, HTTPS, PageSpeed Insights / Core Web Vitals in the field, Rich Results Test, real iOS Safari and Android devices, Search Console.
- Google Solar API path (only active when a key is set). It is coded against Google's documented `buildingInsights:findClosest` response but untested without a key.

### Requires client input
| Item | Where |
|---|---|
| Business name, legal name, phone, email, domain, hours | `site.config.json` |
| Public address or service-area business | `address` |
| **Real price per square, range %, waste %, extra-layer price, minimum job, pitch/storey multipliers** | `estimator` |
| Form recipient + FormSubmit activation | `form_endpoint` |
| Google Business Profile and social URLs | `site.config.json` |
| Confirm hero badges and working standards are true | `_build/pages.py` (`tags`, `features`, `statement_points`) |
| Confirm storm-damage availability (emergency tarping, response times) before adding any claims | `content_services.py` (CLIENT REVIEW comment) |
| Real About story, licences, insurance, manufacturer certifications | `pages.py` → `about` |
| Real job photos | `photos` in config |
| Legal review of Privacy, Terms, Cookie drafts | `pages.py` |

## 2. Manual launch tasks
1. Fill in config, set real estimate pricing, set `"demo_mode": false`, run `build.py`, `qa.py`, `qa_browser.py`. All must pass.
2. **Hosting (Cloudflare Pages, like the other demos):** connect the repo, no build command, output `/`. Add the custom domain in Pages and the DNS records Cloudflare shows. `_headers` noindexes only `*.pages.dev`.
3. **Run one real estimate on the live site**: a known address. Check the outline, price range and lead email.
4. Submit a test quote, confirm the FormSubmit activation email, and submit again.
5. Search Console: verify the domain and submit `https://CLIENTDOMAIN/sitemap.xml`.
6. Rich Results Test and PageSpeed Insights (mobile) on home, a service page and the estimate page.
7. Make sure the Google Business Profile name, phone and service areas match the site.
8. If analytics or ad pixels are added: update the Privacy and Cookie policies and add consent blocking where required.

## 3. Instant estimate: providers, limits and upgrades
| Job | Default (free, no key) | Notes / upgrade path |
|---|---|---|
| Address search | Photon (komoot), Nominatim fallback | Fair-use public services. For high traffic, use a paid geocoder (e.g. Geoapify, Google Places) by changing `PHOTON` in `estimate.js` |
| Building outline | OpenFreeMap vector tiles (OSM buildings), Overpass fallback | OpenFreeMap: no key, no limits, commercial use allowed. Outline accuracy depends on OpenStreetMap coverage; Windsor-Essex coverage was good in testing |
| Satellite imagery | Esri World Imagery | Attribution must stay visible. For a high-traffic production site, Esri's terms favour an ArcGIS Location Platform key (free tier available); add `?token=` to `TILES` |
| Roof pitch/area (optional) | — | `google_solar_api_key`: Google Solar API, billed per request beyond the free tier, restricted by HTTP referrer |

Measurement: footprint + overhang, × √(1 + (rise/12)²), + waste → squares × price per square × multipliers → ± range, rounded, never below `minimum_job`. Shown as a ballpark with clear "not a quote" wording on the page, the result card and in the Terms.

## 4. SEO and technical summary
- `lang="en-CA"`, unique title and description, canonical, Open Graph and Twitter card on every page; favicon set and 1200×630 share image (generated in the brand colour).
- Schema: one `RoofingContractor` (`/#business`) on home; `Service` on service and city pages; `BreadcrumbList` matching visible breadcrumbs; `WebSite`, `ItemList`, `ContactPage`, `WebApplication` (estimate). No reviews, ratings, prices or FAQ markup.
- Internal linking: mega menu and footer link every service; each service links its 3 city pages and related services; city pages cross-link and link the hub; the estimate is linked from the nav, footer, hero, asides, CTAs and roof-system city pages.
- Performance: self-hosted fonts, one CSS file plus deferred JS; Leaflet only on the estimate page; the hero poster is preloaded, and the video (5 MB desktop, 3 MB phone) loads after the page and pauses off-screen.
- Privacy: no cookies, no analytics; one sessionStorage flag for the intro; the estimate's map providers are disclosed in the Privacy and Cookie policies.

## 5. URL structure and redirects
Directory-style URLs with trailing slashes; legal pages use `.html`. If a page is renamed after launch, keep a page at the old path with `<meta http-equiv="refresh">` and a canonical pointing to the new URL, or add a Cloudflare redirect rule.

## 6. Page inventory
Full list with canonical URLs: `_build/page-inventory.json`. Home 1, estimate 1, services hub 1, services 13, service × city 39, areas hub 1, city hubs 3, about/FAQ/contact 3, legal 3, thank-you 1 (noindex), 404 1.
