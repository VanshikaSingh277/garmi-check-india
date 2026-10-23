/* small pure helpers shared by every view */
export function esc(x) { return String(x == null ? "" : x).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
export function fmt(x, d) { return x == null || isNaN(x) ? "–" : Number(x).toFixed(d == null ? 1 : d); }
export function pct(x) { return x == null ? "–" : Math.round(x * 100) + "%"; }
var INR = typeof Intl !== "undefined" ? new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 }) : null;
export function inr(x) { return INR ? INR.format(x) : String(Math.round(x)); }
export function title(s) { return String(s || "").toLowerCase().replace(/\b\w/g, function (c) { return c.toUpperCase(); }); }
export function accTxt(a) { return a == null ? "" : a < 1000 ? "±" + Math.round(a) + " m" : "±" + (a / 1000).toFixed(a < 10000 ? 1 : 0) + " km"; }
export function hm(iso) { return String(iso || "").slice(11, 16); }
export function $(id) { return document.getElementById(id); }
export function classKey(c) { return "cls_" + String(c || "").toLowerCase().replace(/\s+/g, "_"); }
export function classBadge(c) { return { "Very high": "vhigh", "High": "high", "Medium": "moderate", "Low": "low", "Very low": "low" }[c] || ""; }
export var HEAT_VAR = { low: "low", moderate: "mod", high: "high", vhigh: "vhigh", extreme: "ext" };
/* a theme colour as plain rgb(): some tokens are color-mix() expressions, which the map library can't parse,
   so paint one pixel with it and read the pixel back */
var ctx2d = null;
export function cssVar(n) {
  var v = getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  if (!/^(color-mix|var|color)\(/.test(v)) return v;
  if (!ctx2d) { var cv = document.createElement("canvas"); cv.width = cv.height = 1; ctx2d = cv.getContext("2d", { willReadFrequently: true }); }
  ctx2d.clearRect(0, 0, 1, 1); ctx2d.fillStyle = v; ctx2d.fillRect(0, 0, 1, 1);
  var p = ctx2d.getImageData(0, 0, 1, 1).data;
  return "rgba(" + p[0] + "," + p[1] + "," + p[2] + "," + (p[3] / 255).toFixed(3) + ")";
}
export function ranges(rs) { return (rs || []).map(function (r) { return r[0] + "–" + r[1]; }).join(", "); }
export function store(k, v) { try { if (v === undefined) return JSON.parse(localStorage.getItem(k)); localStorage.setItem(k, JSON.stringify(v)); } catch (e) { return null; } }
