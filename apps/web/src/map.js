/* MapLibre maps. The library (~1 MB) is bundled as its own chunk and loaded only when a map is first on screen, so the
   home screen stays small and maps still work offline in the app (no CDN). */
import { t } from "./i18n/index.js";
import { I } from "./icons.js";
import { fmt, cssVar, $ } from "./util.js";
import { S } from "./state.js";
import { api } from "./api.js";
import { GEO, TILE_URL } from "./config.js";

/* India-wide view draws only our district polygons (official LGD outline); OpenStreetMap tiles appear from BASE_MINZOOM. */
var INDIA_FIT = [[68.1, 6.7], [97.4, 37.1]], BOUNDS = [[60, 2], [104, 40]], BASE_MINZOOM = 7;
export var DELHI = { center: [77.12, 28.62], zoom: 9.6 };
/* colour stops = 10/30/50/70/90th percentile across Indian districts (data/india_district_stats.csv) */
export var LAYERS = {
  hx_index: { key: "layer_index", stops: [0.1, 0.3, 0.5, 0.7, 0.9], unit: "", d: 1 },
  tmax_mean_c: { key: "layer_tmax", stops: [27.4, 33.4, 36.0, 37.2, 38.5], unit: " °C", d: 1 },
  tmin_mean_c: { key: "layer_tmin", stops: [18.7, 23.1, 24.6, 25.4, 26.2], unit: " °C", d: 1 },
  twb_max_mean_c: { key: "layer_twb", stops: [21.1, 22.8, 23.8, 24.9, 26.2], unit: " °C", d: 1 }
};
export var WARD_STOPS = [0.29, 0.49, 0.59, 0.67, 0.79];
function heatRamp() { return [1, 2, 3, 4, 5].map(function (i) { return cssVar("--heat-" + i); }); }  // map colours live in styles.css

var maps = [], lib = null, geoD = null, geoW = null;
if (import.meta.env.VITE_DEBUG) window.__maps = maps;  // on-device debugging only (set in .env.app.local)
function distGeo() { if (!geoD) geoD = api(GEO.districts).catch(function (e) { geoD = null; throw e; }); return geoD; }
function wardGeo() { if (!geoW) geoW = api(GEO.wards).catch(function (e) { geoW = null; throw e; }); return geoW; }
export function destroyMaps() { maps.forEach(function (m) { try { m.remove(); } catch (e) {} }); maps.length = 0; }
export function loadLib() {
  if (!lib) lib = Promise.all([import("maplibre-gl"), import("maplibre-gl/dist/maplibre-gl-worker.mjs?url"), import("maplibre-gl/dist/maplibre-gl.css")])
    .then(function (m) { m[0].setWorkerUrl(m[1].default); return m[0]; }, function (e) { lib = null; throw e; });
  return lib;
}
/* start fetching the library and outlines in the background (e.g. while the user reads the first screen) */
export function warmMaps() { loadLib().catch(function () {}); distGeo().catch(function () {}); }

function ramp(prop, st) { var e = ["interpolate", ["linear"], ["to-number", ["get", prop]]], H = heatRamp(); st.forEach(function (v, i) { e.push(v, H[i]); }); return e; }
function distFill(layer) { return ["case", ["==", ["typeof", ["get", layer]], "number"], ramp(layer, LAYERS[layer].stops), cssVar("--surface")]; }
function circle(lon, lat, r) {
  var pts = [], k = 48, dx = r / (111320 * Math.cos(lat * Math.PI / 180)), dy = r / 110574;
  for (var i = 0; i <= k; i++) { var a = 2 * Math.PI * i / k; pts.push([lon + dx * Math.cos(a), lat + dy * Math.sin(a)]); }
  return { type: "Feature", geometry: { type: "Polygon", coordinates: [pts] } };
}
export function popup(ctrl, ll, html) { new ctrl.lib.Popup({ closeButton: true }).setLngLat(ll).setHTML(html).addTo(ctrl.map); }

