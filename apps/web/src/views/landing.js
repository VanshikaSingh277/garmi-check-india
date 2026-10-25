/* #/ - about Thandak: the dusk-sky hero with a live forecast card, the problem, who it is for, method, trust */
import { t } from "../i18n/index.js";
import { I } from "../icons.js";
import { SCENE } from "../art.js";
import { esc, fmt, $ } from "../util.js";
import { S } from "../state.js";
import { api } from "../api.js";
import { render, RAW, timeline } from "../ui.js";
import { promptBox, bindPrompt, bindGps, setLoc, refreshWhere, known } from "../place.js";
import { route } from "../router.js";

/* each fact is a row of docs/verified_numbers.csv (mortality.india.heatwave, roof.offset.tin_top, fan.limit.older) */
var FACTS = [
  { n: "14.7%", k: "f1", c: "c-rooh", url: "https://doi.org/10.1016/j.envint.2024.108461", src: "de Bont et al., Environment International, 2024" },
  { n: "+3.5 °C", k: "f2", c: "c-aam", url: "https://doi.org/10.6084/m9.figshare.12546368.v1", src: "Tasgaonkar et al., Scientific Data, 2022 (13 Delhi homes, 2016)" },
  { n: "35 °C", k: "f3", c: "c-nimbu", url: "https://doi.org/10.1016/S2542-5196(24)00030-5", src: "Meade et al., Lancet Planetary Health, 2024" }
];
var WHO = [
  { ic: "thermo", k: "individual", d: "who_me_d", pts: ["who_me_1", "who_me_2", "who_me_3"] },
  { ic: "users", k: "society", d: "who_soc_d", pts: ["who_soc_1", "who_soc_2", "who_soc_3"] },
  { ic: "landmark", k: "government", d: "who_gov_d", pts: ["who_gov_1", "who_gov_2", "who_gov_3"] }
];

function whoPanel(i) {
  var w = WHO[i];
  return '<div><p class="lede">' + t(w.d) + '</p></div><ul>' + w.pts.map(function (k) { return "<li>" + I("check") + "<span>" + t(k) + "</span></li>"; }).join("") + "</ul>";
}
/* before a place is picked: the same card, faded, with a made-up day shape (cool night, hot afternoon) and no numbers,
   so it never reads as real weather */
function previewCard() {
  var W = 240, H = 70, pts = [];
  for (var i = 0; i < 24; i++) pts.push(0.5 - 0.5 * Math.cos(2 * Math.PI * (i - 3) / 24));
  function line(off) { return pts.map(function (v, i) { return (i ? "L" : "M") + (W * i / 23).toFixed(1) + "," + (8 + (H - 16) * (1 - v) + off).toFixed(1); }).join(" "); }
  return '<div class="l">' + t("live_label") + '</div><div class="preview" aria-hidden="true">' +
    '<svg class="spark" viewBox="0 0 ' + W + " " + H + '" preserveAspectRatio="none"><path d="' + line(0) + '" fill="none" style="stroke:var(--aam-deep)" stroke-width="2.5" vector-effect="non-scaling-stroke"/><path d="' + line(4) + '" fill="none" style="stroke:var(--jamun-deep)" stroke-width="2.5" stroke-dasharray="5 4" vector-effect="non-scaling-stroke"/></svg>' +
    '<div class="lg"><span><i style="background:var(--aam-deep)"></i>' + t("outside") + '</span><span><i style="background:var(--jamun-deep)"></i>' + t("feels") + "</span></div></div>" +
    '<p class="d" style="margin-top:10px">' + t("live_pick") + "</p>";
}
/* live floating card: the real next-24-hour forecast for the user's saved place (a faded preview until they pick one) */
function liveCard(w, label) {
  if (w === "pick") return previewCard();
  if (!w) return '<div class="l">' + t("live_label") + '</div><div class="skeleton" style="height:96px;margin-top:8px"></div>';
  var hrs = (w.next24 || []).slice(0, 24), lvl = w.level || (w.today || {}).hi_level || "low";
  if (hrs.length < 2) return '<div class="l">' + t("live_label") + "</div>";
  var vals = []; hrs.forEach(function (h) { vals.push(h.t, h.hi); });
  var lo = Math.min.apply(null, vals) - 1, hi = Math.max.apply(null, vals) + 1, W = 240, H = 70;
  function line(k) { return hrs.map(function (h, i) { return (i ? "L" : "M") + (W * i / (hrs.length - 1)).toFixed(1) + "," + (4 + (H - 8) * (hi - h[k]) / (hi - lo)).toFixed(1); }).join(" "); }
  var mx = function (k) { return Math.max.apply(null, hrs.map(function (h) { return h[k]; })); };
  return '<div class="l">' + t("live_next24", { p: esc(label) }) + '</div>' +
    '<svg class="spark" viewBox="0 0 ' + W + " " + H + '" preserveAspectRatio="none" role="img" aria-label="' + esc(t("live_next24", { p: label })) + '"><path d="' + line("t") + '" fill="none" style="stroke:var(--aam-deep)" stroke-width="2.5" vector-effect="non-scaling-stroke"/><path d="' + line("hi") + '" fill="none" style="stroke:var(--jamun-deep)" stroke-width="2.5" stroke-dasharray="5 4" vector-effect="non-scaling-stroke"/></svg>' +
    '<div class="lg"><span><i style="background:var(--aam-deep)"></i>' + t("outside") + " " + fmt(mx("t"), 0) + '°</span><span><i style="background:var(--jamun-deep)"></i>' + t("feels") + " " + fmt(mx("hi"), 0) + "°</span></div>" +
    '<div style="margin-top:10px"><span class="badge ' + lvl + '">' + t("today_band") + ": " + t("level_" + lvl) + "</span></div>";
}
function matka(id) { return '<div class="mascot"><div class="bubble float" role="status" hidden></div><button class="mascot-btn" type="button" aria-label="' + esc(t("mascot_label")) + '">' + SCENE.mascot(id.charAt(0) + "m") + "</button></div>"; }
function mascot(id) { return SCENE.clouds(id, "back") + matka(id) + SCENE.clouds(id, "front"); }

