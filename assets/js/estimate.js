/* Instant roof estimate — satellite map, automatic building outline, editable roof trace and price range.
   Pricing comes from site.config.json ("estimator"), written into the page as #est-config by the build.

   Map and data providers (all requested directly by the visitor's browser, only after they search):
     Address search   Photon (photon.komoot.io), OpenStreetMap Nominatim as a fallback
     Building outline OpenStreetMap buildings via OpenFreeMap vector tiles (Overpass API as a fallback)
     Satellite tiles  Esri World Imagery
     Optional         Google Solar API (buildingInsights) when google_solar_api_key is set
   No dependencies besides Leaflet (assets/vendor/leaflet). */
(function () {
  "use strict";
  var root = document.querySelector("[data-estimator]");
  var cfgEl = document.getElementById("est-config");
  if (!root || !cfgEl) return;
  var C = JSON.parse(cfgEl.textContent);
  var $ = function (id) { return document.getElementById(id); };

  var PHOTON = "https://photon.komoot.io/api/";
  var NOMINATIM = "https://nominatim.openstreetmap.org/search";
  var OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"];
  var TILES = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}";
  var SOLAR = "https://solar.googleapis.com/v1/buildingInsights:findClosest";
  var ATTR = 'Imagery &copy; <a href="https://www.esri.com/">Esri</a>, Maxar, Earthstar Geographics &middot; Outlines &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors via <a href="https://openfreemap.org/">OpenFreeMap</a> &middot; Search by <a href="https://photon.komoot.io/">Photon</a>';
  var SQFT = 10.7639;
  var reduced = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  var form = $("est-search"), input = $("est-address"), list = $("est-suggest"), status = $("est-status");
  var details = $("est-details"), result = $("est-result"), lead = $("est-lead");
  var mapEl = $("est-map"), idle = $("est-idle"), scan = $("est-scan"), tools = $("est-tools"), readout = $("est-readout"), hint = $("est-hint");

  var map = null, poly = null, vtxLayer = null, drawLine = null;
  var S = { place: null, pts: [], detected: [], source: "", solar: null, manual: 0, drawing: false, shown: false };

  var setStatus = function (msg, kind) { status.textContent = msg; status.className = "est-status" + (kind ? " is-" + kind : ""); };
  var money = function (n) { return "$" + Math.round(n).toLocaleString("en-CA"); };
  var fmt = function (n) { return Math.round(n).toLocaleString("en-CA"); };

  function fetchJSON(url, opts, ms) {
    var ctl = "AbortController" in window ? new AbortController() : null;
    var t = ctl ? setTimeout(function () { ctl.abort(); }, ms || 12000) : null;
    opts = opts || {}; if (ctl) opts.signal = ctl.signal;
    return fetch(url, opts).then(function (r) { if (t) clearTimeout(t); if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); },
                                 function (e) { if (t) clearTimeout(t); throw e; });
  }
  var qs = function (o) { return Object.keys(o).map(function (k) { return encodeURIComponent(k) + "=" + encodeURIComponent(o[k]); }).join("&"); };

  /* ---------------- address search ---------------- */
  var bias = C.search_bias || {};
  function photonLabel(p) {
    var line1 = p.housenumber && p.street ? p.housenumber + " " + p.street : (p.name || p.street || "");
    var town = p.city || p.town || p.village || p.district || p.county || "";
    return [line1, town, p.state, p.postcode].filter(function (x, i, a) { return x && a.indexOf(x) === i; }).join(", ");
  }
  function photon(q, limit) {
    var o = { q: q, limit: limit || 6, lang: "en" };
    if (bias.lat) { o.lat = bias.lat; o.lon = bias.lng; }
    return fetchJSON(PHOTON + "?" + qs(o), {}, 8000).then(function (d) {
      var all = (d.features || []).map(function (f) {
        return { label: photonLabel(f.properties || {}), lat: f.geometry.coordinates[1], lng: f.geometry.coordinates[0], cc: ((f.properties || {}).countrycode || "").toLowerCase(), house: !!(f.properties || {}).housenumber };
      }).filter(function (x) { return x.label; });
      var local = bias.country ? all.filter(function (x) { return x.cc === bias.country; }) : all;
      return local.length ? local : all;
    });
  }
  function nominatim(q) {
    var o = { q: q, format: "jsonv2", limit: 1 };
    if (bias.country) o.countrycodes = bias.country;
    return fetchJSON(NOMINATIM + "?" + qs(o), { headers: { "Accept-Language": "en" } }, 8000).then(function (d) {
      return (d || []).map(function (x) { return { label: x.display_name, lat: +x.lat, lng: +x.lon, house: true }; });
    });
  }
  function geocode(q) {
    return photon(q, 1).then(function (r) { if (r.length) return r[0]; throw new Error("none"); })
      .catch(function () { return nominatim(q).then(function (r) { if (r.length) return r[0]; throw new Error("none"); }); });
  }

  // combobox
  var sugg = [], active = -1, typingTimer = null, lastQ = "";
  function closeList() { list.hidden = true; input.setAttribute("aria-expanded", "false"); input.removeAttribute("aria-activedescendant"); active = -1; }
  function renderList() {
    list.innerHTML = "";
    if (!sugg.length) { closeList(); return; }
    sugg.forEach(function (s, i) {
      var li = document.createElement("li");
      li.id = "est-opt-" + i; li.setAttribute("role", "option"); li.setAttribute("aria-selected", i === active ? "true" : "false");
      li.textContent = s.label;
      li.addEventListener("mousedown", function (e) { e.preventDefault(); choose(i); });
      list.appendChild(li);
    });
    list.hidden = false; input.setAttribute("aria-expanded", "true");
    if (active >= 0) input.setAttribute("aria-activedescendant", "est-opt-" + active); else input.removeAttribute("aria-activedescendant");
  }
  function choose(i) { var s = sugg[i]; if (!s) return; input.value = s.label; closeList(); locate(s); }
  input.addEventListener("input", function () {
    clearTimeout(typingTimer);
    var q = input.value.trim();
    if (q.length < 4) { sugg = []; renderList(); return; }
    typingTimer = setTimeout(function () {
      lastQ = q;
      photon(q).then(function (r) { if (q !== lastQ) return; sugg = r.slice(0, 6); active = -1; renderList(); }).catch(function () {});
    }, 260);
  });
  input.addEventListener("keydown", function (e) {
    if (list.hidden) return;
    if (e.key === "ArrowDown") { e.preventDefault(); active = Math.min(sugg.length - 1, active + 1); renderList(); }
    else if (e.key === "ArrowUp") { e.preventDefault(); active = Math.max(0, active - 1); renderList(); }
    else if (e.key === "Enter" && active >= 0) { e.preventDefault(); choose(active); }
    else if (e.key === "Escape") { closeList(); }
  });
  input.addEventListener("blur", function () { setTimeout(closeList, 150); });
  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var q = input.value.trim();
    if (!q) { setStatus("Enter your street address, including the town.", "err"); input.focus(); return; }
    closeList();
    setStatus("Looking up " + q + "…", "busy");
    geocode(q).then(locate).catch(function () {
      setStatus("We couldn't find that address. Check the spelling and include the town, or enter your roof size below.", "err");
      showDetails(); openManual();
    });
  });

  /* ---------------- map ---------------- */
  function ensureMap() {
    if (map) return true;
    if (!window.L) { setStatus("The map couldn't load. You can still enter your roof size below.", "err"); showDetails(); openManual(); return false; }
    var mc = C.map_center || { lat: 42.28, lng: -82.99, zoom: 12 };
    map = L.map(mapEl, { zoomControl: true, scrollWheelZoom: false, maxZoom: 21, tap: true, attributionControl: true }).setView([mc.lat, mc.lng], mc.zoom || 12);
    L.tileLayer(TILES, { maxNativeZoom: 19, maxZoom: 21, attribution: ATTR, crossOrigin: true }).addTo(map);
    map.attributionControl.setPrefix('<a href="https://leafletjs.com/">Leaflet</a>');
    vtxLayer = L.layerGroup().addTo(map);
    map.on("click", onMapClick);
    map.on("mousedown touchstart dragstart zoomstart", function () { if (!S.drawing) hideHint(); });
    mapEl.addEventListener("focusin", function () { map.scrollWheelZoom.enable(); });
    map.on("focus click", function () { map.scrollWheelZoom.enable(); });
    root.classList.add("has-map");
    idle.hidden = true;
    return true;
  }

  function locate(place) {
    S.place = place; S.solar = null; S.manual = 0;
    setStatus("Found " + place.label + ". Measuring the roof…", "busy");
    if (!ensureMap()) return;
    scan.classList.add("is-on");
    var t0 = Date.now();
    map.flyTo([place.lat, place.lng], 20, { duration: reduced ? 0 : 1.6 });
    var jobs = [findBuilding(place.lat, place.lng).catch(function () { return null; })];
    if (C.google_solar_api_key) jobs.push(solar(place.lat, place.lng).catch(function () { return null; }));
    Promise.all(jobs).then(function (r) {
      var wait = Math.max(0, (reduced ? 0 : 1700) - (Date.now() - t0));
      setTimeout(function () {
        scan.classList.remove("is-on");
        var ring = r[0];
        S.solar = r[1] || null;
        showDetails();
        if (ring) {
          S.detected = ring.slice(); setPts(ring, "osm", true);
          setStatus("Roof found. Check the red outline matches your roof, then pick the pitch.", "ok");
          showHint("Drag the corners to fit your roof. Tap a midpoint to add a corner, or Redraw to trace it yourself.");
        } else {
          S.detected = [];
          setStatus("We couldn't find the building outline automatically. Tap the corners of your roof on the map, or enter the size below.", "warn");
          startDraw();
        }
        if (S.solar) {
          var rise = Math.tan(S.solar.deg * Math.PI / 180) * 12, best = null;
          C.pitches.forEach(function (p) { if (!best || Math.abs(p.rise - rise) < Math.abs(best.rise - rise)) best = p; });
          var radio = root.querySelector('input[name="pitch"][value="' + best.id + '"]'); if (radio) radio.checked = true;
          S.source = "solar";
        }
        update();
      }, wait);
    });
  }

  /* ---- OpenStreetMap buildings from OpenFreeMap vector tiles (Mapbox Vector Tile / protobuf, decoded here) ---- */
  var OFM_TILEJSON = "https://tiles.openfreemap.org/planet";
  var ofmTemplate = null;
  function mvtBuildings(buf) {
    var b = new Uint8Array(buf), pos = 0;
    function varint(end) { var r = 0, s = 1, c; do { c = b[pos++]; r += (c & 127) * s; s *= 128; } while (c >= 128 && pos < end); return r; }
    // read the length into a variable first: "pos += varint()" would add it to the value of pos from before the read
    function skip(t, end) { var l; if (t === 0) varint(end); else if (t === 1) pos += 8; else if (t === 2) { l = varint(end); pos += l; } else if (t === 5) pos += 4; }
    function packed(end) { var len = varint(end), stop = pos + len, out = []; while (pos < stop) out.push(varint(stop)); return out; }
    var layers = [];
    while (pos < b.length) {
      var key = varint(b.length), f = key >> 3, t = key & 7;
      if (f === 3 && t === 2) {
        var len = varint(b.length), end = pos + len, Ly = { name: "", extent: 4096, feats: [] };
        while (pos < end) {
          var k2 = varint(end), f2 = k2 >> 3, t2 = k2 & 7;
          if (f2 === 1 && t2 === 2) { var n = varint(end); Ly.name = new TextDecoder().decode(b.subarray(pos, pos + n)); pos += n; }
          else if (f2 === 5 && t2 === 0) Ly.extent = varint(end);
          else if (f2 === 2 && t2 === 2) { var fl = varint(end); Ly.feats.push([pos, pos + fl]); pos += fl; }
          else skip(t2, end);
        }
        layers.push(Ly); pos = end;
      } else skip(t, b.length);
    }
    var bl = layers.filter(function (l) { return l.name === "building"; })[0];
    if (!bl) return { extent: 4096, rings: [] };
    var rings = [];
    bl.feats.forEach(function (fr) {
      pos = fr[0]; var geom = null, type = 0;
      while (pos < fr[1]) { var k = varint(fr[1]), ff = k >> 3, tt = k & 7; if (ff === 3 && tt === 0) type = varint(fr[1]); else if (ff === 4 && tt === 2) geom = packed(fr[1]); else skip(tt, fr[1]); }
      if (type !== 3 || !geom) return;
      var x = 0, y = 0, i = 0, ring = null, ext = null;
      while (i < geom.length) {
        var cmd = geom[i] & 7, cnt = geom[i] >> 3; i++;
        if (cmd === 7) {
          if (ring && ring.length >= 3) {
            var a = 0; for (var j = 0; j < ring.length; j++) { var p = ring[j], q = ring[(j + 1) % ring.length]; a += p[0] * q[1] - q[0] * p[1]; }
            if (ext === null) ext = a > 0;          // first ring of a polygon is its outer ring
            if ((a > 0) === ext) rings.push(ring);  // skip holes (courtyards)
          }
          ring = null; continue;
        }
        for (var c = 0; c < cnt; c++) {
          var dx = geom[i++], dy = geom[i++];
          x += (dx >> 1) ^ -(dx & 1); y += (dy >> 1) ^ -(dy & 1);
          if (cmd === 1) ring = [[x, y]]; else if (ring) ring.push([x, y]);
        }
      }
    });
    return { extent: bl.extent, rings: rings };
  }
  function tileXY(lat, lng, z) {
    var n = Math.pow(2, z), r = lat * Math.PI / 180;
    return [Math.floor((lng + 180) / 360 * n), Math.floor((1 - Math.log(Math.tan(r) + 1 / Math.cos(r)) / Math.PI) / 2 * n)];
  }
  function ofmRings(lat, lng) {
    var z = 14, t = tileXY(lat, lng, z);
    var tpl = ofmTemplate ? Promise.resolve(ofmTemplate) : fetchJSON(OFM_TILEJSON, {}, 6000).then(function (j) { ofmTemplate = j.tiles[0]; return ofmTemplate; });
    return tpl.then(function (u) {
      var url = u.replace("{z}", z).replace("{x}", t[0]).replace("{y}", t[1]);
      var ctl = "AbortController" in window ? new AbortController() : null, tm = ctl ? setTimeout(function () { ctl.abort(); }, 8000) : null;
      return fetch(url, ctl ? { signal: ctl.signal } : {}).then(function (r) { if (tm) clearTimeout(tm); if (!r.ok) throw new Error("HTTP " + r.status); return r.arrayBuffer(); });
    }).then(function (buf) {
      var d = mvtBuildings(buf), n = Math.pow(2, z), E = d.extent;
      return d.rings.map(function (ring) {
        var edge = false;
        var ll = ring.map(function (p) {
          if (p[0] <= 2 || p[0] >= E - 2 || p[1] <= 2 || p[1] >= E - 2) edge = true;
          var px = (t[0] + p[0] / E) / n, py = (t[1] + p[1] / E) / n;
          return L.latLng(Math.atan(Math.sinh(Math.PI * (1 - 2 * py))) * 180 / Math.PI, px * 360 - 180);
        });
        ll.edge = edge;
        return ll;
      });
    });
  }

  function pickRing(rings, lat, lng) {
    if (!rings || !rings.length) return null;
    var pt = L.latLng(lat, lng);
    var inside = rings.filter(function (r) { return contains(r, pt); });
    if (inside.length) return inside.sort(function (a, b) { return measure(a).area - measure(b).area; })[0];
    var best = null, bd = Infinity;
    rings.forEach(function (r) { var d = pt.distanceTo(centroid(r)); if (d < bd) { bd = d; best = r; } });
    return bd < 35 ? best : null;
  }
  function overpassRings(lat, lng) {
    var q = "[out:json][timeout:15];(way[\"building\"](around:45," + lat + "," + lng + "););out geom;";
    var tryEp = function (i) {
      return fetchJSON(OVERPASS[i] + "?data=" + encodeURIComponent(q), {}, 7000)
        .catch(function (e) { if (i + 1 < OVERPASS.length) return tryEp(i + 1); throw e; });
    };
    return tryEp(0).then(function (d) {
      return (d.elements || []).filter(function (el) { return el.geometry && el.geometry.length >= 4; }).map(function (el) {
        var g = el.geometry.map(function (p) { return L.latLng(p.lat, p.lon); });
        if (g.length > 1 && g[0].equals(g[g.length - 1])) g.pop();
        return g;
      });
    });
  }
  /* Building outline: OpenFreeMap vector tile first (fast CDN), Overpass as a fallback when the tile fails
     or the chosen building is cut by the tile edge. */
  function findBuilding(lat, lng) {
    return ofmRings(lat, lng).then(function (rings) {
      var r = pickRing(rings, lat, lng);
      if (r && !r.edge) return r;
      return overpassRings(lat, lng).then(function (o) { return pickRing(o, lat, lng) || r; }, function () { return r; });
    }, function () {
      return overpassRings(lat, lng).then(function (o) { return pickRing(o, lat, lng); });
    });
  }

  function solar(lat, lng) {
    var url = SOLAR + "?" + qs({ "location.latitude": lat.toFixed(6), "location.longitude": lng.toFixed(6), requiredQuality: "LOW", key: C.google_solar_api_key });
    return fetchJSON(url, {}, 10000).then(function (d) {
      var sp = d && d.solarPotential; if (!sp || !sp.wholeRoofStats) return null;
      var segs = sp.roofSegmentStats || [], wsum = 0, dsum = 0;
      segs.forEach(function (s) { var a = (s.stats && s.stats.areaMeters2) || 0; wsum += a; dsum += a * (s.pitchDegrees || 0); });
      return { area: sp.wholeRoofStats.areaMeters2 * SQFT, deg: wsum ? dsum / wsum : 22 };
    });
  }

  /* ---------------- geometry ---------------- */
  function centroid(r) { var la = 0, ln = 0; r.forEach(function (p) { la += p.lat; ln += p.lng; }); return L.latLng(la / r.length, ln / r.length); }
  function contains(r, p) {
    var c = false;
    for (var i = 0, j = r.length - 1; i < r.length; j = i++) {
      var a = r[i], b = r[j];
      if (((a.lat > p.lat) !== (b.lat > p.lat)) && (p.lng < (b.lng - a.lng) * (p.lat - a.lat) / (b.lat - a.lat) + a.lng)) c = !c;
    }
    return c;
  }
  function measure(r) {
    if (!r || r.length < 3) return { area: 0, perim: 0 };
    var c = centroid(r), kx = 111320 * Math.cos(c.lat * Math.PI / 180), ky = 110574;
    var xy = r.map(function (p) { return [(p.lng - c.lng) * kx, (p.lat - c.lat) * ky]; });
    var a = 0, per = 0;
    for (var i = 0; i < xy.length; i++) {
      var p = xy[i], q = xy[(i + 1) % xy.length];
      a += p[0] * q[1] - q[0] * p[1];
      per += Math.hypot(q[0] - p[0], q[1] - p[1]);
    }
    return { area: Math.abs(a) / 2 * SQFT, perim: per * 3.28084 };
  }

  /* ---------------- outline editing ---------------- */
  var vIcon = function () { return L.divIcon({ className: "est-vtx", iconSize: [18, 18] }); };
  var mIcon = function () { return L.divIcon({ className: "est-mid", iconSize: [14, 14] }); };

  function setPts(pts, source, animate) {
    S.pts = pts.slice(); S.source = source; S.manual = 0;
    if (!poly) {
      poly = L.polygon(S.pts, { color: getComputedStyle(document.documentElement).getPropertyValue("--accent").trim() || "#ff4d2d", weight: 3, fillOpacity: 0.18, className: "est-poly", interactive: false }).addTo(map);
    } else poly.setLatLngs(S.pts);
    renderHandles();
    if (animate && !reduced) {
      var el = poly.getElement && poly.getElement();
      if (el && el.getTotalLength) {
        var len = el.getTotalLength();
        el.style.transition = "none"; el.style.strokeDasharray = len; el.style.strokeDashoffset = len; el.style.fillOpacity = 0;
        el.getBoundingClientRect();
        el.style.transition = "stroke-dashoffset 1.3s cubic-bezier(.16,1,.3,1), fill-opacity .6s .9s";
        el.style.strokeDashoffset = 0; el.style.fillOpacity = "";
        setTimeout(function () { el.style.strokeDasharray = ""; el.style.transition = ""; }, 1500);
      }
    }
    if (S.pts.length >= 3) { map.stop(); map.invalidateSize(); map.fitBounds(L.latLngBounds(S.pts).pad(0.9), { maxZoom: 20, animate: false }); }
    tools.hidden = false; readout.hidden = false;
  }

  function renderHandles() {
    vtxLayer.clearLayers();
    if (S.drawing) return;
    S.pts.forEach(function (p, i) {
      var m = L.marker(p, { icon: vIcon(), draggable: true, keyboard: false, autoPan: true, title: "Corner " + (i + 1) }).addTo(vtxLayer);
      m.on("drag", function (e) { S.pts[i] = e.target.getLatLng(); poly.setLatLngs(S.pts); edited(); });
      m.on("dragend", function () { renderHandles(); });
      m.on("contextmenu dblclick", function (e) { L.DomEvent.stop(e); if (S.pts.length > 3) { S.pts.splice(i, 1); poly.setLatLngs(S.pts); renderHandles(); edited(); } });
    });
    if (S.pts.length < 3) return;
    S.pts.forEach(function (p, i) {
      var q = S.pts[(i + 1) % S.pts.length];
      var mid = L.latLng((p.lat + q.lat) / 2, (p.lng + q.lng) / 2);
      var mm = L.marker(mid, { icon: mIcon(), draggable: true, keyboard: false, title: "Add a corner here" }).addTo(vtxLayer);
      var ins = function (ll) { S.pts.splice(i + 1, 0, ll); poly.setLatLngs(S.pts); renderHandles(); edited(); };
      mm.on("click", function (e) { L.DomEvent.stop(e); ins(mid); });
      mm.on("dragend", function (e) { ins(e.target.getLatLng()); });
    });
    $("est-pts").textContent = S.pts.length;
  }
  function edited() { if (S.source !== "drawn") { S.source = "drawn"; S.solar = null; } update(); }

  function startDraw() {
    if (map) map.stop();
    S.drawing = true; S.pts = []; S.manual = 0;
    if (poly) { map.removeLayer(poly); poly = null; }
    if (drawLine) { map.removeLayer(drawLine); drawLine = null; }
    vtxLayer.clearLayers();
    root.classList.add("is-drawing");
    $("est-redraw").lastChild.textContent = "Finish outline";
    tools.hidden = false; readout.hidden = false;
    showHint("Tap each corner of your roof, going around the edge. Tap the first corner (or Finish outline) to close it.");
    update();
  }
  function finishDraw() {
    if (S.pts.length < 3) { showHint("Tap at least three corners to make an outline."); return; }
    S.drawing = false; root.classList.remove("is-drawing");
    if (drawLine) { map.removeLayer(drawLine); drawLine = null; }
    $("est-redraw").lastChild.textContent = "Redraw outline";
    var pts = S.pts.slice(); S.solar = null;
    setPts(pts, "drawn", false);
    showHint("Outline set. Drag the corners to fine-tune it.");
    update();
  }
  function onMapClick(e) {
    if (!S.drawing) return;
    if (S.pts.length >= 3) {
      var first = map.latLngToContainerPoint(S.pts[0]), here = map.latLngToContainerPoint(e.latlng);
      if (first.distanceTo(here) < 16) { finishDraw(); return; }
    }
    S.pts.push(e.latlng);
    if (!drawLine) drawLine = L.polyline(S.pts, { color: "#fff", weight: 2, dashArray: "6 6", interactive: false }).addTo(map);
    else drawLine.setLatLngs(S.pts);
    L.marker(e.latlng, { icon: vIcon(), keyboard: false, interactive: S.pts.length === 1 }).addTo(vtxLayer).on("click", function (ev) { L.DomEvent.stop(ev); if (S.pts.length >= 3) finishDraw(); });
    $("est-pts").textContent = S.pts.length;
    update();
  }
  $("est-redraw").addEventListener("click", function () { if (!map) return; if (S.drawing) finishDraw(); else startDraw(); });
  $("est-reset").addEventListener("click", function () {
    if (!map) return;
    S.drawing = false; root.classList.remove("is-drawing"); $("est-redraw").lastChild.textContent = "Redraw outline";
    if (drawLine) { map.removeLayer(drawLine); drawLine = null; }
    if (S.detected.length) { setPts(S.detected, "osm", true); showHint("Back to the detected outline."); }
    else startDraw();
    update();
  });
  var hintTimer = null;
  function showHint(t) {
    hint.textContent = t; hint.hidden = false; hint.classList.remove("is-fading");
    clearTimeout(hintTimer);
    hintTimer = setTimeout(hideHint, 7000);   // tips get out of the way so they never cover the outline for long
  }
  function hideHint() { if (hint.hidden) return; hint.classList.add("is-fading"); setTimeout(function () { hint.hidden = true; hint.classList.remove("is-fading"); }, 400); }

  /* ---------------- manual size ---------------- */
  function openManual() { var d = root.querySelector(".est-manual"); if (d) d.open = true; }
  $("est-manual-go").addEventListener("click", function () {
    var v = parseFloat($("est-manual-area").value);
    if (!(v >= 200 && v <= 20000)) { setStatus("Enter a footprint between 200 and 20,000 square feet.", "err"); $("est-manual-area").focus(); return; }
    S.manual = v; S.solar = null; S.source = "manual";
    setStatus("Using a " + fmt(v) + " sq ft footprint.", "ok");
    update();
  });

  /* ---------------- pricing ---------------- */
  function sel(name) { var r = root.querySelector('input[name="' + name + '"]:checked'); return r ? r.value : ""; }
  function find(arr, id) { for (var i = 0; i < arr.length; i++) if (arr[i].id === id) return arr[i]; return arr[0]; }
  root.addEventListener("change", function (e) { if (e.target.name === "pitch" || e.target.name === "storeys" || e.target.name === "layers") update(); });

  function showDetails() { if (details.hidden) { details.hidden = false; } }

  var shown = { low: 0, high: 0 }, animId = 0;
  function animateTo(low, high) {
    var from = { low: shown.low, high: shown.high }, t0 = performance.now(), id = ++animId, dur = reduced ? 0 : 700;
    var step = function (now) {
      if (id !== animId) return;
      var t = dur ? Math.min(1, (now - t0) / dur) : 1, e = 1 - Math.pow(1 - t, 3);
      shown.low = from.low + (low - from.low) * e; shown.high = from.high + (high - from.high) * e;
      $("est-low").textContent = money(shown.low); $("est-high").textContent = money(shown.high);
      if (t < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }

  function update() {
    var fp = 0, per = 0, src = S.source;
    if (S.manual) { fp = S.manual; per = 4 * Math.sqrt(fp) * 1.15; src = "manual"; }
    else if (S.pts.length >= 3 && !S.drawing) { var m = measure(S.pts); fp = m.area; per = m.perim; }
    else if (S.drawing && S.pts.length >= 3) { var m2 = measure(S.pts); fp = m2.area; per = m2.perim; }
    $("est-fp").textContent = fp ? fmt(fp) : "—";
    var pitch = find(C.pitches, sel("pitch")), storey = find(C.storeys, sel("storeys")), layers = sel("layers") || "1";
    var o = +C.overhang_ft || 0;
    var surface;
    if (S.solar && src === "solar") surface = S.solar.area;
    else if (fp) surface = (fp + per * o + 4 * o * o) * Math.sqrt(1 + Math.pow(pitch.rise / 12, 2));
    else { result.hidden = true; return; }
    var raw = surface / 100, squares = raw * (1 + (+C.waste_pct || 0) / 100);
    var mid = squares * C.price_per_square * (pitch.price_mult || 1) * (storey.price_mult || 1);
    if (layers === "2") mid += raw * (+C.extra_layer_per_square || 0);
    mid = Math.max(mid, +C.minimum_job || 0);
    var r = (+C.range_pct || 0) / 100, rt = +C.round_to || 1;
    var low = Math.max(mid * (1 - r), +C.minimum_job || 0), high = mid * (1 + r) + (layers === "unsure" ? raw * (+C.extra_layer_per_square || 0) : 0);
    low = Math.floor(low / rt) * rt; high = Math.ceil(high / rt) * rt;
    var srcLabel = { osm: "Satellite outline", drawn: "Your traced outline", manual: "Size you entered", solar: "Google Solar roof data" }[src] || "Satellite outline";
    $("est-area").textContent = fmt(surface) + " sq ft";
    $("est-squares").textContent = squares.toFixed(1);
    $("est-source").textContent = srcLabel;
    if (fp && !S.manual && (fp < 350 || fp > 12000)) showHint(fp < 350 ? "That outline looks small for a house. Make sure it covers the whole roof, including any attached garage." : "That outline looks very large. Check it only covers your building.");
    var wasHidden = result.hidden;
    result.hidden = false;
    animateTo(low, high);
    if (wasHidden) { result.classList.add("is-new"); setTimeout(function () { result.classList.remove("is-new"); }, 1200); }
    // lead form hidden fields
    var set = function (id, v) { var el = $(id); if (el) el.value = v; };
    set("lead-property-address", S.place ? S.place.label : input.value.trim());
    set("lead-coordinates", S.place ? S.place.lat.toFixed(6) + ", " + S.place.lng.toFixed(6) : "");
    set("lead-measured-footprint-(sq-ft)", fp ? fmt(fp) : "");
    set("lead-roof-surface-(sq-ft)", fmt(surface));
    set("lead-squares-incl.-waste", squares.toFixed(1));
    set("lead-pitch", pitch.label + " (~" + pitch.rise + "/12)");
    set("lead-stories", storey.label);
    set("lead-old-layers", layers === "unsure" ? "Not sure" : layers);
    set("lead-measurement-source", srcLabel);
    set("lead-estimate-shown", money(low) + " – " + money(high) + " " + (C.currency || "USD"));
  }

  $("est-lead-open").addEventListener("click", function () {
    lead.hidden = false;
    lead.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "start" });
    setTimeout(function () { $("lead-name").focus({ preventScroll: true }); }, reduced ? 0 : 450);
  });

  /* address handed over from the home page hero (?address=...) */
  try {
    var a = new URLSearchParams(location.search).get("address");
    if (a) { input.value = a; setTimeout(function () { form.requestSubmit ? form.requestSubmit() : form.dispatchEvent(new Event("submit", { cancelable: true })); }, 300); }
  } catch (e) {}
})();
