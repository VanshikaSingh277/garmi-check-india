/* app state; the answers and language survive restarts (localStorage), the rest is per session */
import { store } from "./util.js";

export var S = { lang: "en", step: 0, result: null, layer: "hx_index", gscope: "india", gcity: "", gstate: "", gdist: "", gfilter: "", gsort: null, glimit: 60, ptab: "plan",
                 a: { lat: null, lon: null, method: null, acc: null, at: null, where: null, roof: null, vulnerable: [], devices: {}, roof_access: true, cross_ventilation: null, budget: null } };
export var LEVELS = ["low", "moderate", "high", "extreme"];
export var APP_ROUTES = ["app", "me", "area", "gov"];

var sv = store("gc_state") || {};
if (sv.lang) S.lang = sv.lang;
if (sv.a) { S.a = Object.assign(S.a, sv.a); if (S.a.lat != null) S.a.method = "saved"; }  // never present an old fix as "just detected"
export function save() { store("gc_state", { lang: S.lang, a: S.a }); }
