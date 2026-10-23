/* hash routes: #/ landing · #/app home · #/me personal check · #/area colony · #/gov government · #/how method · #/sources
   Each view lives in its own module and is loaded on first visit, so opening the app downloads only the screen shown. */
import { S } from "./state.js";

var VIEWS = {
  "": [function () { return import("./views/landing.js"); }, function (m) { m.landing(); }],
  app: [function () { return import("./views/home.js"); }, function (m) { m.appHome(); }],
  me: [function () { return import("./views/check.js"); }, function (m) { if (S.result && S.step === 9) m.resultView(); else m.flowStep(); }],
  area: [function () { return import("./views/area.js"); }, function (m) { m.areaView(); }],
  gov: [function () { return import("./views/gov.js"); }, function (m) { m.govView(); }],
  how: [function () { return import("./views/info.js"); }, function (m) { m.howView(); }],
  sources: [function () { return import("./views/info.js"); }, function (m) { m.sourcesView(); }]
};
export function route() { return location.hash.replace(/^#\/?/, "").split("/")[0]; }
var seq = 0, last = null;
export function go() {
  var r = route(), my = ++seq, v = VIEWS[r] || VIEWS[""];
  /* the place is chosen on the home screen, so opening the personal check from there starts at the roof question */
  if (r === "me" && last !== "me" && !S.result && S.step === 0 && S.a.where && S.a.where.in_india !== false) S.step = 1;
  last = r;
  return v[0]().then(function (m) {
    if (my === seq) v[1](m);  // a slow chunk must not paint over a page the user already moved on to
  }, function () {
    /* a chunk from an older deploy is gone: reload once to get the new build */
    try { if (!sessionStorage.getItem("gc_reloaded")) { sessionStorage.setItem("gc_reloaded", "1"); location.reload(); } } catch (e) {}
  });
}
