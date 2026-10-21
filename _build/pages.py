# -*- coding: utf-8 -*-
# Copy for the home page and the standalone pages (about, FAQ, thank-you, legal).
# Items in HTML comments marked CLIENT REVIEW must be confirmed with the client before launch.

GENERAL_FAQS = [
("What areas do you serve?", "We work in {cities}. If your home or building is nearby but outside these communities, contact us and we'll let you know whether we can help."),
("How accurate is the instant roof estimate?", "It's a ballpark for a standard asphalt shingle reshingle, based on your roof's outline in satellite imagery and the pitch you choose. Hidden deck damage, extra layers, chimneys, skylights and complex roof shapes can change the final price, which is confirmed in writing after an on-site inspection."),
("How do I know if I need a new roof or just a repair?", "Isolated damage can usually be repaired. Widespread curling, cracking, granule loss or repeated leaks usually mean the roof is near the end of its life. After an inspection, we'll tell you which applies and show you photos."),
("How long does a roof replacement take?", "Most homes take one to three days. Size, steepness, the number of old layers and the weather all affect the schedule."),
("What happens if you find rotten decking?", "Damaged sheathing has to be replaced before the new roof goes on. We list a per-sheet price in your quote in advance, show you what we found and only replace what needs it."),
("Do I need a permit to replace my roof?", "Replacing shingles with similar materials usually doesn't need a building permit, but structural repairs, new roof framing and new skylight openings generally do. We confirm with your municipality during planning."),
("Can you work with my insurance company after a storm?", "We provide dated photos and a written description of the damage and repair price for you to share with your insurer. Your insurer decides what's covered; we can't promise a claim outcome."),
("What should I check before hiring any roofer?", "Get the scope and price in writing, ask for proof of liability insurance and workers' compensation coverage where applicable, ask how decking and extra layers are priced, and make sure you understand the payment schedule before work starts."),
("Do I need to be home during the work?", "Not the whole time. We'll confirm access, parking for the disposal bin and anything near the house that should be moved before we start."),
("How do I get started?", "Use the instant roof estimate for a ballpark number, call us, or send your details through our quote form. We'll follow up to set up an inspection."),
]

