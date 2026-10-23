/* API client: one place for the server address, timeouts and caching.
   - identical GET requests made at the same time share one network call
   - small GET answers (place names, search, weather) are kept for a few minutes so moving between screens is instant
   - a request that hangs on a weak mobile connection is abandoned after TIMEOUT instead of spinning forever */
import { API_BASE } from "./config.js";

var TIMEOUT = 20000, TTL = 5 * 60 * 1000, MAX = 80;
var cache = new Map(), inflight = new Map();

export function api(path, body) {
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
    if (!r.ok) throw new Error(r.status);
    return r.json();
  }, function (e) { clearTimeout(timer); throw e; });
}