export function landing() {
  var a = S.a, saved = known();
  render('<section class="sky" id="sky"><div class="wrap hero"><h1>' + t("lp_title") + '</h1><p class="lead">' + t("lp_sub") + "</p>" +
    '<div class="cta-row"><a class="btn white lg attn" href="#/app">' + t("enter") + " " + I("arrow-r") + "</a></div>" +
    (saved ? '<p class="saved-link">' + I("pin", "sm") + "<span>" + t("lp_saved", { p: esc(a.where.label || a.where.district || "") }) + '</span><a href="#/app">' + t("go_my_heat") + " →</a></p>" : "") +
    '<div class="peek"><div class="mid">' + promptBox("lq") + '<button class="btn ghost-sky gps-btn" id="lgps" type="button">' + I("locate") + t("use_gps") + '</button><div class="statusline" id="lmsg"></div></div>' +
    /* the matka sits in the same row as the live card, so however tall the hero gets it is never cut off */
    '<div class="fcard" id="livecard">' + liveCard(saved ? null : "pick") + "</div>" + matka("hc") + "</div></div>" + SCENE.clouds("hc", "back") + SCENE.clouds("hc", "front") + "</section>" +
    '<section class="lsec"><div class="wrap"><div class="head"><h2>' + t("prob_title") + "</h2><p>" + t("prob_sub") + '</p></div><div class="acards">' +
    FACTS.map(function (f) { return '<div class="acard ' + f.c + '"><div class="big">' + f.n + "</div><p>" + t(f.k + "_t") + "</p></div>"; }).join("") + "</div></div></section>" +
    '<section class="sky band"><div class="wrap"><div class="panel"><h2>' + t("who_title") + '</h2><div class="tabnav" role="tablist">' +
    WHO.map(function (w, i) { return '<button role="tab" id="whot' + i + '" aria-controls="whop" aria-selected="' + (i === 0) + '" data-who="' + i + '">' + I(w.ic, "sm") + t(w.k) + "</button>"; }).join("") +
    /* all three panels share one grid cell, so the box keeps the tallest one's height when switching tabs */
    '</div><div class="tabstack" id="whop" role="tabpanel" aria-labelledby="whot0">' +
    WHO.map(function (w, i) { return '<div class="tabpanel' + (i ? " off" : "") + '" data-whop="' + i + '"' + (i ? ' aria-hidden="true"' : "") + ">" + whoPanel(i) + "</div>"; }).join("") +
    "</div></div></div>" + SCENE.clouds("wc", "back") + "</section>" +
    '<section class="lsec"><div class="wrap"><div class="head"><h2>' + t("how_teaser") + "</h2><p>" + t("how_lp_sub") + "</p></div>" + timeline() +
    '<div class="center"><a class="more-link" href="#/how">' + t("full_method") + " " + I("arrow-r", "sm") + "</a></div></div></section>" +
    '<section class="lsec" style="background:var(--surface-2)"><div class="wrap"><div class="head"><h2>' + t("trust_title") + '</h2></div><div class="trust3">' +
    [["t1", "shield", "trust_sourced", "trust_sourced_d"], ["t2", "lock", "trust_private", "trust_private_d"], ["t3", "check", "trust_free", "trust_free_d"]].map(function (x) { return '<div class="card ' + x[0] + '">' + I(x[1]) + "<b>" + t(x[2]) + "</b><p>" + t(x[3]) + "</p></div>"; }).join("") +
    "</div></div></section>" +
    '<section class="sky cta"><div class="wrap"><h2>' + t("cta_title") + "</h2><p>" + t("cta_sub") + '</p><div class="cta-row"><a class="btn white lg attn" href="#/app">' + t("enter") + " " + I("arrow-r") + "</a></div></div>" + mascot("cc") + "</section>", RAW);
  bindPrompt("lq", function (it) { setLoc(it.lat, it.lon, "search", null, null).then(function () { location.hash = "#/app"; }); });
  bindGps("lgps", "lmsg", function () { return null; }, function () { location.hash = "#/app"; });
  document.querySelectorAll("[data-who]").forEach(function (b) {
    b.onclick = function () {
      var i = +b.getAttribute("data-who");
      document.querySelectorAll("[data-who]").forEach(function (x) { x.setAttribute("aria-selected", String(x === b)); });
      $("whop").setAttribute("aria-labelledby", b.id);
      document.querySelectorAll("[data-whop]").forEach(function (p) { var off = +p.getAttribute("data-whop") !== i; p.classList.toggle("off", off); p.setAttribute("aria-hidden", String(off)); });
    };
    /* arrow keys move between tabs */
    b.onkeydown = function (e) {
      if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
      var tabs = document.querySelectorAll("[data-who]"), j = (+b.getAttribute("data-who") + (e.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length;
      tabs[j].focus(); tabs[j].click(); e.preventDefault();
    };
  });
  var p = saved ? { lat: a.lat, lon: a.lon, label: a.where.label || a.where.district } : null;
  if (p) api("/api/weather?lat=" + p.lat + "&lon=" + p.lon).then(function (w) { if ($("livecard")) $("livecard").innerHTML = liveCard(w, p.label); }).catch(function () { var c = $("livecard"); if (c) c.style.display = "none"; });
  if (a.lat != null && !a.where && !S._rw) { S._rw = true; refreshWhere().then(function () { if (route() === "" && S.a.where) landing(); }); }
}