def _and(items):
    items = list(items)
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def home(cfg, cities, services=None, all_offered=True):
    names = [c["name"] for c in cities]
    city_text = _and(names)
    d = {
        "desc": f"Roofing company serving {city_text}: roof replacement, repairs, metal and flat roofing, gutters and an instant satellite roof estimate.",
        "eyebrow": f"Roofing · {cfg['region_label']}",
        "lead": "Roof replacements, repairs, metal and flat roofing, built from the deck up and priced in writing. Enter your address and see a ballpark price for your roof in about a minute.",
        # CLIENT REVIEW: confirm these badges describe how the client actually works.
        "tags": ["Written, itemized quotes", "Full tear-off to the deck", "Photos of every repair"],
        "statement_eyebrow": "Every layer matters.",
        "statement": "Shingles are only the part you see. A roof lasts because of the deck, the eave protection, the underlayment, the flashing and the ventilation underneath, so that's where we put the most care.",
        "statement_points": [
            ("Torn off to the deck", "We remove the old layers, inspect the sheathing and replace what's damaged before anything new goes on."),
            ("Priced in writing", "Itemized quotes with a per-sheet decking price up front, so a surprise on the day isn't a surprise on the bill."),
            ("Shown in photos", "Before and after photos of repairs and anything we find, so you know what was done up there."),
        ],
        "services_lead": "Full replacements, repairs, metal and flat roofs, and the roofline around them. Pick a service to see what's included and what to ask before you hire.",
        # pinned "anatomy of a roof" sequence: one step per layer, bottom to top
        "layers": [
            ("Solid deck", "Old roofing comes off and every sheet of sheathing is checked. Soft or rotted wood is replaced so the new roof has something solid to hold onto."),
            ("Ice & water shield", "Self-adhering membrane at the eaves and in the valleys, where wind-driven rain and heavy runoff try to force water under the shingles."),
            ("Underlayment & drip edge", "Synthetic underlayment over the rest of the deck, with metal drip edge so water drops into the gutter instead of behind it."),
            ("Shingles & flashing", "Starter strips, architectural shingles nailed to the manufacturer's pattern, and new flashing at every wall, chimney and pipe."),
            ("Ridge vent & cap", "A continuous ridge vent lets the attic breathe, finished with ridge cap shingles that lock the top of the roof down."),
        ],
        "process": [
            ("Estimate online", "Use the satellite estimate for a ballpark, or call us. No pressure either way."),
            ("Inspect in person", "We check the roof, flashing, ventilation and attic, and take photos of what we find."),
            ("Quote in writing", "An itemized price, materials list and per-sheet decking price, to review on your own time."),
            ("Roof & clean up", "Install day, magnetic nail sweeps and a final walk-around with you."),
        ],
        "why_lead": "Roofing is noisy, messy and happens where you can't see it. These are the standards every job is run on, so you always know what's happening over your head.",
        # CLIENT REVIEW: confirm these working standards with the client.
        "features": [
            ("Straight answers", "If a repair will hold, we'll say so. If the roof is done, we'll show you why."),
            ("Written, itemized quotes", "Materials, labor, decking and extras listed separately so you can compare quotes properly."),
            ("Protected property", "Tarps over landscaping, plywood against siding where needed and magnetic nail sweeps at the end of the day."),
            ("Photos of the work", "You see what's under the shingles, what we replaced and the finished roof."),
        ],
        "faqs": [(q.replace("{cities}", city_text), a.replace("{cities}", city_text)) for q, a in GENERAL_FAQS[1:5]],
    }
    if not all_offered and services:
        low = [x["name"].lower() for x in services]
        d["desc"] = f"Roofing company serving {city_text}: " + (", ".join(low[:5]) + " and more." if len(low) > 5 else _and(low) + ".")
        if len(d["desc"]) > 158:
            d["desc"] = f"Roofing company serving {city_text}: " + ", ".join(low[:3]) + " and more."
        d["services_lead"] = "Pick a service to see what's included, how the work runs and what to ask before you hire."
    return d


