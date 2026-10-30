/* API client: one place for the server address, timeouts and caching.
   - identical GET requests made at the same time share one network call
   - small GET answers (place names, search, weather) are kept for a few minutes so moving between screens is instant
   - a request that hangs on a weak mobile connection is abandoned after TIMEOUT instead of spinning forever
   - if the server can't be reached at all, screens get a bundled sample (Delhi, a recorded heatwave day) marked with
     _sample, so the app still shows something; samples are never cached, so live answers replace them on the next try */
import { API_BASE } from "./config.js";

var TIMEOUT = 20000, TTL = 5 * 60 * 1000, MAX = 80;
var cache = new Map(), inflight = new Map();

var onSample = null;
export function whenSample(fn) { onSample = fn; }

export function api(path, body) {
  return live(path, body).then(function (v) {
    if (onSample && path.indexOf("/api/") === 0) onSample(null);  // the server answers again
    return v;
  }, function (e) {
    var file = e.unreachable && sampleFile(path, body);
    if (!file) throw e;
    return sample(file, path).catch(function () { throw e; });
  });
}

function live(path, body) {
  var url = /^https?:|^data\//.test(path) ? path : API_BASE + path;
  if (body) return request(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  var hit = cache.get(url);
  if (hit && Date.now() - hit.at < TTL) return Promise.resolve(hit.v);
  if (inflight.has(url)) return inflight.get(url);
  var p = request(url, {}).then(function (v) {
    inflight.delete(url);
    if (!/geojson$/.test(url)) {  // the map layers are cached by the map code; keep this cache small
      cache.set(url, { at: Date.now(), v: v });
      if (cache.size > MAX) cache.delete(cache.keys().next().value);
    }
    return v;
  }, function (e) { inflight.delete(url); throw e; });
  inflight.set(url, p);
  return p;
}

function request(url, opt) {
  var ctl = typeof AbortController !== "undefined" ? new AbortController() : null, timer = null;
  if (ctl) { opt.signal = ctl.signal; timer = setTimeout(function () { ctl.abort(); }, TIMEOUT); }
  return fetch(url, opt).then(function (r) {
    clearTimeout(timer);
    if (!r.ok) throw failure(r.status, r.status >= 500);
    return r.json();
  }, function () { clearTimeout(timer); throw failure(0, true); });
}

function failure(status, unreachable) {
  var e = new Error(String(status));
  e.status = status;
  e.unreachable = unreachable;  // no answer or a server error; a 4xx is our own mistake and must surface
  return e;
}

/* ---------- bundled sample (scripts/build_sample_data.py) ---------- */
var ROOFS = ["tin_top", "asbestos_top", "stone_slab_top", "rcc_brick_top", "lower_floor"];
function param(path, k) { var m = path.match(new RegExp("[?&]" + k + "=([^&]*)")); return m ? decodeURIComponent(m[1]) : ""; }
function sampleFile(path, body) {
  var lang = (body && body.lang) || param(path, "lang");
  lang = lang === "hi" ? "hi" : "en";
  var route = path.split("?")[0];
  if (route === "/api/status/individual") return "individual_" + (body && ROOFS.indexOf(body.roof) >= 0 ? body.roof : "rcc_brick_top") + "_" + lang;
  if (route === "/api/gov/rank") return "rank_" + (param(path, "scope") === "delhi" ? "delhi" : "india") + "_" + lang;
  if (route === "/api/area") return "area_" + lang;
  return { "/api/where": "where", "/api/weather": "weather", "/api/outdoor": "outdoor", "/api/about": "about" }[route] || null;
}
function sample(file, path) {
  return Promise.all([request("sample/" + file + ".json", {}), request("sample/meta.json", {})]).then(function (x) {
    var d = x[0], state = param(path, "state");
    if (state && d.districts) d.districts = d.districts.filter(function (r) { return r.state === state; });
    d._sample = x[1];
    if (onSample) onSample(x[1]);
    return d;
  });
}
