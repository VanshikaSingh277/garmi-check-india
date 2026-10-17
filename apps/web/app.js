/* Garmi Check India - vanilla JS single-page app, no build step.
   Routes: #/ home · #/me personal check · #/area colony · #/gov government · #/how how it works · #/sources
   MapLibre loads lazily (only when a map is on screen). Icons: icons.js. Strings: i18n.js (en / hi). */
(function () {
  "use strict";
  var S = { lang: "en", step: 0, result: null, layer: "hx_index", gscope: "india", gstate: "", gfilter: "", gsort: null, glimit: 60, ptab: "plan",
            a: { lat: null, lon: null, method: null, acc: null, at: null, where: null, roof: null, vulnerable: [], devices: {}, roof_access: true } };
  var app = document.getElementById("app");
  var I = window.ICON;
  /* India-wide view draws only our district polygons (official LGD outline); OpenStreetMap tiles appear from BASE_MINZOOM. */
  var INDIA_FIT = [[68.1, 6.7], [97.4, 37.1]], BOUNDS = [[60, 2], [104, 40]], BASE_MINZOOM = 7, DELHI = { center: [77.12, 28.62], zoom: 9.6 };
  var HEAT = ["#fff7bc", "#fec44f", "#fe9929", "#d95f0e", "#993404"];
  /* colour stops = 10/30/50/70/90th percentile across Indian districts (data/india_district_stats.csv) */
  var LAYERS = {
    hx_index: { key: "layer_index", stops: [0.1, 0.3, 0.5, 0.7, 0.9], unit: "", d: 1 },
    tmax_mean_c: { key: "layer_tmax", stops: [27.4, 33.4, 36.0, 37.2, 38.5], unit: " °C", d: 1 },
    tmin_mean_c: { key: "layer_tmin", stops: [18.7, 23.1, 24.6, 25.4, 26.2], unit: " °C", d: 1 },
    twb_max_mean_c: { key: "layer_twb", stops: [21.1, 22.8, 23.8, 24.9, 26.2], unit: " °C", d: 1 }
  };
  var WARD_STOPS = [0.29, 0.49, 0.59, 0.67, 0.79];
  var NAV = [{ r: "", ic: "home", k: "nav_home" }, { r: "me", ic: "thermo", k: "nav_me" }, { r: "area", ic: "users", k: "nav_area" }, { r: "gov", ic: "landmark", k: "nav_gov" }, { r: "how", ic: "book", k: "nav_how" }];
  var LEVELS = ["low", "moderate", "high", "extreme"];

  try {
    var sv = JSON.parse(localStorage.getItem("gc_state") || "{}");
    if (sv.lang) S.lang = sv.lang;
    if (sv.a) { S.a = Object.assign(S.a, sv.a); if (S.a.lat != null) S.a.method = "saved"; }  // never present an old fix as "just detected"
  } catch (e) {}
  function save() { try { localStorage.setItem("gc_state", JSON.stringify({ lang: S.lang, a: S.a })); } catch (e) {} }

  /* ---------- helpers ---------- */
  function t(k, v) { var s = I18N[S.lang] && I18N[S.lang][k]; if (s == null) s = I18N.en[k]; if (s == null) s = k; if (v) Object.keys(v).forEach(function (x) { s = s.split("{" + x + "}").join(v[x]); }); return s; }
  function esc(x) { return String(x == null ? "" : x).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function fmt(x, d) { return x == null || isNaN(x) ? "–" : Number(x).toFixed(d == null ? 1 : d); }
  function pct(x) { return x == null ? "–" : Math.round(x * 100) + "%"; }
  function inr(x) { try { return new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 }).format(x); } catch (e) { return String(Math.round(x)); } }
  function title(s) { return String(s || "").toLowerCase().replace(/\b\w/g, function (c) { return c.toUpperCase(); }); }
  function accTxt(a) { return a == null ? "" : a < 1000 ? "±" + Math.round(a) + " m" : "±" + (a / 1000).toFixed(a < 10000 ? 1 : 0) + " km"; }
  function hm(iso) { return String(iso || "").slice(11, 16); }
  function $(id) { return document.getElementById(id); }
  function api(path, body) { return fetch(path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {}).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); }); }
  function classBadge(c) { return { "Very high": "extreme", "High": "high", "Medium": "moderate", "Low": "low", "Very low": "low" }[c] || ""; }
  function cssVar(n) { return getComputedStyle(document.documentElement).getPropertyValue(n).trim(); }
  function ranges(rs) { return (rs || []).map(function (r) { return r[0] + "–" + r[1]; }).join(", "); }
  function render(html) { destroyMaps(); app.innerHTML = '<div class="fade">' + html + "</div>"; applyStatic(); window.scrollTo(0, 0); }
  function card(icon, head, body, extra) { return '<div class="card"' + (extra || "") + '><div class="card-h"><div class="ic">' + I(icon) + "</div><h3>" + head + "</h3></div>" + body + "</div>"; }
  function skeletonCard(h) { return '<div class="card"><div class="skeleton" style="height:22px;width:40%"></div><div class="skeleton" style="height:' + (h || 120) + 'px;margin-top:14px"></div></div>'; }

  /* ---------- shell: nav, language, theme ---------- */
  function route() { var h = location.hash.replace(/^#\/?/, ""); return h.split("/")[0]; }
  function applyStatic() {
    document.querySelectorAll("[data-i18n]").forEach(function (el) { el.textContent = t(el.getAttribute("data-i18n")); });
    document.documentElement.lang = S.lang; document.title = t("app_name");
    $("lang-en").classList.toggle("on", S.lang === "en"); $("lang-hi").classList.toggle("on", S.lang === "hi");
    var r = route();
    $("tabs").innerHTML = NAV.map(function (n) { return '<a href="#/' + n.r + '" class="' + (r === n.r ? "on" : "") + '">' + I(n.ic, "sm") + "<span>" + t(n.k) + "</span></a>"; }).join("");
    $("bottomnav").innerHTML = NAV.map(function (n) { return '<a href="#/' + n.r + '" class="' + (r === n.r ? "on" : "") + '"><span class="pillicon">' + I(n.ic) + "</span><span>" + t(n.k) + "</span></a>"; }).join("");
    var th = document.documentElement.getAttribute("data-theme") || "auto";
    $("themeBtn").innerHTML = I(th === "dark" ? "moon" : th === "light" ? "sun" : "monitor");
    $("themeBtn").title = t("theme_" + th); $("themeBtn").setAttribute("aria-label", t("theme_" + th));
  }
  $("logo").innerHTML = I("thermo");
  document.querySelectorAll("[data-lang]").forEach(function (b) { b.onclick = function () { S.lang = b.getAttribute("data-lang"); save(); go(); }; });
  $("themeBtn").onclick = function () {
    var cur = document.documentElement.getAttribute("data-theme") || "auto", next = cur === "auto" ? "light" : cur === "light" ? "dark" : "auto";
    if (next === "auto") document.documentElement.removeAttribute("data-theme"); else document.documentElement.setAttribute("data-theme", next);
    try { localStorage.setItem("gc_theme", next); } catch (e) {}
    applyStatic();
  };
  window.addEventListener("hashchange", go);
  function go() {
    var r = route();
    if (r === "me") return S.result && S.step === 9 ? resultView() : flowStep();
    if (r === "area") return areaView();
    if (r === "gov") return govView();
    if (r === "how") return howView();
    if (r === "sources") return sourcesView();
    return home();
  }

  /* ---------- location ---------- */
  /* Watch the device position for up to 15 s, keep the most accurate fix, stop early once within 50 m. */
  function locate(onFix, onEnd) {
    if (!window.isSecureContext) return onEnd("insecure");
    if (!navigator.geolocation) return onEnd("unsupported");
    var best = null, done = false, id = null, timer = null;
    function finish(code) { if (done) return; done = true; if (id != null) navigator.geolocation.clearWatch(id); clearTimeout(timer); onEnd(best ? null : code); }
    id = navigator.geolocation.watchPosition(function (p) {
      var c = p.coords;
      if (!best || c.accuracy < best.acc) { best = { lat: c.latitude, lon: c.longitude, acc: c.accuracy }; onFix(best); }
      if (c.accuracy <= 50) finish(null);
    }, function (e) { finish(e.code === 1 ? "denied" : e.code === 3 ? "timeout" : "unavailable"); }, { enableHighAccuracy: true, maximumAge: 0, timeout: 20000 });
    timer = setTimeout(function () { finish("timeout"); }, 15000);
  }
  function methodTxt(a) { return a.method === "gps" ? t("method_gps", { a: accTxt(a.acc) }) : t({ map: "method_map", search: "method_search", saved: "method_saved" }[a.method] || "method_map"); }
  function subLine(w) { return [w.district ? esc(w.district) + " " + t("district_label") : "", esc(w.state || "")].filter(Boolean).join(" · "); }
  function placeBlock(w, a, headKey) {
    if (!w) return '<div class="place"><div class="pin">' + I("pin") + '</div><div class="grow"><div class="skeleton" style="height:22px;width:60%"></div><div class="skeleton" style="height:16px;width:40%;margin-top:8px"></div></div></div>';
    if (w.in_india === false) return '<div class="callout warn">' + I("alert") + "<div>" + t("outside_india") + "</div></div>";
    return '<div class="place"><div class="pin">' + I("pin") + '</div><div class="grow">' + (headKey ? '<div class="tiny muted">' + t(headKey) + "</div>" : "") +
      '<div class="name">' + esc(w.label || w.district) + '</div><div class="sub">' + subLine(w) + (w.ward ? " · " + t("ward_label") + " " + esc(w.ward.ward) : "") + "</div>" +
      (a ? '<div class="badges" style="margin-top:8px"><span class="badge primary">' + I(a.method === "gps" ? "locate" : a.method === "search" ? "search" : "pin", "sm") + esc(methodTxt(a)) + '</span><span class="badge num">' + fmt(a.lat, 4) + "°N, " + fmt(a.lon, 4) + "°E</span></div>" : "") + "</div></div>";
  }
  function districtKpis(dh) {
    if (!dh) return "";
    return '<div class="kpis" style="margin-top:14px"><div class="kpi"><div class="l">' + I("sun", "sm") + t("summer_tmax") + '</div><div class="v">' + fmt(dh.tmax_mean_c) + "<small>°C</small></div><div class=\"s\">" + t("hotter_than_india", { p: Math.round(((dh.pct || {}).tmax_mean_c || 0) * 100) }) + "</div></div>" +
      '<div class="kpi"><div class="l">' + I("gauge", "sm") + t("index_label") + '</div><div class="v"><span class="badge ' + classBadge(dh.hx_class) + '" style="font-size:15px">' + esc(dh.hx_class) + '</span></div><div class="s">' + t("index_rank", { r: Math.round(dh.hx_rank), n: dh.n_india || "" }) + "</div></div></div>";
  }
  function locCard() {
    var a = S.a;
    if (a.lat == null) return '<div class="callout">' + I("info") + "<div>" + t("tap_to_move") + "</div></div>";
    return placeBlock(a.where, a, a.method === "saved" ? "saved_place" : "detected") + (a.where ? districtKpis(a.where.district_heat) : "");
  }
  function setLoc(lat, lon, method, acc, ctrl, fly) {
    S.a.lat = lat; S.a.lon = lon; S.a.method = method; S.a.acc = acc || null; S.a.at = new Date().toISOString(); S.a.where = null; save();
    if (ctrl) ctrl.pin(lat, lon, acc, fly !== false);
    if ($("loccard")) $("loccard").innerHTML = locCard();
    return api("/api/where?lat=" + lat + "&lon=" + lon).then(function (w) {
      if (S.a.lat !== lat || S.a.lon !== lon) return;  // a newer fix arrived meanwhile
      S.a.where = w; save();
      if ($("loccard")) $("loccard").innerHTML = locCard();
      if ($("nx") && route() === "me" && S.step === 0) $("nx").disabled = w.in_india === false;
      if (ctrl) ctrl.select(w.district_heat && w.district_heat.id, w.ward && w.ward.ward_no);
    }).catch(function () { if ($("loccard")) $("loccard").innerHTML = locCard(); });
  }
  /* re-describe a saved place (e.g. saved before the district layer existed) without changing how it was found */
  function refreshWhere() {
    var a = S.a, lat = a.lat, lon = a.lon;
    return api("/api/where?lat=" + lat + "&lon=" + lon).then(function (w) {
      if (a.lat !== lat || a.lon !== lon) return;
      a.where = w; save();
      if ($("loccard")) $("loccard").innerHTML = locCard();
    }).catch(function () {});
  }
  /* search: our own /api/search (PIN or place name) - nothing goes to a third-party geocoder */
  function searchBox(id) { return '<div class="search">' + I("search") + '<input class="input" id="' + id + '" type="search" autocomplete="off" enterkeyhint="search" placeholder="' + esc(t("search_ph")) + '" aria-label="' + esc(t("search_ph")) + '"><ul class="menu" id="' + id + '_r" role="listbox"></ul></div>'; }
  function bindSearch(id, onPick) {
    var inp = $(id), ul = $(id + "_r"), timer = null, items = [], seq = 0, active = -1;
    if (!inp) return;
    function paint() { ul.querySelectorAll("li[data-i]").forEach(function (li, i) { li.classList.toggle("active", i === active); }); }
    inp.oninput = function () {
      clearTimeout(timer); var q = inp.value.trim(); active = -1;
      if (q.length < 2) { ul.innerHTML = ""; return; }
      timer = setTimeout(function () {
        var my = ++seq;
        api("/api/search?q=" + encodeURIComponent(q)).then(function (d) {
          if (my !== seq) return; items = d.results;
          ul.innerHTML = items.length ? items.map(function (x, i) { return '<li role="option" data-i="' + i + '"><span class="ic">' + I(x.kind === "pin" ? "pin" : x.town ? "building" : "map", "sm") + "</span><div><b>" + esc(x.label) + "</b><span>" + esc(x.sub) + (x.approx ? " · " + t("approx") : "") + "</span></div></li>"; }).join("")
            : '<li class="none">' + t("no_results") + "</li>";
          ul.querySelectorAll("li[data-i]").forEach(function (li) { li.onmousedown = function (e) { e.preventDefault(); }; li.onclick = function () { var it = items[+li.getAttribute("data-i")]; ul.innerHTML = ""; inp.value = it.label; inp.blur(); onPick(it); }; });
        }).catch(function () {});
      }, 200);
    };
    inp.onkeydown = function (e) {
      var lis = ul.querySelectorAll("li[data-i]");
      if (e.key === "ArrowDown" && lis.length) { e.preventDefault(); active = Math.min(active + 1, lis.length - 1); paint(); }
      else if (e.key === "ArrowUp" && lis.length) { e.preventDefault(); active = Math.max(active - 1, 0); paint(); }
      else if (e.key === "Enter") { e.preventDefault(); var li = lis[active < 0 ? 0 : active]; if (li) li.click(); }
      else if (e.key === "Escape") ul.innerHTML = "";
    };
    inp.onblur = function () { setTimeout(function () { ul.innerHTML = ""; }, 150); };
  }
  function bindGps(btnId, msgId, ctrlRef, after) {
    var b = $(btnId), m = $(msgId);
    if (!b) return;
    b.onclick = function () {
      b.disabled = true; m.innerHTML = '<span class="spin"></span><span>' + t("locating") + "</span>";
      locate(function (f) { m.innerHTML = '<span class="spin"></span><span>' + t("refining", { a: accTxt(f.acc) }) + "</span>"; setLoc(f.lat, f.lon, "gps", f.acc, ctrlRef(), true); },
        function (err) {
          b.disabled = false;
          if (err) { m.innerHTML = '<div class="callout warn">' + I("alert") + "<div>" + t("gps_" + err) + "</div></div>"; return; }
          m.innerHTML = (S.a.acc || 0) > 1000 ? '<div class="callout warn">' + I("alert") + "<div>" + t("gps_rough", { a: accTxt(S.a.acc) }) + "</div></div>" : "";
          if (after) after();
        });
    };
  }

  /* ---------- map ---------- */
  var maps = [], mapLib = null, geoD = null, geoW = null;
  function distGeo() { if (!geoD) geoD = api("/api/india/districts.geojson").catch(function (e) { geoD = null; throw e; }); return geoD; }
  function wardGeo() { if (!geoW) geoW = api("/api/wards.geojson").catch(function (e) { geoW = null; throw e; }); return geoW; }
  function destroyMaps() { maps.forEach(function (m) { try { m.remove(); } catch (e) {} }); maps = []; }
  function loadLib() {
    if (mapLib) return mapLib;
    mapLib = new Promise(function (res, rej) {
      var c = document.createElement("link"); c.rel = "stylesheet"; c.href = "https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css"; document.head.appendChild(c);
      var s = document.createElement("script"); s.src = "https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"; s.onload = res; s.onerror = function () { mapLib = null; rej(); }; document.head.appendChild(s);
    });
    return mapLib;
  }
  function ramp(prop, st) { var e = ["interpolate", ["linear"], ["to-number", ["get", prop]]]; st.forEach(function (v, i) { e.push(v, HEAT[i]); }); return e; }
  function distFill(layer) { return ["case", ["==", ["typeof", ["get", layer]], "number"], ramp(layer, LAYERS[layer].stops), "#c9ced6"]; }
  function circle(lon, lat, r) {
    var pts = [], k = 48, dx = r / (111320 * Math.cos(lat * Math.PI / 180)), dy = r / 110574;
    for (var i = 0; i <= k; i++) { var a = 2 * Math.PI * i / k; pts.push([lon + dx * Math.cos(a), lat + dy * Math.sin(a)]); }
    return { type: "Feature", geometry: { type: "Polygon", coordinates: [pts] } };
  }
  /* opts: {el, center, zoom, wards: "lines"|"fill"|null, onClick(lngLat, districtProps, wardProps), drag(lngLat)} -> Promise(ctrl) */
  function makeMap(opts) {
    distGeo().catch(function () {});
    if (opts.wards) wardGeo().catch(function () {});
    return loadLib().then(function () {
      var m = new maplibregl.Map({ container: opts.el, center: opts.center || [80.5, 22.6], zoom: opts.zoom || 4, minZoom: 3, maxZoom: 17, maxBounds: BOUNDS,
        attributionControl: { compact: true }, dragRotate: false, pitchWithRotate: false,
        style: { version: 8, sources: { osm: { type: "raster", tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"], tileSize: 256, maxzoom: 19,
          attribution: '© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors' } },
          layers: [{ id: "bg", type: "background", paint: { "background-color": cssVar("--map-bg") || "#e3ebf3" } }, { id: "osm", type: "raster", source: "osm", minzoom: BASE_MINZOOM }] } });
      maps.push(m);
      if (!opts.center) m.fitBounds(INDIA_FIT, { padding: 16, duration: 0 });
      m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
      m.touchZoomRotate.disableRotation();
      var ctrl = { map: m, marker: null };
      ctrl.ready = new Promise(function (res) {
        m.on("load", function () {
          var empty = { type: "FeatureCollection", features: [] };
          m.addSource("d", { type: "geojson", data: empty });
          m.addLayer({ id: "df", type: "fill", source: "d", paint: { "fill-color": distFill(S.layer), "fill-opacity": ["interpolate", ["linear"], ["zoom"], 4, 0.9, 7, 0.6, 11, 0.32, 14, 0.12] } });
          m.addLayer({ id: "dl", type: "line", source: "d", paint: { "line-color": "#475569", "line-opacity": 0.55, "line-width": ["interpolate", ["linear"], ["zoom"], 4, 0.25, 9, 0.9] } });
          m.addLayer({ id: "dsel", type: "line", source: "d", filter: ["==", ["get", "id"], "__none__"], paint: { "line-color": "#0d9488", "line-width": 3.5 } });
          distGeo().then(function (g) { m.getSource("d").setData(g); }).catch(function () {});
          if (opts.wards) {
            m.addSource("w", { type: "geojson", data: empty });
            if (opts.wards === "fill") m.addLayer({ id: "wf", type: "fill", source: "w", paint: { "fill-color": ramp("hvi", WARD_STOPS), "fill-opacity": 0.6 } });
            m.addLayer({ id: "wl", type: "line", source: "w", minzoom: 9, paint: { "line-color": "#334155", "line-opacity": 0.6, "line-width": 0.6 } });
            m.addLayer({ id: "wsel", type: "line", source: "w", filter: ["==", ["get", "ward_no"], "__none__"], paint: { "line-color": "#0369a1", "line-width": 3 } });
            wardGeo().then(function (g) { m.getSource("w").setData(g); }).catch(function () {});
          }
          m.addSource("acc", { type: "geojson", data: empty });
          m.addLayer({ id: "accf", type: "fill", source: "acc", paint: { "fill-color": "#0ea5e9", "fill-opacity": 0.15 } });
          m.addLayer({ id: "accl", type: "line", source: "acc", paint: { "line-color": "#0284c7", "line-width": 1.5 } });
          if (opts.onClick) {
            m.on("click", function (e) {
              var d = m.queryRenderedFeatures(e.point, { layers: ["df"] })[0];
              var w = opts.wards ? m.queryRenderedFeatures(e.point, { layers: [opts.wards === "fill" ? "wf" : "wl"] })[0] : null;
              opts.onClick(e.lngLat, d ? d.properties : null, w ? w.properties : null);
            });
            m.getCanvas().style.cursor = "crosshair";
          }
          res(ctrl);
        });
      });
      ctrl.setLayer = function (layer) { ctrl.ready.then(function () { m.setPaintProperty("df", "fill-color", distFill(layer)); }); };
      ctrl.select = function (distId, wardNo) { ctrl.ready.then(function () {
        m.setFilter("dsel", ["==", ["get", "id"], distId || "__none__"]);
        if (opts.wards) m.setFilter("wsel", ["==", ["get", "ward_no"], wardNo || "__none__"]);
      }); };
      ctrl.pin = function (lat, lon, acc, fly) { ctrl.ready.then(function () {
        if (!ctrl.marker) {
          ctrl.marker = new maplibregl.Marker({ color: "#0d9488", draggable: !!opts.drag }).setLngLat([lon, lat]).addTo(m);
          if (opts.drag) ctrl.marker.on("dragend", function () { opts.drag(ctrl.marker.getLngLat()); });
        } else ctrl.marker.setLngLat([lon, lat]);
        m.getSource("acc").setData({ type: "FeatureCollection", features: acc ? [circle(lon, lat, Math.min(acc, 20000))] : [] });
        if (fly !== false) m.flyTo({ center: [lon, lat], zoom: Math.max(m.getZoom(), acc > 3000 ? 10 : 13), speed: 1.6 });
      }); };
      return ctrl;
    });
  }
  function legend(stops, unit, labelKey, d) { return '<div class="legend"><b>' + t(labelKey) + '</b><div class="bar"></div><div class="ends"><span>' + t("lower") + " ≤" + fmt(stops[0], d) + unit + "</span><span>" + t("higher") + " ≥" + fmt(stops[4], d) + unit + "</span></div></div>"; }
  function mapTools(id) {
    return '<div class="maptools"><div class="seg" id="' + id + '">' + Object.keys(LAYERS).map(function (k) { return '<button data-layer="' + k + '" class="' + (k === S.layer ? "on" : "") + '">' + t(LAYERS[k].key) + "</button>"; }).join("") + "</div></div>" +
      '<div id="' + id + '_lg">' + legend(LAYERS[S.layer].stops, LAYERS[S.layer].unit, LAYERS[S.layer].key, LAYERS[S.layer].d) + "</div>";
  }
  function bindTools(id, ctrl) {
    document.querySelectorAll("#" + id + " button").forEach(function (b) { b.onclick = function () {
      S.layer = b.getAttribute("data-layer");
      document.querySelectorAll("#" + id + " button").forEach(function (x) { x.classList.toggle("on", x === b); });
      $(id + "_lg").innerHTML = legend(LAYERS[S.layer].stops, LAYERS[S.layer].unit, LAYERS[S.layer].key, LAYERS[S.layer].d);
      ctrl.setLayer(S.layer);
    }; });
  }
  function mapFail(el) { var n = $(el); if (n) n.outerHTML = '<div class="callout">' + I("info") + "<div>" + t("map_fail") + "</div></div>"; }

  /* ================= HOME ================= */
  function home() {
    var a = S.a, known = a.lat != null && a.where && a.where.in_india !== false;
    render('<section class="hero"><div><span class="eyebrow">' + I("globe", "sm") + t("hero_eyebrow") + "</span><h1>" + t("hero_title") + '</h1><p class="lead">' + t("hero_sub") + "</p>" +
      '<div class="finder">' + searchBox("hq") + '<div class="row"><button class="btn primary lg grow" id="startBtn">' + I("thermo") + t("start") + '</button><button class="btn secondary lg" id="hgps">' + I("locate") + '<span class="hide-sm">' + t("use_gps") + '</span></button></div><div class="statusline" id="hmsg"></div></div>' +
      '<div class="trust"><span>' + I("lock", "sm") + t("trust_private") + "</span><span>" + I("shield", "sm") + t("trust_sourced") + "</span><span>" + I("sparkles", "sm") + t("trust_free") + "</span></div></div>" +
      '<div class="now-card" id="nowcard">' + nowCardInner(known ? null : "empty") + "</div></section>" +
      '<section class="section"><h2>' + t("roles_title") + '</h2><div class="roles">' +
      [["me", "thermo", "individual"], ["area", "users", "society"], ["gov", "landmark", "government"]].map(function (r) {
        return '<a class="role" href="#/' + r[0] + '"><span class="ic">' + I(r[1], "lg") + "</span><b>" + t(r[2]) + '</b><span class="muted">' + t(r[2] + "_sub") + '</span><span class="go">' + t("go") + I("arrow-r", "sm") + "</span></a>"; }).join("") + "</div></section>" +
      '<section class="section"><div class="row between" style="margin-bottom:6px"><h2>' + t("how_teaser") + '</h2><a class="btn ghost sm" href="#/how">' + t("see_how") + I("arrow-r", "sm") + '</a></div><p class="muted" style="margin-bottom:14px">' + t("how_teaser_sub") + "</p>" + pipeline("steps") + "</section>");
    $("startBtn").onclick = function () { location.hash = "#/me"; };
    bindSearch("hq", function (it) { setLoc(it.lat, it.lon, "search", null, null).then(home); });
    bindGps("hgps", "hmsg", function () { return null; }, home);
    if (a.lat != null && (!a.where || (!a.where.district_heat && a.where.in_india !== false))) refreshWhere().then(function () { if (route() === "") home(); });
    if (known) api("/api/weather?lat=" + a.lat + "&lon=" + a.lon).then(function (w) { if ($("nowcard")) $("nowcard").innerHTML = nowCardInner(w); }).catch(function () {});
  }
  function nowCardInner(w) {
    var a = S.a;
    if (w === "empty") return '<div class="row" style="gap:10px"><span class="badge primary">' + I("clock", "sm") + t("now_title") + '</span></div><div class="now-big"><span class="t muted">--°</span></div><p class="muted">' + t("now_pick") + "</p>";
    var head = '<div class="row between"><span class="badge primary">' + I("pin", "sm") + esc(a.where.label) + (a.where.state ? ", " + esc(a.where.state) : "") + '</span><a class="small" href="#/me">' + t("change_place") + "</a></div>";
    if (!w) return head + '<div class="skeleton" style="height:64px;margin:14px 0"></div><div class="kpis"><div class="skeleton" style="height:70px"></div><div class="skeleton" style="height:70px"></div></div>';
    var n = w.now || {}, td = w.today || {}, tm = w.tomorrow || {}, lvl = td.hi_level || "low";
    return head + '<div class="now-big"><span class="t">' + fmt(n.t, 0) + '°</span><span class="s">' + t("feels") + " " + fmt(n.hi, 0) + "° · " + fmt(n.rh, 0) + "% RH</span></div>" +
      '<div class="kpis"><div class="kpi"><div class="l">' + t("today_max") + '</div><div class="v">' + fmt(td.hi_max, 0) + '<small>°C</small></div></div><div class="kpi"><div class="l">' + t("tomorrow_max") + '</div><div class="v">' + fmt(tm.hi_max, 0) + "<small>°C</small></div></div></div>" +
      '<div class="row between" style="margin-top:14px"><span class="small muted">' + t("today_band") + '</span><span class="badge ' + lvl + '">' + t("level_" + lvl) + "</span></div>" +
      '<a class="btn primary block" style="margin-top:14px" href="#/me">' + t("see_status") + I("arrow-r", "sm") + "</a>";
  }
  function pipeline(cls) {
    return '<div class="' + cls + '">' + [["pin", "p1"], ["cloud", "p2"], ["cpu", "p3"], ["shield", "p4"], ["list", "p5"]].map(function (s, i) {
      return '<div class="step"><div class="ic">' + I(s[0]) + '</div><div class="tiny muted">' + t("step_n", { n: i + 1 }) + "</div><b>" + t(s[1] + "_t") + "</b><p>" + t(s[1] + "_d") + "</p></div>"; }).join("") + "</div>";
  }

  /* ================= PERSONAL FLOW ================= */
  var STEPS = ["st_place", "st_roof", "st_people", "st_cooling"];
  function stepper(n) { return '<div class="stepper">' + STEPS.map(function (k, i) { return '<div class="s' + (i <= n ? " on" : "") + (i === n ? " cur" : "") + '"><i></i><span>' + (i + 1) + ". " + t(k) + "</span></div>"; }).join("") + "</div>"; }
  function opt(v, art, k, desc, on, multi) { return '<button class="opt' + (multi ? " multi" : "") + (on ? " on" : "") + '" data-v="' + v + '" aria-pressed="' + (on ? "true" : "false") + '"><span class="art">' + art + "</span><span class=\"grow\"><b>" + t(k) + "</b>" + (desc ? '<span class="d">' + t(desc) + "</span>" : "") + '</span><span class="tick">' + I("check", "sm") + "</span></button>"; }
  function actionbar(backOk, nextLabel, nextDisabled) { return '<div class="actionbar"><button class="btn secondary" id="bk"' + (backOk ? "" : " disabled") + ">" + I("arrow-l") + '<span class="hide-sm">' + t("back") + '</span></button><button class="btn primary" id="nx"' + (nextDisabled ? " disabled" : "") + ">" + nextLabel + I("arrow-r") + "</button></div>"; }
  function flowStep() {
    var a = S.a, head = '<div class="page-head"><div><h1>' + t("flow_title") + "</h1></div></div>" + stepper(S.step);
    if (S.step === 0) {
      render(head + '<div class="layout even"><div class="mapbox"><div id="map" class="map" role="application" aria-label="map"></div>' + mapTools("lt") + "</div>" +
        '<div class="stack"><div class="card"><h3 style="margin-bottom:12px">' + t("q_location") + '</h3><button class="btn primary block" id="gps">' + I("locate") + t("use_gps") + '</button><div class="statusline" id="gpsmsg" style="margin-top:10px"></div><div id="loccard" style="margin-top:14px">' + locCard() + "</div></div>" +
        '<div class="card"><div class="field"><span>' + t("or_pick") + "</span>" + searchBox("q") + '</div><p class="tiny muted" style="margin-top:10px">' + t("tap_to_move") + "</p></div></div></div>" +
        actionbar(false, t("confirm_loc"), a.lat == null || (a.where && a.where.in_india === false)));
      var ctrl = null;
      makeMap({ el: "map", center: a.lat != null ? [a.lon, a.lat] : null, zoom: a.lat != null ? 12 : null, wards: "lines",
        onClick: function (ll) { setLoc(ll.lat, ll.lng, "map", null, ctrl, false); }, drag: function (ll) { setLoc(ll.lat, ll.lng, "map", null, ctrl, false); } })
        .then(function (c) { ctrl = c; bindTools("lt", c); if (a.lat != null) { c.pin(a.lat, a.lon, a.acc, false); if (a.where) c.select(a.where.district_heat && a.where.district_heat.id, a.where.ward && a.where.ward.ward_no); } })
        .catch(function () { mapFail("map"); });
      bindGps("gps", "gpsmsg", function () { return ctrl; });
      bindSearch("q", function (it) { setLoc(it.lat, it.lon, "search", null, ctrl, true); });
      if (a.lat != null && (!a.where || (!a.where.district_heat && a.where.in_india !== false))) refreshWhere();
    } else if (S.step === 1) {
      render(head + "<h2 style=\"margin-bottom:14px\">" + t("q_roof") + '</h2><div class="options">' + ["tin_top", "stone_slab_top", "rcc_brick_top", "lower_floor"].map(function (v) { return opt(v, ART(v), "roof_" + v, "roof_d_" + v, a.roof === v); }).join("") + "</div>" + actionbar(true, t("continue"), !a.roof));
      app.querySelectorAll(".opt").forEach(function (b) { b.onclick = function () { a.roof = b.getAttribute("data-v"); save(); S.step = 2; flowStep(); }; });
    } else if (S.step === 2) {
      var ppl = [["elderly", "elder", "p_elderly"], ["child", "baby", "p_child"], ["pregnant", "pregnant", "p_pregnant"], ["chronic", "heart", "p_chronic"], ["outdoor_worker", "hardhat", "p_outdoor_worker"], ["none", "smile", "p_none"]];
      render(head + "<h2 style=\"margin-bottom:14px\">" + t("q_people") + '</h2><div class="options three">' + ppl.map(function (o) { var on = o[0] === "none" ? a.vulnerable.length === 0 : a.vulnerable.indexOf(o[0]) >= 0; return opt(o[0], I(o[1]), o[2], null, on, true); }).join("") + "</div>" + actionbar(true, t("continue")));
      app.querySelectorAll(".opt").forEach(function (b) { b.onclick = function () { var v = b.getAttribute("data-v"); if (v === "none") a.vulnerable = []; else { var i = a.vulnerable.indexOf(v); if (i >= 0) a.vulnerable.splice(i, 1); else a.vulnerable.push(v); } save(); flowStep(); }; });
    } else {
      var d = a.devices, dev = [["fan", "fan", "d_fan"], ["cooler", "droplet", "d_cooler"], ["ac", "snow", "d_ac"], ["none", "ban", "d_none"]];
      render(head + "<h2 style=\"margin-bottom:14px\">" + t("q_cooling") + '</h2><div class="options">' + dev.map(function (o) { var on = o[0] === "none" ? !(d.fan || d.cooler || d.ac) : !!d[o[0]]; return opt(o[0], I(o[1]), o[2], null, on, true); }).join("") + "</div>" +
        (a.roof !== "lower_floor" ? '<div class="card" style="margin-top:18px"><div class="row between"><b>' + t("q_roof_access") + '</b><div class="seg lg" id="ra"><button data-ra="1" class="' + (a.roof_access ? "on" : "") + '">' + t("yes") + '</button><button data-ra="0" class="' + (!a.roof_access ? "on" : "") + '">' + t("no") + "</button></div></div></div>" : "") +
        actionbar(true, t("see_status")));
      app.querySelectorAll(".opt").forEach(function (b) { b.onclick = function () { var v = b.getAttribute("data-v"); if (v === "none") a.devices = {}; else a.devices[v] = !a.devices[v]; save(); flowStep(); }; });
      app.querySelectorAll("[data-ra]").forEach(function (b) { b.onclick = function () { a.roof_access = b.getAttribute("data-ra") === "1"; save(); flowStep(); }; });
    }
    $("bk").onclick = function () { S.step = Math.max(0, S.step - 1); flowStep(); };
    $("nx").onclick = function () {
      if (S.step === 0 && (a.lat == null || (a.where && a.where.in_india === false))) return;
      if (S.step === 1 && !a.roof) return;
      if (S.step < 3) { S.step++; flowStep(); } else submit();
    };
  }
  function submit() {
    render('<div class="page-head"><div><h1>' + t("flow_title") + '</h1></div></div><div class="card"><div class="row"><span class="spin"></span><span>' + t("loading") + "</span></div></div>" + skeletonCard(160) + "<br>" + skeletonCard(220));
    var a = S.a;
    api("/api/status/individual", { lat: a.lat, lon: a.lon, roof: a.roof, vulnerable: a.vulnerable, devices: { fan: !!a.devices.fan, cooler: !!a.devices.cooler, ac: !!a.devices.ac }, roof_access: a.roof_access, lang: S.lang })
      .then(function (r) { S.result = r; S.step = 9; try { localStorage.setItem("gc_last", JSON.stringify({ at: new Date().toISOString(), r: r })); } catch (e) {} resultView(); })
      .catch(function () {
        var last = null; try { last = JSON.parse(localStorage.getItem("gc_last")); } catch (e) {}
        if (last) { S.result = last.r; S.result._offline = last.at; S.step = 9; resultView(); }
        else render('<div class="callout warn">' + I("alert") + '<div>Network error. <button class="btn sm secondary" onclick="location.reload()">Retry</button></div></div>');
      });
  }

  /* ================= RESULT ================= */
  function gaugeSVG(idx) {
    var cx = 120, cy = 118, r = 92, cols = ["--low", "--mod", "--high", "--ext"], out = "";
    function pt(a) { var q = a * Math.PI / 180; return (cx + r * Math.cos(q)).toFixed(1) + " " + (cy - r * Math.sin(q)).toFixed(1); }
    for (var i = 0; i < 4; i++) out += '<path d="M' + pt(180 - i * 45 - 3) + " A" + r + " " + r + " 0 0 1 " + pt(180 - (i + 1) * 45 + 3) + '" style="stroke:var(' + cols[i] + ");opacity:" + (i === idx ? 1 : 0.22) + '" stroke-width="20" fill="none" stroke-linecap="round"/>';
    var q = (180 - (idx * 45 + 22.5)) * Math.PI / 180, nx = cx + (r - 36) * Math.cos(q), ny = cy - (r - 36) * Math.sin(q);
    return '<svg class="gauge" viewBox="0 0 240 132" role="img" aria-label="' + esc(t("level_" + LEVELS[idx])) + '">' + out + '<line x1="' + cx + '" y1="' + cy + '" x2="' + nx.toFixed(1) + '" y2="' + ny.toFixed(1) + '" style="stroke:var(--text)" stroke-width="5" stroke-linecap="round"/><circle cx="' + cx + '" cy="' + cy + '" r="9" style="fill:var(--text)"/></svg>';
  }
  function reasonText(r) { return t("reason_" + r.code, { v: Array.isArray(r.value) ? r.value.join(", ") : r.value, t: r.threshold }); }
  var SOL_IC = { night_ventilation: "moon", hydrate_shade: "droplet", cool_roof_coating: "roller", lime_whitewash: "brush", modroof: "layers", avoid_translucent_sheets: "ban", cooling_room: "snow", water_points: "tap", outdoor_work_hours: "clock", cool_roof_program: "building" };
  function whyChips(s) {
    return (s.why || []).map(function (w) {
      if (w === "free") return '<span class="badge low">' + I("check", "sm") + t("why_free") + "</span>";
      if (w.indexOf("roof:") === 0) return '<span class="badge primary">' + I("home", "sm") + t("why_roof") + ": " + esc(t("roof_" + w.slice(5))) + "</span>";
      if (w === "roof_access") return '<span class="badge primary">' + I("check", "sm") + t("why_roof_access") + "</span>";
      if (w === "avoid_harm") return '<span class="badge extreme">' + I("alert", "sm") + t("why_avoid_harm") + "</span>";
      if (w.indexOf("evidence:") === 0) return '<span class="badge info">' + I("shield", "sm") + t("ev_" + w.slice(9)) + "</span>";
      return "";
    }).join("");
  }
  function fixCard(s, avoid) {
    return '<details class="fix' + (avoid ? " avoid" : "") + '"><summary><span class="ic">' + I(SOL_IC[s.id] || "check") + '</span><div class="grow"><div class="t">' + esc(s.name) + (s.tier ? ' <span class="badge">' + t("tier_" + s.tier) + "</span>" : "") + '</div><div class="w">' + esc(s.what) + '</div><div class="badges why">' + whyChips(s) + "</div></div>" + I("chev-r", "chev") + "</summary>" +
      '<div class="body">' + (s.effect ? "<p><b>" + t("effect") + ":</b> " + esc(s.effect) + "</p>" : "") +
      (s.cost && s.cost !== "—" ? "<p><b>" + t("cost") + ":</b> " + esc(s.cost) + (s.cost_status && s.cost_status.indexOf("UNVERIFIED") === 0 ? " (" + t("not_verified") + ")" : "") + "</p>" : "") +
      (s.time && s.time !== "—" ? "<p><b>" + t("time") + ":</b> " + esc(s.time) + " · " + esc(s.who) + "</p>" : "") +
      '<p><a href="' + esc(s.source) + '" target="_blank" rel="noopener">' + t("source") + " " + I("link", "sm") + "</a></p></div></details>";
  }
  function fixesBlock(sol, sections) {
    var html = "", tiers = ["free", "low", "medium", "high"];
    var items = [].concat(sol.free || [], sol.cooling || []);
    if (sections.indexOf("health") >= 0) items = items.concat(sol.health || []);
    tiers.forEach(function (tr) { var g = items.filter(function (x) { return x.tier === tr; }); if (g.length) html += '<div class="tiergroup"><h4>' + t("tier_" + tr) + "</h4>" + g.map(function (x) { return fixCard(x); }).join("") + "</div>"; });
    var other = items.filter(function (x) { return tiers.indexOf(x.tier) < 0; });
    if (other.length) html += '<div class="tiergroup">' + other.map(function (x) { return fixCard(x); }).join("") + "</div>";
    if (sol.avoid && sol.avoid.length) html += '<div class="tiergroup"><h4>' + t("avoid") + "</h4>" + sol.avoid.map(function (x) { return fixCard(x, true); }).join("") + "</div>";
    if (sol.skipped && sol.skipped.length) html += '<details class="acc" style="margin-top:16px"><summary>' + I("eye-off") + t("skipped_title") + I("chev-r", "chev") + '</summary><div class="body"><ul class="skipped">' +
      sol.skipped.map(function (x) { return "<li>" + I(SOL_IC[x.id] || "x", "sm") + "<div><b>" + esc(x.name) + "</b> — " + t("skip_" + x.reason) + "</div></li>"; }).join("") + "</ul></div></details>";
    return html;
  }
  function planView(r) {
    var p = r.plan, hasIn = p.basis === "indoor", hot = {};
    (p.hottest || []).forEach(function (h) { hot[h] = 1; });
    var chips = "";
    if (hasIn) {
      if (p.open.length) chips += '<span class="planchip open">' + I("window", "sm") + t("plan_open", { r: ranges(p.open) }) + "</span>";
      if (p.close.length) chips += '<span class="planchip shut">' + I("curtain", "sm") + t("plan_close", { r: ranges(p.close) }) + "</span>";
    }
    if (p.fan_avoid.length) chips += '<span class="planchip bad">' + I("fan", "sm") + t("plan_fan_avoid", { r: ranges(p.fan_avoid) }) + "</span>";
    if (p.fan_not_enough.length) chips += '<span class="planchip warn">' + I("fan", "sm") + t("plan_fan_ne", { r: ranges(p.fan_not_enough) }) + "</span>";
    if (!p.fan_avoid.length && !p.fan_not_enough.length) chips += '<span class="planchip ok">' + I("fan", "sm") + t("plan_fan_ok") + "</span>";
    if (p.hottest.length) chips += '<span class="planchip hot">' + I("flame", "sm") + t(hasIn ? "plan_hottest" : "plan_hottest_out", { r: p.hottest.join(", ") }) + "</span>";
    var H = p.hours, row = function (label, cells) { return "<tr><th>" + label + "</th>" + cells + "</tr>"; };
    var grid = '<div class="hourgrid"><table>' +
      row("", H.map(function (h) { return '<td class="time">' + h.time.slice(11, 13) + "</td>"; }).join("")) +
      row(t("row_out"), H.map(function (h) { return "<td>" + fmt(h.outdoor, 0) + "</td>"; }).join("")) +
      (hasIn ? row(t("row_room"), H.map(function (h) { return '<td class="' + (hot[hm(h.time)] ? "hot" : "") + '">' + fmt(h.indoor, 0) + "</td>"; }).join("")) +
        row(t("row_window"), H.map(function (h) { return '<td class="w-' + h.window + '" title="' + esc(t("w_" + h.window)) + '">' + (h.window === "open" ? I("window", "sm") : h.window === "close" ? I("curtain", "sm") : "–") + "</td>"; }).join("")) : "") +
      row(t("row_fan"), H.map(function (h) { var c = h.fan === "fan_helps" ? "f-ok" : h.fan === "fan_not_enough_alone" ? "f-ne" : "f-avoid"; return '<td class="' + c + '" title="' + esc(t(h.fan)) + '">' + I("fan", "sm") + "</td>"; }).join("")) + "</table></div>";
    var leg = '<div class="legendrow">' + (hasIn ? '<span><i style="background:var(--primary-soft);border:1px solid var(--open)"></i>' + t("w_open") + '</span><span><i style="background:var(--surface-3)"></i>' + t("w_close") + "</span>" : "") +
      '<span><i style="background:var(--low-soft);border:1px solid var(--low)"></i>' + t("leg_helps") + '</span><span><i style="background:var(--mod-soft);border:1px solid var(--mod)"></i>' + t("leg_ne") + '</span><span><i style="background:var(--ext-soft);border:1px solid var(--ext)"></i>' + t("leg_avoid") + "</span></div>";
    return '<div class="planchips">' + chips + "</div>" + grid + leg + '<div class="callout ' + (hasIn ? "info" : "warn") + '" style="margin-top:14px">' + I(hasIn ? "info" : "alert") + "<div>" + t(hasIn ? "plan_note" : "plan_no_windows") + "</div></div>";
  }
  function chartSVG(hours, outdoor, fan) {
    var hasIn = hours && hours.length > 1;
    var src = hasIn ? hours : (outdoor || []).map(function (o) { return { time: o.time, outdoor: o.t }; });
    if (src.length < 2) return "";
    var narrow = window.innerWidth < 600, W = narrow ? 360 : 680, H = narrow ? 230 : 250, L = 34, R = 10, T = 20, B = 30, n = src.length, step = narrow ? 6 : 3;
    var vals = []; src.forEach(function (x) { vals.push(x.outdoor); if (hasIn) vals.push(x.low, x.high); });
    var lim = fan ? fan.limits_c : null; if (lim) vals.push(lim.not_enough_from);
    var lo = Math.floor(Math.min.apply(null, vals) - 1), hi = Math.ceil(Math.max.apply(null, vals) + 1);
    function X(i) { return L + (W - L - R) * i / (n - 1); } function Y(v) { return T + (H - T - B) * (hi - v) / (hi - lo); }
    var body = "";
    if (hasIn) {
      var band = src.map(function (x, i) { return X(i) + "," + Y(x.high); }).join(" ") + " " + src.slice().reverse().map(function (x, j) { return X(n - 1 - j) + "," + Y(x.low); }).join(" ");
      body += '<polygon points="' + band + '" style="fill:var(--high);opacity:.16"/><path d="' + src.map(function (x, i) { return (i ? "L" : "M") + X(i) + "," + Y(x.indoor); }).join(" ") + '" fill="none" style="stroke:var(--high)" stroke-width="3" stroke-linejoin="round"/>';
    }
    var grid = ""; for (var v = Math.ceil(lo / 2) * 2; v <= hi; v += 2) grid += '<line x1="' + L + '" x2="' + (W - R) + '" y1="' + Y(v) + '" y2="' + Y(v) + '" stroke="currentColor" opacity=".14"/><text x="' + (L - 6) + '" y="' + (Y(v) + 4) + '" font-size="12" text-anchor="end" fill="currentColor">' + v + "°</text>";
    var xl = ""; src.forEach(function (x, i) { if (i % step === 0) xl += '<text x="' + X(i) + '" y="' + (H - 10) + '" font-size="12" text-anchor="middle" fill="currentColor">' + x.time.slice(11, 16) + "</text>"; });
    var limLine = lim && lim.not_enough_from >= lo && lim.not_enough_from <= hi ? '<line x1="' + L + '" x2="' + (W - R) + '" y1="' + Y(lim.not_enough_from) + '" y2="' + Y(lim.not_enough_from) + '" style="stroke:var(--ext)" stroke-dasharray="6 5" stroke-width="2"/><text x="' + (W - R) + '" y="' + (Y(lim.not_enough_from) - 6) + '" font-size="12" text-anchor="end" style="fill:var(--ext)">' + esc(t("fan_line")) + " " + lim.not_enough_from + "°</text>" : "";
    return '<svg class="chart" viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="' + esc(t("chart_title")) + '">' + grid + xl + limLine + body +
      '<path d="' + src.map(function (x, i) { return (i ? "L" : "M") + X(i) + "," + Y(x.outdoor); }).join(" ") + '" fill="none" style="stroke:var(--info)" stroke-width="3" stroke-linejoin="round"/></svg>' +
      '<div class="legendrow"><span><i style="background:var(--info)"></i>' + t("outside") + "</span>" + (hasIn ? '<span><i style="background:var(--high)"></i>' + t("inside_range") + "</span>" : "") + '<span><i style="background:var(--ext)"></i>' + t("fan_line") + "</span></div>";
  }
  function districtCard(dh, mapId) {
    if (!dh) return "";
    return '<div class="card"><div class="card-h"><div class="ic">' + I("map") + "</div><h3>" + t("your_district") + ": " + esc(dh.district) + '</h3><span class="badge ' + classBadge(dh.hx_class) + '">' + esc(dh.hx_class) + "</span></div>" +
      (mapId ? '<div class="mapbox" style="margin-bottom:14px;box-shadow:none"><div class="map mini" id="' + mapId + '"></div></div>' : "") +
      '<div class="kpis"><div class="kpi"><div class="l">' + t("summer_tmax") + '</div><div class="v">' + fmt(dh.tmax_mean_c) + '<small>°C</small></div></div><div class="kpi"><div class="l">' + t("summer_tmin") + '</div><div class="v">' + fmt(dh.tmin_mean_c) + "<small>°C</small></div></div>" +
      '<div class="kpi"><div class="l">' + t("summer_twb") + '</div><div class="v">' + fmt(dh.twb_max_mean_c) + '<small>°C</small></div></div><div class="kpi"><div class="l">' + t("hot_days40") + '</div><div class="v">' + fmt(dh.days_tmax_ge40, 0) + "</div></div></div>" +
      '<div style="margin-top:10px"><div class="kv"><span>' + t("share65") + "</span><b>" + pct(dh.share_65plus) + '</b></div><div class="kv"><span>' + t("share_u5") + "</span><b>" + pct(dh.share_under5) + '</b></div><div class="kv"><span>' + t("pop_label") + "</span><b>" + inr(dh.pop_total) + '</b></div><div class="kv"><span>' + t("index_label") + "</span><b>" + t("index_rank", { r: Math.round(dh.hx_rank), n: dh.n_india || "" }) + "</b></div></div>" +
      '<p class="tiny muted" style="margin-top:8px">' + t("district_note") + "</p></div>";
  }
  function wardCard(w) {
    if (!w) return "";
    return card("building", t("delhi_ward_title") + " — " + esc(w.ward), '<div class="kpis"><div class="kpi"><div class="l">' + t("surface_heat") + '</div><div class="v">' + fmt(w.lst_day_c) + '<small>°C</small></div><div class="s">' + t("hotter_than", { p: Math.round((w.lst_day_pct || 0) * 100) }) + '</div></div><div class="kpi"><div class="l">' + t("night_ground") + '</div><div class="v">' + fmt(w.lst_night_c) + "<small>°C</small></div></div></div>" +
      (w.drivers && w.drivers.length ? '<p class="small" style="margin-top:12px"><b>' + t("why_hot") + ":</b> " + w.drivers.map(function (d) { return t("drv_" + d.code); }).join(" · ") + "</p>" : ""));
  }
  function sosCard() {
    return '<div class="card sos"><div class="card-h"><div class="ic">' + I("alert") + "</div><h3>" + t("signs") + "</h3></div><p><b>" + t("exhaustion") + ":</b> " + t("sx_ex") + "</p><p><b>" + t("stroke") + ":</b> " + t("sx_st") + "</p><p>" + t("cool_first") + '</p><div class="calls"><a href="tel:108">' + I("phone") + "108</a><a href=\"tel:112\">" + I("phone") + "112</a></div></div>";
  }
  function resultView() {
    var r = S.result, k = r.risk.level, w = r.weather, ind = r.indoor, fan = r.fan, p = r.place, a = S.a;
    var idx = Math.max(0, LEVELS.indexOf(k)), hasIn = ind.next24 && ind.next24.length > 0;
    var reasons = r.risk.reasons.map(function (x) { return '<li class="' + (x.raise ? "up" : "") + '">' + I(x.raise ? "arrow-up" : x.code === "no_household_raise_mild_heat" ? "info" : "thermo", "sm") + "<span>" + esc(reasonText(x)) + "</span></li>"; }).join("");
    var summary = '<div class="card summary"><div class="stack">' + placeBlock(p, a, null) + '<div class="row"><span class="badge">' + I("clock", "sm") + t("updated", { t: hm(w.fetched_at) }) + "</span>" + (r._offline ? '<span class="badge moderate">offline</span>' : "") + '</div><div class="row"><button class="btn secondary sm" id="chgloc">' + I("pin", "sm") + t("change_place") + '</button><button class="btn secondary sm" id="chg">' + I("edit", "sm") + t("change") + "</button></div></div>" +
      "<div>" + gaugeSVG(idx) + '<div class="level ' + k + '"><div class="tiny muted">' + t("level_title") + '</div><div class="name">' + t("level_" + k) + "</div></div></div>" +
      '<div><h3 style="margin-bottom:10px">' + t("reasons_title") + '</h3><ul class="reasons">' + reasons + "</ul></div></div>";
    var td = w.today || {}, tm = w.tomorrow || {};
    var kpis = '<div class="kpis" style="margin:16px 0 20px"><div class="kpi"><div class="l">' + I("sun", "sm") + t("today") + " · " + t("feels_max") + '</div><div class="v">' + fmt(td.hi_max, 0) + '<small>°C</small></div><div class="s">' + t("air_max") + " " + fmt(td.tmax, 0) + "° · " + t("wetbulb") + " " + fmt(td.twb_max, 0) + "°</div></div>" +
      '<div class="kpi"><div class="l">' + I("cloud", "sm") + t("tomorrow") + " · " + t("feels_max") + '</div><div class="v">' + fmt(tm.hi_max, 0) + '<small>°C</small></div><div class="s">' + t("air_max") + " " + fmt(tm.tmax, 0) + "° · " + t("wetbulb") + " " + fmt(tm.twb_max, 0) + "°</div></div>" +
      (hasIn && ind.peak ? '<div class="kpi"><div class="l">' + I("home", "sm") + t("room_peak") + " · " + hm(ind.peak.time) + '</div><div class="v">' + fmt(ind.peak.low, 0) + "–" + fmt(ind.peak.high, 0) + "<small>°C</small></div></div>" : "") +
      (hasIn && ind.night_min ? '<div class="kpi"><div class="l">' + I("moon", "sm") + t("room_night") + '</div><div class="v">' + fmt(ind.night_min.low, 0) + "–" + fmt(ind.night_min.high, 0) + "<small>°C</small></div></div>" : "") + "</div>";
    var note = ind.note_code === "outside_training_range" ? '<div class="callout warn" style="margin-top:12px">' + I("alert") + "<div>" + t("indoor_hidden", { t1: ind.applicability.trained_t_c[0], t2: ind.applicability.trained_t_c[1], h1: ind.applicability.trained_rh_pct[0], h2: ind.applicability.trained_rh_pct[1] }) + "</div></div>"
      : ind.note_code === "not_validated_here" ? '<div class="callout warn" style="margin-top:12px">' + I("info") + "<div>" + t("indoor_not_validated") + "</div></div>" : '<div class="callout" style="margin-top:12px">' + I("info") + "<div>" + t("indoor_note") + "</div></div>";
    var plan = '<div class="card"><div class="card-h"><div class="ic">' + I("clock") + "</div><h3>" + t("plan_title") + '</h3><div class="seg" id="ptabs"><button data-t="plan" class="' + (S.ptab === "plan" ? "on" : "") + '">' + t("tab_plan") + '</button><button data-t="temp" class="' + (S.ptab === "temp" ? "on" : "") + '">' + t("tab_temp") + '</button></div></div><div id="pbody"></div></div>';
    var fixes = card("list", t("fixes_title"), fixesBlock(r.solutions, ["free", "cooling", "avoid"]));
    var how = r.how || {};
    var howAcc = '<details class="acc"><summary>' + I("cpu") + t("how_short") + I("chev-r", "chev") + '</summary><div class="body">' +
      [["how_k_risk", "how_v_risk"], ["how_k_indoor", hasIn ? "how_v_indoor" : "how_v_indoor_off"], ["how_k_fan", fan.basis === "outdoor" ? "how_v_fan_out" : "how_v_fan"], ["how_k_windows", hasIn ? "how_v_windows" : "plan_no_windows"], ["how_k_fixes", "how_v_fixes"]]
        .map(function (x) { return '<div class="kv" style="display:block"><b style="display:block;text-align:left">' + t(x[0]) + '</b><span class="small muted">' + t(x[1]) + "</span></div>"; }).join("") +
      '<a class="btn ghost sm" href="#/how" style="margin-top:8px">' + t("read_more") + I("arrow-r", "sm") + "</a></div></details>";
    render(summary + kpis + '<div class="layout"><div class="stack">' + plan + fixes + '</div><div class="stack">' + districtCard(p.district_heat, "mmap") + wardCard(p.ward) + sosCard() + howAcc + "</div></div>");
    function paintPlan() { $("pbody").innerHTML = S.ptab === "plan" ? planView(r) : chartSVG(ind.next24, ind.outdoor24, fan) + note; }
    paintPlan();
    document.querySelectorAll("#ptabs button").forEach(function (b) { b.onclick = function () { S.ptab = b.getAttribute("data-t"); document.querySelectorAll("#ptabs button").forEach(function (x) { x.classList.toggle("on", x === b); }); paintPlan(); }; });
    $("chg").onclick = function () { S.step = 1; S.result = null; flowStep(); };
    $("chgloc").onclick = function () { S.step = 0; S.result = null; flowStep(); };
    if ($("mmap")) makeMap({ el: "mmap", center: [a.lon, a.lat], zoom: 8.5, wards: p.in_delhi ? "lines" : null })
      .then(function (c) { c.pin(a.lat, a.lon, a.acc, false); c.select(p.district_heat && p.district_heat.id, p.ward && p.ward.ward_no); }).catch(function () { mapFail("mmap"); });
  }

  /* ================= COLONY / SOCIETY ================= */
  function areaView() {
    var a = S.a;
    render('<div class="page-head"><div><h1>' + t("soc_title") + "</h1><p>" + t("pick_ward_tap") + '</p></div></div><div class="layout even"><div class="mapbox sticky-side"><div id="map" class="map"></div>' + mapTools("st") + "</div>" +
      '<div class="stack"><div class="card">' + searchBox("q") + '</div><div id="soc" class="stack"></div></div></div>');
    var ctrl = null;
    makeMap({ el: "map", center: a.lat != null ? [a.lon, a.lat] : null, zoom: a.lat != null ? 7.5 : null, wards: "lines", onClick: function (ll) { showArea(ll.lat, ll.lng, ctrl); } })
      .then(function (c) { ctrl = c; bindTools("st", c); if (a.lat != null) showArea(a.lat, a.lon, c); }).catch(function () { mapFail("map"); });
    bindSearch("q", function (it) { showArea(it.lat, it.lon, ctrl); });
    if (a.lat == null) $("soc").innerHTML = '<div class="callout">' + I("info") + "<div>" + t("pick_ward_tap") + "</div></div>";
  }
  function showArea(lat, lon, ctrl) {
    var box = $("soc"); box.innerHTML = skeletonCard(80) + skeletonCard(200);
    api("/api/area?lat=" + lat + "&lon=" + lon + "&lang=" + S.lang).then(function (d) {
      var wh = d.where, dh = d.district, e = d.coolroof_effect_c;
      if (ctrl) { ctrl.pin(lat, lon, null, true); ctrl.select(dh.id, wh.ward && wh.ward.ward_no); }
      box.innerHTML = '<div class="card">' + placeBlock(wh, null, null) + "</div>" + districtCard(dh) + wardCard(wh.ward) +
        card("rupee", t("calc_title"), '<div class="stack"><label class="field"><span>' + t("roof_area") + ' <b id="rav" class="num"></b></span><input type="range" id="ra" min="20" max="5000" step="10" value="500"></label>' +
          '<label class="field"><span>' + t("households") + ' <b id="hhv" class="num"></b></span><input type="range" id="hh" min="1" max="500" step="1" value="20"></label>' +
          '<div class="kpis"><div class="kpi"><div class="l">' + t("total_cost") + '</div><div class="v" id="ct"></div></div><div class="kpi"><div class="l">' + t("per_hh") + '</div><div class="v" id="cp"></div></div><div class="kpi"><div class="l">' + t("cooler_by") + '</div><div class="v">' + e.india_low + "–" + e.india_high + "<small>°C</small></div></div></div>" +
          '<p class="tiny muted">₹' + d.coolroof_cost_inr_per_m2 + "/m² · " + esc(d.sources[0].status) + " · " + esc(d.sources[1].status) + "</p></div>") +
        card("list", t("fixes_title"), fixesBlock(d.solutions, ["free", "cooling", "health", "avoid"])) + '<p class="tiny muted">' + t("index_note") + "</p>";
      function calc() { var ra = +$("ra").value, hh = +$("hh").value, c = ra * d.coolroof_cost_inr_per_m2; $("rav").textContent = inr(ra) + " m²"; $("hhv").textContent = hh; $("ct").textContent = "₹" + inr(c); $("cp").textContent = "₹" + inr(c / hh); }
      $("ra").oninput = calc; $("hh").oninput = calc; calc();
    }).catch(function () { box.innerHTML = '<div class="callout warn">' + I("alert") + "<div>" + t("outside_india") + "</div></div>"; });
  }

  /* ================= GOVERNMENT ================= */
  function csvDownload(name, rows) {
    var blob = new Blob(["﻿" + rows.map(function (r) { return r.map(function (x) { return '"' + String(x == null ? "" : x).replace(/"/g, '""') + '"'; }).join(","); }).join("\n")], { type: "text/csv" });
    var a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = name; a.click();
  }
  var GOV_DATA = {};
  function govView() {
    var india = S.gscope !== "delhi", key = india ? "india|" + S.gstate : "delhi";
    var head = '<div class="page-head"><div><h1>' + t("gov_title") + "</h1><p>" + t("government_sub") + '</p></div><div class="seg lg" id="scope"><button data-scope="india" class="' + (india ? "on" : "") + '">' + I("map", "sm") + t("scope_india") + '</button><button data-scope="delhi" class="' + (!india ? "on" : "") + '">' + I("building", "sm") + t("scope_delhi") + "</button></div></div>";
    if (!GOV_DATA[key]) {
      render(head + skeletonCard(60) + "<br>" + skeletonCard(380));
      bindScope();
      var q = india ? "/api/gov/rank?scope=india&limit=800&lang=" + S.lang + (S.gstate ? "&state=" + encodeURIComponent(S.gstate) : "") : "/api/gov/rank?scope=delhi&limit=300&lang=" + S.lang;
      api(q).then(function (d) { GOV_DATA[key] = d; govView(); }).catch(function () { render(head + '<div class="callout warn">' + I("alert") + "<div>Could not load data.</div></div>"); bindScope(); });
      return;
    }
    var d = GOV_DATA[key], rows = india ? d.districts : d.wards;
    var cols = india ? [["hx_rank", "#", 1], ["district", t("col_district")], ["hx_index", t("col_index"), 1], ["tmax_mean_c", t("col_tmax"), 1], ["tmin_mean_c", t("col_tmin"), 1], ["twb_max_mean_c", t("col_twb"), 1], ["days_tmax_ge40", t("col_hot40"), 1], ["share_65plus", t("col_65"), 1], ["pop_total", t("col_pop"), 1]]
      : [["hvi_rank", "#", 1], ["ward_name", t("ward")], ["hvi", "HVI", 1], ["lst_day_mean_c", t("day"), 1], ["lst_night_mean_c", t("night"), 1], ["frac_tree", t("trees"), 1], ["pop_65plus", t("elderly65"), 1], ["drivers", t("drivers")]];
    var vh = india ? rows.filter(function (x) { return x.hx_class === "Very high"; }) : [];
    var kpis = india ? '<div class="kpis" style="margin-bottom:16px"><div class="kpi"><div class="l">' + I("map", "sm") + t("kpi_shown") + '</div><div class="v">' + rows.length + '</div></div><div class="kpi"><div class="l">' + I("flame", "sm") + t("kpi_vh") + '</div><div class="v">' + vh.length + '</div></div><div class="kpi"><div class="l">' + I("users", "sm") + t("kpi_people_vh") + '</div><div class="v">' + inr(vh.reduce(function (s, x) { return s + (x.pop_total || 0); }, 0)) + '</div></div><div class="kpi"><div class="l">' + I("sun", "sm") + t("kpi_mean_tmax") + '</div><div class="v">' + fmt(rows.reduce(function (s, x) { return s + x.tmax_mean_c; }, 0) / Math.max(rows.length, 1)) + "<small>°C</small></div></div></div>" : "";
    var tools = '<div class="toolbar">' + (india ? '<select class="input" id="st" style="max-width:260px"><option value="">' + t("state_all") + "</option>" + d.states.map(function (x) { return "<option" + (x === S.gstate ? " selected" : "") + ">" + esc(x) + "</option>"; }).join("") + "</select>" : "") +
      '<div class="search">' + I("search") + '<input class="input" id="gf" type="search" placeholder="' + esc(t("filter_ph")) + '" value="' + esc(S.gfilter) + '"></div><button class="btn secondary" id="csv">' + I("download") + t("download_csv") + "</button></div>";
    render(head + kpis + tools + '<div class="mapbox" style="margin-bottom:20px"><div id="map" class="map"></div>' + (india ? mapTools("gt") : legend(WARD_STOPS, "", "layer_index", 2)) + "</div>" +
      '<div class="card" style="padding:0;overflow:hidden"><div style="padding:16px 20px 8px" class="row between"><h3>' + t("rank_label") + '</h3><span class="tiny muted">' + t("sort_hint") + '</span></div><div id="tbl"></div></div>' +
      '<div class="layout" style="margin-top:20px"><div>' + card("list", t("todo"), fixesBlock(d.solutions, ["cooling", "health", "avoid"])) + '</div><div class="stack">' +
      card("book", t("schemes"), '<ul class="bullets"><li><a target="_blank" rel="noopener" href="https://ndma.gov.in/sites/default/files/PDF/Guidelines/Heatwaveguidelines.pdf">NDMA Guidelines for Heat Wave Action Plans (2019)</a></li><li><a target="_blank" rel="noopener" href="https://ncdc.mohfw.gov.in/uploads/pdf/4.%20Heat%20wave%20advisory%20for%20State%20Health%20department_2026.pdf">NCDC heat-wave advisory for State Health Departments (2026)</a></li><li><a target="_blank" rel="noopener" href="https://www.downtoearth.org.in/climate-change/india-updates-disaster-list-to-include-heatwaves-and-lightning-after-finance-commission-push">Heatwaves notified as a natural calamity (Aug 2026), reported</a></li></ul>') +
      card("info", t("notes"), '<ul class="bullets small">' + (d.notes || []).map(function (n) { return "<li>" + esc(n) + "</li>"; }).join("") + (india && d.checks && d.checks.spearman_equal_vs_pca != null ? "<li>Equal vs PCA weights: Spearman " + d.checks.spearman_equal_vs_pca + "</li>" : "") + "</ul>") + "</div></div>");
    bindScope();
    function table() {
      var f = S.gfilter.trim().toLowerCase(), nameKey = india ? "district" : "ward_name";
      var list = rows.filter(function (x) { return !f || String(x[nameKey]).toLowerCase().indexOf(f) >= 0 || String(x.state || x.district || "").toLowerCase().indexOf(f) >= 0; });
      var s = S.gsort && S.gsort.scope === key ? S.gsort : { k: india ? "hx_rank" : "hvi_rank", dir: 1 };
      list = list.slice().sort(function (p, q) { var x = p[s.k], y = q[s.k]; if (typeof x === "string") return s.dir * String(x).localeCompare(String(y)); return s.dir * ((x == null ? -1e9 : x) - (y == null ? -1e9 : y)); });
      var shown = list.slice(0, S.glimit);
      var cell = function (x, c) {
        var v = x[c[0]];
        if (c[0] === "hx_rank" || c[0] === "hvi_rank") return '<td class="num"><span class="rankpill">' + Math.round(v) + "</span></td>";
        if (c[0] === "district") return "<td><b>" + esc(v) + '</b><div class="tiny muted">' + esc(x.state) + "</div></td>";
        if (c[0] === "ward_name") return "<td><b>" + esc(title(v)) + '</b><div class="tiny muted">' + esc(x.district) + "</div></td>";
        if (c[0] === "hx_index" || c[0] === "hvi") { var cls = india ? classBadge(x.hx_class) : (v > WARD_STOPS[4] ? "extreme" : v > WARD_STOPS[2] ? "high" : v > WARD_STOPS[0] ? "moderate" : "low"); return '<td class="num"><span class="meterbar"><i style="width:' + Math.round(v * 100) + "%;background:var(--" + ({ low: "low", moderate: "mod", high: "high", extreme: "ext" }[cls] || "muted") + ')"></i></span>' + fmt(v, 2) + "</td>"; }
        if (c[0] === "share_65plus" || c[0] === "frac_tree") return '<td class="num">' + pct(v) + "</td>";
        if (c[0] === "pop_total" || c[0] === "pop_65plus") return '<td class="num">' + inr(v) + "</td>";
        if (c[0] === "days_tmax_ge40") return '<td class="num">' + fmt(v, 0) + "</td>";
        if (c[0] === "drivers") return '<td class="tiny">' + (v || []).map(function (z) { return t("drv_" + z.code); }).join("; ") + "</td>";
        return '<td class="num">' + fmt(v) + "</td>";
      };
      $("tbl").innerHTML = '<div class="tablewrap" style="border:0;border-radius:0"><table class="data"><thead><tr>' + cols.map(function (c) { return '<th data-k="' + c[0] + '" class="' + (c[2] ? "num " : "") + (s.k === c[0] ? "sorted" : "") + '">' + c[1] + " " + I(s.k === c[0] ? (s.dir > 0 ? "arrow-up" : "sort") : "sort", "sm") + "</th>"; }).join("") + "</tr></thead><tbody>" +
        shown.map(function (x) { return "<tr>" + cols.map(function (c) { return cell(x, c); }).join("") + "</tr>"; }).join("") + "</tbody></table></div>" +
        (list.length > shown.length ? '<div style="padding:14px 20px"><button class="btn secondary sm" id="more">' + t("show_more") + " (" + (list.length - shown.length) + ")</button></div>" : "");
      document.querySelectorAll("#tbl th").forEach(function (th) { th.onclick = function () { var k2 = th.getAttribute("data-k"); S.gsort = { scope: key, k: k2, dir: s.k === k2 ? -s.dir : 1 }; table(); }; });
      if ($("more")) $("more").onclick = function () { S.glimit += 100; table(); };
    }
    table();
    $("gf").oninput = function (e) { S.gfilter = e.target.value; S.glimit = 60; table(); };
    if (india) $("st").onchange = function (e) { S.gstate = e.target.value; S.glimit = 60; govView(); };
    $("csv").onclick = function () {
      if (india) csvDownload("india_district_heat_priorities.csv", [["rank", "district", "state", "index", "class", "summer_tmax_c", "summer_tmin_c", "wetbulb_max_c", "days_ge40", "share_65plus", "share_under5", "population_2025"]].concat(rows.map(function (x) { return [Math.round(x.hx_rank), x.district, x.state, x.hx_index, x.hx_class, x.tmax_mean_c, x.tmin_mean_c, x.twb_max_mean_c, x.days_tmax_ge40, x.share_65plus, x.share_under5, x.pop_total]; })));
      else csvDownload("delhi_ward_heat_priorities.csv", [["rank", "ward", "district", "hvi", "lst_day", "lst_night", "tree_frac", "pop_65plus"]].concat(rows.map(function (w) { return [w.hvi_rank, w.ward_name, w.district, w.hvi, w.lst_day_mean_c, w.lst_night_mean_c, w.frac_tree, w.pop_65plus]; })));
    };
    var ctrl = null, first = india && S.gstate && rows[0] ? rows[0] : null;
    makeMap({ el: "map", center: india ? (first ? [first.lon, first.lat] : null) : DELHI.center, zoom: india ? (first ? 5.8 : null) : DELHI.zoom, wards: india ? null : "fill",
      onClick: function (ll, dp, wp) {
        if (!ctrl) return;
        var pop = !india && wp ? "<b>" + esc(title(wp.ward_name)) + "</b><br>" + esc(wp.district) + "<br>HVI " + fmt(wp.hvi, 2) + " · " + esc(wp.hvi_class) + "<br>" + t("day") + " " + fmt(wp.lst_day_mean_c) + " · " + t("night") + " " + fmt(wp.lst_night_mean_c)
          : dp && dp.hx_index != null ? "<b>" + esc(dp.district) + "</b><br>" + esc(dp.state || "") + "<br>" + t("index_label") + " " + fmt(dp.hx_index, 2) + " · " + esc(dp.hx_class) + " (#" + Math.round(dp.hx_rank) + ")<br>" + t("col_tmax") + " " + fmt(dp.tmax_mean_c) + " °C · " + t("col_tmin") + " " + fmt(dp.tmin_mean_c) + " °C<br>" + t("col_twb") + " " + fmt(dp.twb_max_mean_c) + " °C · " + t("col_65") + " " + pct(dp.share_65plus) : null;
        if (!pop) return;
        ctrl.select(dp && dp.id, wp && wp.ward_no);
        new maplibregl.Popup({ closeButton: true }).setLngLat(ll).setHTML(pop).addTo(ctrl.map);
      } }).then(function (c) { ctrl = c; if (india) bindTools("gt", c); }).catch(function () { mapFail("map"); });
  }
  function bindScope() { document.querySelectorAll("#scope button").forEach(function (b) { b.onclick = function () { S.gscope = b.getAttribute("data-scope"); S.gfilter = ""; S.glimit = 60; govView(); }; }); }

  /* ================= HOW IT WORKS ================= */
  function howView() {
    render('<div class="page-head"><div><span class="eyebrow">' + I("cpu", "sm") + t("nav_how") + "</span><h1>" + t("how_title") + "</h1><p>" + t("how_sub") + "</p></div></div>" + pipeline("pipeline") +
      '<section class="section"><h2>' + t("models_title") + '</h2><div class="grid g3" id="models">' + skeletonCard(160) + skeletonCard(160) + skeletonCard(160) + "</div></section>" +
      '<section class="section"><div class="grid g2">' + card("list", t("pick_title"), '<ol class="flow">' + [1, 2, 3, 4, 5].map(function (i) { return "<li>" + t("pick_" + i) + "</li>"; }).join("") + "</ol>") +
      '<div class="stack">' + card("shield", t("why_rules_title"), '<p class="muted">' + t("why_rules_d") + "</p>") + card("sparkles", t("ai_title"), '<p class="muted">' + t("ai_d") + "</p>") + "</div></div></section>" +
      '<section class="section">' + card("info", t("limits_title"), '<ul class="bullets">' + [1, 2, 3, 4].map(function (i) { return "<li>" + t("lim_" + i) + "</li>"; }).join("") + '</ul><a class="btn ghost sm" style="margin-top:12px" href="#/sources">' + t("open_sources") + I("arrow-r", "sm") + "</a>") + "</section>");
    api("/api/about").then(function (d) {
      var m = function (v, l) { return '<div class="metric"><b>' + v + "</b><span>" + l + "</span></div>"; };
      $("models").innerHTML = card("home", t("m1_t"), '<p class="muted small">' + t("m1_d") + '</p><div class="metrics">' + m("±" + fmt(d.indoor.mae_c), t("m1_a")) + (d.indoor.rule_mae_c ? m("±" + fmt(d.indoor.rule_mae_c), t("m1_b")) : "") + m(d.indoor.homes, t("m1_c")) + "</div>") +
        card("map", t("m2_t"), '<p class="muted small">' + t("m2_d") + '</p><div class="metrics">' + m(d.districts.n, t("m2_a")) + m(fmt(d.districts.spearman_equal_vs_pca, 2), t("m2_b")) + m((d.districts.years || []).length, t("m2_c")) + "</div>") +
        card("building", t("m3_t"), '<p class="muted small">' + t("m3_d") + '</p><div class="metrics">' + m(fmt(d.wards.r2, 2), t("m3_a")) + m(d.wards.n_wards, t("m3_b")) + "</div>");
    }).catch(function () { $("models").innerHTML = ""; });
  }

  /* ================= SOURCES ================= */
  function sourcesView() {
    render('<div class="page-head"><div><h1>' + t("sources_title") + "</h1><p>" + t("trust_sourced") + "</p></div></div>" + skeletonCard(300));
    api("/api/sources").then(function (d) {
      var badge = function (st) { var s = String(st || ""); var c = /^Verified|^Done|^Computed/.test(s) ? "low" : /UNVERIFIED|DISPUTED/.test(s) ? "extreme" : /Reported|To verify/.test(s) ? "moderate" : ""; return '<span class="badge ' + c + '">' + esc(s.length > 48 ? s.slice(0, 46) + "…" : s) + "</span>"; };
      render('<div class="page-head"><div><h1>' + t("sources_title") + "</h1><p>" + t("trust_sourced") + "</p></div></div>" +
        '<div class="card" style="padding:0;overflow:hidden"><div class="tablewrap" style="border:0;border-radius:0"><table class="data"><thead><tr><th>ID</th><th>Source</th><th>Used for</th><th>Year</th><th>Licence</th><th>Status</th></tr></thead><tbody>' +
        d.sources.map(function (s) { var u = (String(s.url).match(/https?:\/\/[^\s;]+/) || [""])[0]; return '<tr><td><span class="rankpill">' + esc(s.id) + "</span></td><td><b>" + esc(s.source) + "</b>" + (u ? '<div class="tiny"><a target="_blank" rel="noopener" href="' + esc(u) + '">' + I("link", "sm") + " link</a></div>" : "") + "</td><td class=\"small\">" + esc(s.used_for) + "</td><td>" + esc(s.year) + '</td><td class="small">' + esc(s.licence) + "</td><td>" + badge(s.status) + "</td></tr>"; }).join("") + "</tbody></table></div></div>" +
        '<section class="section"><h2>Verified numbers</h2><p class="muted" style="margin:-6px 0 14px">verified_numbers.csv — every threshold and effect the app uses.</p><div class="card" style="padding:0;overflow:hidden"><div class="tablewrap" style="border:0;border-radius:0"><table class="data"><thead><tr><th>Key</th><th>' + t("status_label") + "</th><th>Source</th></tr></thead><tbody>" +
        d.verified_numbers.map(function (v) { return '<tr><td class="small"><code>' + esc(v.key) + "</code></td><td>" + badge(v.status) + '</td><td class="small">' + esc(v.source) + "</td></tr>"; }).join("") + "</tbody></table></div></div></section>");
    });
  }

  go();
})();