def simple_pages(cfg, cities, services, city_text, all_offered=True):
    biz = cfg["business_name"]
    offered = {x["slug"]: x for x in services}

    def links(slugs, limit=None):
        out = [f"[[{sl}|{offered[sl]['name'].lower()}]]" for sl in dict.fromkeys(slugs) if sl in offered]
        return out[:limit] if limit else out
    faqs = [(q.replace("{cities}", city_text), a.replace("{cities}", city_text)) for q, a in GENERAL_FAQS]
    est_on = (cfg.get("estimator") or {}).get("enabled", True)

    def about(here):
        work = _and(links([x["slug"] for x in services], 6) or ["roofing"])
        return f"""
<!-- CLIENT REVIEW: replace or extend with the client's real story: founding year, owner names, crew, licenses, manufacturer certifications, memberships and real project photos. Do not add claims that can't be verified. -->
<h2>Who we are</h2>
<p>{biz} is a roofing company serving {city_text}. We work on homes, garages and small commercial buildings, and our work includes {work}.</p>
<p>Roofing is one of the few home projects most people never see up close. That's exactly why we explain what we find, put our prices in writing and photograph the work, so you know what's on your roof and why.</p>
<h2>How we work</h2>
<ul>
<li><strong>The whole system, not just shingles.</strong> Deck, eave protection, underlayment, flashing and ventilation are done properly on every roof we replace.</li>
<li><strong>Clear, written quotes.</strong> Your quote spells out materials, labor, decking prices and anything that isn't included.</li>
<li><strong>Honest about repairs.</strong> If a repair will do the job, we'll tell you. If the roof is finished, we'll show you why.</li>
<li><strong>Respect for your property.</strong> Protected landscaping, a tidy site and magnetic nail sweeps before we leave.</li>
</ul>
<h2>Where we work</h2>
<p>We work across {city_text}. Each community has its own housing, weather exposure and permit office, which we cover on our pages for [[area:{cities[0]['slug']}|{cities[0]['name']}]], [[area:{cities[1]['slug']}|{cities[1]['name']}]] and [[area:{cities[2]['slug']}|{cities[2]['name']}]].</p>
<h2>Before you hire anyone</h2>
<p>Whoever you choose, get the scope and price in writing, ask for proof of liability insurance and workers' compensation coverage where applicable, and ask how extra layers and rotted decking are priced. Good roofers are glad to answer those questions. When you're ready, {"try our [[estimate|instant roof estimate]] or " if est_on else ""}[[contact|request a quote]].</p>
"""

    def faq(here):
        out = '<h2>Frequently asked questions</h2><div class="faq">'
        for q, a in faqs:
            if "instant roof estimate" in q.lower() and not est_on:
                continue
            out += f'<details><summary>{q}<i aria-hidden="true"></i></summary><div class="faq__a"><p>{a}</p></div></details>'
        l = links(["roof-replacement", "roof-repair", "metal-roofing", "storm-damage-repair"] + [x["slug"] for x in services], 4) or ["our services"]
        out += '</div><h2>Service-specific questions</h2><p>Each service page answers common questions about that type of work. Start with ' + (
            l[0] if len(l) == 1 else ", ".join(l[:-1]) + " or " + l[-1]) + ', or browse [[services|all services]].</p>'
        return out

    def thanks(here):
        return f"""<h2>We've received your request</h2>
<p>Thanks for contacting {biz}. We'll review your details and follow up by phone or email to set up an inspection.</p>
<p>If your roof is leaking right now, call us at <a href="tel:{cfg['phone_e164']}">{cfg['phone_display']}</a>.</p>
<p>While you wait, you can browse [[services|our services]] or read our [[faq|frequently asked questions]].</p>"""

    tool_privacy = ""
    tool_cookies = ""
    if est_on:
        solar = bool((cfg.get("estimator") or {}).get("google_solar_api_key"))
        tool_privacy = f"""<p><strong>Instant roof estimate.</strong> If you use our instant roof estimate, the address you type is sent to an address-search service (Photon by komoot, with OpenStreetMap Nominatim as a backup) to find its location. That location is then used to request satellite imagery (Esri World Imagery) and building outlines (OpenStreetMap data from OpenFreeMap, with the Overpass API as a backup){", and roof measurements from Google's Solar API" if solar else ""}. These services receive the address or map location and your IP address, as any website does when your browser requests content, and handle it under their own privacy policies. The address, measurements and estimate are not sent to us unless you choose to submit the estimate form.</p>"""
        tool_cookies = f"""<p>If you use the instant roof estimate, your browser requests map imagery, building outlines and address suggestions directly from the providers listed in our [[privacy|Privacy Policy]]. We don't add cookies to those requests, but those providers may log technical information under their own policies.</p>"""

    def privacy(here):
        return f"""
<!-- CLIENT REVIEW / LEGAL REVIEW REQUIRED: This is a draft based on the website as built (quote and estimate forms via {cfg['form_provider_name']}, static hosting, instant estimate map services, no analytics or advertising). Confirm actual data handling, retention periods, email provider and any CRM or other tools before publishing. If analytics, advertising pixels, chat or booking tools are added, this policy must be updated. -->
<p><strong>Effective date:</strong> {cfg['policy_effective_date']}</p>
<p>This Privacy Policy explains how {cfg['legal_name']} ("we", "us") collects, uses and protects personal information through this website and when you contact us about your roof. We handle personal information in accordance with applicable United States and state privacy laws.</p>
<h2>Information we collect</h2>
<p><strong>Information you give us.</strong> When you submit our quote form or send us an instant estimate, we collect your name, phone number, email address, property address or area, the service you're interested in and any details you choose to share. Estimate submissions also include the roof measurements, roof details you selected and the estimated price range shown to you. If you call or email us, we collect the information you provide in that conversation.</p>
{tool_privacy}
<p><strong>Technical information.</strong> When you visit, our hosting provider's servers may automatically log technical information such as your IP address and browser details for security and operational purposes. We do not use this website to collect analytics, and we do not use advertising or tracking cookies.</p>
<h2>How we use your information</h2>
<ul>
<li>To respond to your inquiry and arrange a roof inspection.</li>
<li>To prepare quotes, contracts and work schedules.</li>
<li>To communicate with you about your project before, during and after the work.</li>
<li>To meet legal, accounting, tax and warranty obligations.</li>
</ul>
<p>We do not sell your personal information, and we do not use it for unrelated marketing without your consent.</p>
<h2>Who we share it with</h2>
<p>Quote and estimate requests submitted through this website are transmitted through {cfg['form_provider_name']}, a third-party form service that delivers submissions to our email. Your information may also be shared with suppliers or subcontractors when it's needed to deliver your project, and with professional advisors or authorities where required by law. Service providers we use may store or process information outside your state or outside the United States, where it may be subject to the laws of those jurisdictions.</p>
<h2>How long we keep it</h2>
<p>We keep personal information only as long as needed for the purposes above, including any period required for legal, tax or warranty reasons, and then securely delete or destroy it.</p>
<h2>How we protect it</h2>
<p>We use reasonable administrative, technical and physical safeguards appropriate to the sensitivity of the information. No method of transmission or storage is completely secure, so we cannot guarantee absolute security. Please don't include sensitive information, such as financial details, in our website forms.</p>
<h2>Your choices and rights</h2>
<p>You may ask to access the personal information we hold about you, ask us to correct it, or withdraw your consent to our use of it, subject to legal and contractual restrictions. To make a request, contact us using the details below.</p>
<h2>Cookies</h2>
<p>This website does not set cookies. See our [[cookies|Cookie Policy]] for details on the limited browser storage the site uses.</p>
<h2>Contact us</h2>
<p>Questions about privacy can be sent to <a href="mailto:{cfg['privacy_contact']}">{cfg['privacy_contact']}</a> or by phone at <a href="tel:{cfg['phone_e164']}">{cfg['phone_display']}</a>.</p>
<h2>Changes to this policy</h2>
<p>We may update this policy from time to time. The effective date above shows when it was last changed.</p>
"""

    def terms(here):
        est = """<h2>Instant roof estimates</h2>
<p>The instant roof estimate is an automated ballpark for a standard asphalt shingle reshingle, calculated from satellite imagery, map data and the details you choose. Imagery may be out of date, building outlines may be inaccurate and measurements are approximate. An estimate is not a quote or an offer. The actual price is confirmed only in a written quote after an on-site inspection, and can differ because of roof size, pitch, layers, decking condition, ventilation, flashing, access and other factors.</p>
""" if est_on else ""
        return f"""
<!-- CLIENT REVIEW / LEGAL REVIEW REQUIRED: Draft website terms. Project-specific terms (payment schedules, deposits, warranties, cancellations) belong in the client's written contracts, not here. Have the limitation of liability and governing-law sections reviewed by a lawyer. -->
<p><strong>Effective date:</strong> {cfg['policy_effective_date']}</p>
<p>These Terms and Conditions apply to your use of this website, operated by {cfg['legal_name']} ("we", "us"). By using the website, you agree to these terms.</p>
<h2>Use of this website</h2>
<p>You may use this website for lawful purposes, such as learning about our services and contacting us. You agree not to misuse the website, attempt to interfere with its operation, or submit false or misleading information through our forms.</p>
<h2>Information on this website</h2>
<p>Content on this website is general information about our services. It is not professional, engineering, legal or code-compliance advice for your specific property. Building code, permit and local ordinance requirements vary by municipality and project, and change over time. While we try to keep information accurate and current, we don't warrant that it is complete or error-free.</p>
{est}<h2>Quotes and project agreements</h2>
<p>Nothing on this website is an offer, quote or contract. Pricing, scope, schedules, payment terms, warranties and cancellation terms for any project are set out only in a written quote or contract provided to you after an inspection. If there is a conflict between this website and your written contract, the contract applies.</p>
<h2>Intellectual property</h2>
<p>The text, design, graphics and logos on this website belong to us or our licensors. Map imagery and data shown in the instant estimate belong to their respective providers and are shown with their attribution. You may view and print pages for personal, non-commercial use, but you may not copy, reproduce or republish website content for commercial purposes without our written permission.</p>
<h2>Third-party links and services</h2>
<p>This website may link to third-party websites or use third-party services, such as our form provider and map services. We aren't responsible for the content, terms or privacy practices of those third parties.</p>
<h2>Limitation of liability</h2>
<p>To the extent permitted by law, we are not liable for any indirect or consequential loss arising from your use of this website or reliance on its general information or automated estimates. Nothing in these terms limits any rights you have under applicable consumer protection law.</p>
<h2>Governing law</h2>
<p>These terms are governed by the laws of the State of {cfg['legal_jurisdiction']} and the federal laws of the United States that apply there.</p>
<h2>Changes and contact</h2>
<p>We may update these terms from time to time. Questions can be sent to <a href="mailto:{cfg['email']}">{cfg['email']}</a>. Our [[privacy|Privacy Policy]] explains how we handle personal information.</p>
"""

    def cookies(here):
        return f"""
<!-- CLIENT REVIEW: accurate for the template as built (no cookies, no analytics, no pixels; the instant estimate requests map content from third parties only when used). If Google Analytics, Meta Pixel, Google Ads tags, chat widgets or other embeds are added, update this page and add a consent mechanism that blocks non-essential tags until the visitor agrees, where required. -->
<p><strong>Effective date:</strong> {cfg['policy_effective_date']}</p>
<h2>Does this website use cookies?</h2>
<p>No. This website does not set cookies, and it does not use analytics, advertising pixels or other tracking technologies.</p>
<h2>Browser storage we use</h2>
<p>The website uses your browser's <em>session storage</em> to remember that the opening animation has already played during your visit, so it isn't shown again on every page. This stores a single value with no personal information, isn't shared with us or anyone else, and is cleared automatically when you close your browser tab. Because it's needed only to provide the website as you'd expect, it doesn't require consent.</p>
<h2>Third-party services</h2>
{tool_cookies}
<p>When you submit one of our forms, your browser sends it to {cfg['form_provider_name']}, which delivers it to us by email. That service may display its own pages, such as a spam-protection check, and may use cookies on its own domain under its own policies. Our hosting provider may log technical information such as IP addresses for security purposes, as explained in our [[privacy|Privacy Policy]].</p>
<h2>Managing storage</h2>
<p>You can clear or block site data at any time through your browser settings. The website will continue to work, although the opening animation may play again.</p>
<h2>Changes</h2>
<p>If we add tools that use cookies or similar technologies, we will update this policy and, where required, ask for your consent before those tools run.</p>
"""

    return {
        "about": dict(title=f"About {biz}", desc=f"{biz} is a roofing company serving {city_text}. Learn how we inspect, quote and install roofs, from the deck to the ridge.", eyebrow="About us", h1="About Us", lead="A roofing company built around straight answers, written prices and roofs done right from the deck up.", inner=about, active="about"),
        "faq": dict(title="Roofing FAQ", desc=f"Answers about roof replacement, repairs, permits, rotten decking, storm damage, the instant estimate and hiring a roofer in {city_text}.", eyebrow="FAQ", h1="Frequently Asked Questions", lead="Straight answers about roofs, repairs and how we work, before you commit to anything.", inner=faq, active="faq"),
        "thanks": dict(title="Thank You", desc="Your request has been sent.", eyebrow="Request sent", h1="Thank You", lead="Your details are on their way to us.", inner=thanks, noindex=True, aside=False, cta=False, hero_ctas=False),
        "privacy": dict(title="Privacy Policy", desc=f"How {biz} collects, uses and protects personal information submitted through this website, its forms and the instant roof estimate.", eyebrow="Legal", h1="Privacy Policy", lead="How we collect, use and protect your personal information.", inner=privacy, mark="doc", aside=False, cta=False, hero_ctas=False),
        "terms": dict(title="Terms and Conditions", desc=f"Terms and conditions for using the {biz} website and its instant roof estimate.", eyebrow="Legal", h1="Terms and Conditions", lead="The terms that apply when you use this website.", inner=terms, mark="doc", aside=False, cta=False, hero_ctas=False),
        "cookies": dict(title="Cookie Policy", desc=f"How the {biz} website uses cookies and browser storage.", eyebrow="Legal", h1="Cookie Policy", lead="What this website stores in your browser, and what it doesn't.", inner=cookies, mark="doc", aside=False, cta=False, hero_ctas=False),
    }
