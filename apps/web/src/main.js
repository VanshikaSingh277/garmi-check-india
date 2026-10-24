/* Thandak entry point: fonts and styles, the shell around every page (top bar, bottom nav, footer, language, theme),
   then the router. Views: src/views/*. Strings: src/i18n/{en,hi}.js. Native (Android / iOS) differences: src/native.js. */
import "@fontsource-variable/nunito-sans/wght.css";
import "@fontsource/dm-serif-display/latin-400.css";
import "@fontsource/mukta/devanagari-400.css";
import "@fontsource/mukta/devanagari-600.css";
import "@fontsource/mukta/devanagari-700.css";
import "@fontsource/tiro-devanagari-hindi/devanagari-400.css";
import "./styles.css";
import { t, setLang } from "./i18n/index.js";
import { I } from "./icons.js";
import { $ } from "./util.js";
import { S, save, APP_ROUTES } from "./state.js";
import { api } from "./api.js";
import { hooks } from "./ui.js";
import { route, go } from "./router.js";
import { initNative, setStatusBar } from "./native.js";
import { NATIVE } from "./config.js";
import { districtCsv, wardCsv } from "./export.js";

var NAV = [{ r: "app", ic: "home", k: "nav_home" }, { r: "me", ic: "thermo", k: "nav_me" }, { r: "area", ic: "users", k: "nav_area" }, { r: "gov", ic: "landmark", k: "nav_gov" }];

function applyStatic() {
  document.querySelectorAll("[data-i18n]").forEach(function (el) { el.textContent = t(el.getAttribute("data-i18n")); });
  document.documentElement.lang = S.lang; document.title = t("app_name");
  document.querySelectorAll("[data-lang]").forEach(function (b) { b.classList.toggle("on", b.getAttribute("data-lang") === S.lang); b.setAttribute("aria-pressed", String(b.getAttribute("data-lang") === S.lang)); });
  var r = route(), inApp = APP_ROUTES.indexOf(r) >= 0;
  document.body.classList.toggle("is-app", inApp); document.body.classList.toggle("is-landing", !inApp); document.body.classList.toggle("is-home", r === "");
  $("brand").setAttribute("href", inApp ? "#/app" : "#/");
  $("tabs").innerHTML = NAV.slice(1).map(function (n) { return '<a href="#/' + n.r + '" class="' + (r === n.r ? "on" : "") + '"' + (r === n.r ? ' aria-current="page"' : "") + ">" + I(n.ic, "sm") + "<span>" + t(n.k) + "</span></a>"; }).join("");
  $("bottomnav").innerHTML = NAV.map(function (n) { return '<a href="#/' + n.r + '" class="' + (r === n.r ? "on" : "") + '"' + (r === n.r ? ' aria-current="page"' : "") + ">" + I(n.ic) + "<span>" + t(n.k) + "</span></a>"; }).join("");
  $("dlWard").parentNode.hidden = !(S.a.where && S.a.where.in_delhi);
  $("barx").innerHTML = inApp ? '<a class="about-link" href="#/"><span class="hide-sm">' + t("nav_about") + '</span><span class="show-sm">' + t("nav_about_short") + "</span></a>"
    : '<a class="btn primary sm bar-enter" href="#/app">' + t("enter") + " " + I("arrow-r", "sm") + "</a>";
  var next = curTheme() === "dark" ? "light" : "dark"; // the button shows the theme it switches to
  $("themeBtn").innerHTML = I(next === "dark" ? "moon" : "sun");
  $("themeBtn").title = t("theme_" + next); $("themeBtn").setAttribute("aria-label", t("theme_" + next));
  skyBar();
}
hooks.afterRender = applyStatic;

/* light is the default; dark only when the visitor picked it */
function curTheme() { return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light"; }
/* the top bar floats transparently over the dusk sky and turns solid cream once the sky has scrolled away */
function skyBar() {
  var sky = route() === "" && $("sky"), bar = document.querySelector(".appbar");
  var onSky = !!sky && window.scrollY < 24;  // see-through only at the very top, so it never sits over cards
  bar.classList.toggle("on-sky", onSky);
  setStatusBar(onSky || curTheme() === "dark");
}
window.addEventListener("scroll", skyBar, { passive: true });

$("logo").innerHTML = I("matka"); $("logo2").innerHTML = I("matka");
document.querySelectorAll("[data-lang]").forEach(function (b) { b.onclick = function () {
  S.lang = b.getAttribute("data-lang"); save(); setLang(S.lang).then(go);
}; });
$("themeBtn").onclick = function () {
  var next = curTheme() === "dark" ? "light" : "dark";
  if (next === "dark") document.documentElement.setAttribute("data-theme", "dark"); else document.documentElement.removeAttribute("data-theme");
  try { localStorage.setItem("gc_theme", next); } catch (e) {}
  applyStatic();
};
$("dlDist").onclick = function () { api("/api/gov/rank?scope=india&limit=800&lang=" + S.lang).then(function (d) { districtCsv(d.districts); }).catch(function () {}); };
$("dlWard").onclick = function () { api("/api/gov/rank?scope=delhi&limit=300&lang=" + S.lang).then(function (d) { wardCsv(d.wards); }).catch(function () {}); };
window.addEventListener("hashchange", go);
/* while typing, the on-screen keyboard needs the space the bottom tab bar takes */
document.addEventListener("focusin", function (e) { if (e.target.matches("input[type=search], input[type=text], textarea")) document.body.classList.add("typing"); });
document.addEventListener("focusout", function () { document.body.classList.remove("typing"); });

/* Android back button: step back inside the personal check before leaving the screen */
initNative(function () {
  if (route() === "me" && S.step > 0 && S.step !== 9) { S.step--; go(); return true; }
  if (route() === "me" && S.step === 9) { S.step = 3; S.result = null; go(); return true; }
  return false;
});
/* the phone app opens on its home screen; the about page stays one tap away ("About") */
if (NATIVE && route() === "") history.replaceState(null, "", "#/app");
setLang(S.lang).then(go);
