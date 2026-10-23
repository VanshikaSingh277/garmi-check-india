/* t(key, {x}) looks up the current language and falls back to English, then to the key itself.
   English ships in the main bundle; Hindi is a separate chunk loaded only when someone picks it. */
import en from "./en.js";

var DICT = { en: en }, lang = "en";
export function getLang() { return lang; }
export function setLang(l) {
  if (l !== "hi") { lang = "en"; return Promise.resolve(); }
  if (DICT.hi) { lang = "hi"; return Promise.resolve(); }
  return import("./hi.js").then(function (m) { DICT.hi = m.default; lang = "hi"; }).catch(function () { lang = "en"; });
}
export function t(k, v) {
  var s = DICT[lang] && DICT[lang][k];
  if (s == null) s = en[k];
  if (s == null) s = k;
  if (v) Object.keys(v).forEach(function (x) { s = s.split("{" + x + "}").join(v[x]); });
  return s;
}
