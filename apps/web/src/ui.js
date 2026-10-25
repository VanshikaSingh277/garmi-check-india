/* page rendering and the small building blocks every view uses */
import { t } from "./i18n/index.js";
import { I } from "./icons.js";
import { SCENE } from "./art.js";
import { esc, $ } from "./util.js";
import { S } from "./state.js";
import { destroyMaps } from "./map.js";

var app = $("app");
export function root() { return app; }
/* the shell sets this so every page refresh also refreshes the nav, language buttons and title */
export var hooks = { afterRender: function () {} };

/* render(html) puts a page in the content column; render(html, pageHero(...)) adds the dusk-sky header and lets the
   first card rest on the sky (pass lift=false to keep it below); render(html, RAW) is for the full-bleed landing page */
export var RAW = {};
export function render(html, hero, lift) {
  destroyMaps();
  app.innerHTML = '<div class="fade">' + (hero === RAW ? html : (hero || "") + '<div class="page' + (hero && lift !== false ? " lifted" : "") + '">' + html + "</div>") + "</div>";
  hooks.afterRender(); window.scrollTo(0, 0); fx();
}
export function moodOf(level) { return !level || level === "low" ? "happy" : level === "moderate" ? "warm" : "hot"; }
/* compact dusk-sky header used by every inner page: title on the left, the matka with a speech bubble on the right */
export function pageHero(o) {
  return '<section class="sky pagesky"><div class="wrap ph"><div class="ph-text">' + (o.eyebrow ? '<span class="eyebrow">' + o.eyebrow + "</span>" : "") + "<h1>" + o.title + "</h1>" +
    (o.sub ? '<p class="lead">' + o.sub + "</p>" : "") + (o.extra || "") + '</div><div class="ph-aside">' +
    '<div class="bubble" id="bubble" role="status">' + (o.tip || "") + "</div>" +
    '<button class="mascot-btn" type="button" id="' + o.id + '" aria-label="' + esc(t("mascot_label")) + '">' + SCENE.mascot(o.id + "s", o.mood) + "</button></div></div>" +
    SCENE.clouds(o.id + "c", "front") + "</section>";
}
export function setMascot(id, mood, tip) {
  var b = $(id); if (!b) return;
  b.innerHTML = SCENE.mascot(id + "s", mood);
  var bub = b.parentNode.querySelector(".bubble"); if (bub && tip != null) bub.innerHTML = tip;
}
export function card(icon, head, body, extra) { return '<div class="card"' + (extra || "") + '><div class="card-h"><div class="ic">' + I(icon) + "</div><h3>" + head + "</h3></div>" + body + "</div>"; }
export function skeletonCard(h) { return '<div class="card"><div class="skeleton" style="height:22px;width:40%"></div><div class="skeleton" style="height:' + (h || 120) + 'px;margin-top:14px"></div></div>'; }
export function callout(icon, html, cls, style) { return '<div class="callout' + (cls ? " " + cls : "") + '"' + (style ? ' style="' + style + '"' : "") + ">" + I(icon) + "<div>" + html + "</div></div>"; }
/* a failed load with a working retry button (onRetry is bound by the caller via the returned id) */
export function failBox(msgKey) { return callout("alert", t(msgKey || "load_fail") + ' <button class="btn sm secondary" type="button" data-retry>' + t("retry") + "</button>", "warn"); }
/* the five-step "how it works" list (landing page and the method page) */
export function timeline() {
  return '<ol class="timeline">' + ["p1", "p2", "p3", "p4", "p5"].map(function (k, i) { return '<li><span class="n" aria-hidden="true">' + (i + 1) + "</span><b>" + t(k + "_t") + "</b><p>" + t(k + "_d") + "</p></li>"; }).join("") + "</ol>";
}
export function bindRetry(fn) { app.querySelectorAll("[data-retry]").forEach(function (b) { b.onclick = fn; }); }

/* ---------- interaction: matka tips, eyes, count-ups, scroll reveal ---------- */
export var MOTION = !(window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches);
var N_TIPS = 6;
if (MOTION) document.documentElement.classList.add("motion");
function tipFrom(btn) {
  var host = btn.parentNode, bub = host.querySelector(".bubble");
  S.tip = (S.tip || 0) % N_TIPS + 1;
  if (bub) { bub.hidden = false; bub.innerHTML = t("tip_" + S.tip); }
  btn.classList.remove("hop"); void btn.offsetWidth; btn.classList.add("hop");
}
function countUp(el) {
  var end = parseFloat(el.getAttribute("data-count")); if (isNaN(end)) return;
  var dec = +(el.getAttribute("data-dec") || 0), from = end - Math.max(6, Math.abs(end) * 0.25), t0 = performance.now();
  (function step(now) {
    var k = Math.min(1, (now - t0) / 700), v = from + (end - from) * (1 - Math.pow(1 - k, 3));
    el.textContent = k < 1 ? v.toFixed(dec) : el.getAttribute("data-final") || end.toFixed(dec);
    if (k < 1) requestAnimationFrame(step);
  })(t0);
}
var revealer = window.IntersectionObserver ? new IntersectionObserver(function (es) { es.forEach(function (e) { if (e.isIntersecting) { var el = e.target; el.classList.add("in"); revealer.unobserve(el); setTimeout(function () { el.style.transitionDelay = ""; }, 1200); } }); }, { rootMargin: "0px 0px -8% 0px" }) : null;
export function fx() {
  app.querySelectorAll(".mascot-btn").forEach(function (b) { b.onclick = function () { tipFrom(b); }; });
  if (!MOTION) return;
  app.querySelectorAll("[data-count]").forEach(countUp);
  if (revealer) app.querySelectorAll(".lsec .head, .acard, .panel, .timeline li, .trust3 .card, .entry").forEach(function (el) {
    el.classList.add("rv"); if (el.matches(".timeline li, .acard, .trust3 .card, .entry")) el.style.transitionDelay = (Array.prototype.indexOf.call(el.parentNode.children, el) * 70) + "ms";
    revealer.observe(el);
  });
}
/* the matka's eyes follow the pointer (mouse only: on touch screens there is no hover to follow) */
var look = { x: 0, y: 0, raf: 0 };
if (MOTION && window.matchMedia && matchMedia("(hover: hover)").matches) document.addEventListener("pointermove", function (e) {
  look.x = e.clientX; look.y = e.clientY; if (look.raf) return;
  look.raf = requestAnimationFrame(function () {
    look.raf = 0;
    document.querySelectorAll(".mascot-svg .pupils").forEach(function (g) {
      var r = g.ownerSVGElement.getBoundingClientRect(); if (!r.width || r.bottom < 0 || r.top > innerHeight) return;
      var dx = look.x - (r.left + r.width * 0.5), dy = look.y - (r.top + r.height * 0.6), d = Math.sqrt(dx * dx + dy * dy) || 1, k = Math.min(1, d / 260) * 5;
      g.setAttribute("transform", "translate(" + (dx / d * k).toFixed(2) + " " + (dy / d * k).toFixed(2) + ")");
    });
  });
}, { passive: true });