/* opts: {el, center, zoom, wards: "lines"|"fill"|null, onClick(lngLat, districtProps, wardProps), drag(lngLat)} -> Promise(ctrl) */
export function makeMap(opts) {
  distGeo().catch(function () {});
  if (opts.wards) wardGeo().catch(function () {});
  return loadLib().then(function (ml) {
    if (!$(opts.el)) throw new Error("gone");  // the user left the page while the library loaded
    var m = new ml.Map({ container: opts.el, center: opts.center || [80.5, 22.6], zoom: opts.zoom || 4, minZoom: 3, maxZoom: 17, maxBounds: BOUNDS,
      attributionControl: { compact: true }, dragRotate: false, pitchWithRotate: false, fadeDuration: 0,
      style: { version: 8, sources: { osm: { type: "raster", tiles: [TILE_URL], tileSize: 256, maxzoom: 19,
        attribution: '© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors' } },
        layers: [{ id: "bg", type: "background", paint: { "background-color": cssVar("--line") } }, { id: "osm", type: "raster", source: "osm", minzoom: BASE_MINZOOM }] } });
    maps.push(m);
    if (!opts.center) m.fitBounds(INDIA_FIT, { padding: 16, duration: 0 });
    m.addControl(new ml.NavigationControl({ showCompass: false }), "top-right");
    m.touchZoomRotate.disableRotation();
    var ctrl = { map: m, lib: ml, marker: null };
    ctrl.ready = new Promise(function (res) {
      m.on("load", function () {
        var empty = { type: "FeatureCollection", features: [] };
        m.addSource("d", { type: "geojson", data: empty });
        m.addLayer({ id: "df", type: "fill", source: "d", paint: { "fill-color": distFill(S.layer), "fill-opacity": ["interpolate", ["linear"], ["zoom"], 4, 0.9, 7, 0.6, 11, 0.32, 14, 0.12] } });
        m.addLayer({ id: "dl", type: "line", source: "d", paint: { "line-color": cssVar("--ink-muted"), "line-opacity": 0.55, "line-width": ["interpolate", ["linear"], ["zoom"], 4, 0.25, 9, 0.9] } });
        m.addLayer({ id: "dsel", type: "line", source: "d", filter: ["==", ["get", "id"], "__none__"], paint: { "line-color": cssVar("--primary"), "line-width": 3.5 } });
        distGeo().then(function (g) { if (m.getSource("d")) m.getSource("d").setData(g); }).catch(function () {});
        if (opts.wards) {
          m.addSource("w", { type: "geojson", data: empty });
          if (opts.wards === "fill") m.addLayer({ id: "wf", type: "fill", source: "w", paint: { "fill-color": ramp("hvi", WARD_STOPS), "fill-opacity": 0.6 } });
          m.addLayer({ id: "wl", type: "line", source: "w", minzoom: 9, paint: { "line-color": cssVar("--ink"), "line-opacity": 0.6, "line-width": 0.6 } });
          m.addLayer({ id: "wsel", type: "line", source: "w", filter: ["==", ["get", "ward_no"], "__none__"], paint: { "line-color": cssVar("--primary"), "line-width": 3 } });
          wardGeo().then(function (g) { if (m.getSource("w")) m.getSource("w").setData(g); }).catch(function () {});
        }
        m.addSource("acc", { type: "geojson", data: empty });
        m.addLayer({ id: "accf", type: "fill", source: "acc", paint: { "fill-color": cssVar("--primary"), "fill-opacity": 0.12 } });
        m.addLayer({ id: "accl", type: "line", source: "acc", paint: { "line-color": cssVar("--primary"), "line-width": 1.5 } });
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
        ctrl.marker = new ml.Marker({ color: cssVar("--accent"), draggable: !!opts.drag }).setLngLat([lon, lat]).addTo(m);
        if (opts.drag) ctrl.marker.on("dragend", function () { opts.drag(ctrl.marker.getLngLat()); });
      } else ctrl.marker.setLngLat([lon, lat]);
      m.getSource("acc").setData({ type: "FeatureCollection", features: acc ? [circle(lon, lat, Math.min(acc, 20000))] : [] });
      if (fly !== false) m.flyTo({ center: [lon, lat], zoom: Math.max(m.getZoom(), acc > 3000 ? 10 : 13), speed: 1.6 });
    }); };
    return ctrl;
  });
}
export function legend(stops, unit, labelKey, d) { return '<div class="legend"><b>' + t(labelKey) + '</b><div class="bar"></div><div class="ends"><span>' + t("lower") + " ≤" + fmt(stops[0], d) + unit + "</span><span>" + t("higher") + " ≥" + fmt(stops[4], d) + unit + "</span></div></div>"; }
export function mapTools(id) {
  var L = LAYERS[S.layer];
  return '<div class="maptools"><div class="seg" id="' + id + '">' + Object.keys(LAYERS).map(function (k) { return '<button type="button" data-layer="' + k + '" class="' + (k === S.layer ? "on" : "") + '">' + t(LAYERS[k].key) + "</button>"; }).join("") + "</div></div>" +
    '<div id="' + id + '_lg">' + legend(L.stops, L.unit, L.key, L.d) + "</div>";
}
export function bindTools(id, ctrl) {
  document.querySelectorAll("#" + id + " button").forEach(function (b) { b.onclick = function () {
    S.layer = b.getAttribute("data-layer");
    var L = LAYERS[S.layer];
    document.querySelectorAll("#" + id + " button").forEach(function (x) { x.classList.toggle("on", x === b); });
    $(id + "_lg").innerHTML = legend(L.stops, L.unit, L.key, L.d);
    ctrl.setLayer(S.layer);
  }; });
}
export function mapFail(el) { var n = $(el); if (n) n.outerHTML = '<div class="callout">' + I("info") + "<div>" + t("map_fail") + "</div></div>"; }
