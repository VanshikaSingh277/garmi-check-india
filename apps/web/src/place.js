/* the user's place: GPS / map / search, the place card, and the search box (our own /api/search - PIN code or place
   name - so nothing goes to a third-party geocoder) */
import { t } from "./i18n/index.js";
import { I } from "./icons.js";
import { esc, fmt, accTxt, classBadge, classKey, $ } from "./util.js";
import { S, save } from "./state.js";
import { api } from "./api.js";
import { locate } from "./native.js";
import { route } from "./router.js";

function methodTxt(a) { return a.method === "gps" ? t("method_gps", { a: accTxt(a.acc) }) : t({ map: "method_map", search: "method_search", saved: "method_saved" }[a.method] || "method_map"); }
function subLine(w) { return [w.district ? esc(w.district) + " " + t("district_label") : "", esc(w.state || "")].filter(Boolean).join(" · "); }
export function placeBlock(w, a, headKey) {
  if (!w) return '<div class="place"><div class="pin">' + I("pin") + '</div><div class="grow"><div class="skeleton" style="height:22px;width:60%"></div><div class="skeleton" style="height:16px;width:40%;margin-top:8px"></div></div></div>';
  if (w.in_india === false) return '<div class="callout warn">' + I("alert") + "<div>" + t("outside_india") + "</div></div>";
  return '<div class="place"><div class="pin">' + I("pin") + '</div><div class="grow">' + (headKey ? '<div class="tiny muted">' + t(headKey) + "</div>" : "") +
    '<div class="name">' + esc(w.label || w.district) + '</div><div class="sub">' + subLine(w) + (w.ward ? " · " + t("ward_label") + " " + esc(w.ward.ward) : "") + "</div>" +
    (a ? '<div class="badges" style="margin-top:8px"><span class="badge primary">' + I(a.method === "gps" ? "locate" : a.method === "search" ? "search" : "pin", "sm") + esc(methodTxt(a)) + '</span><span class="badge num">' + fmt(a.lat, 4) + "°N, " + fmt(a.lon, 4) + "°E</span></div>" : "") + "</div></div>";
}
function districtKpis(dh) {
  if (!dh) return "";
  return '<div class="kpis" style="margin-top:14px"><div class="kpi"><div class="l">' + I("sun", "sm") + t("summer_tmax") + '</div><div class="v">' + fmt(dh.tmax_mean_c) + "<small>°C</small></div><div class=\"s\">" + t("hotter_than_india", { p: Math.round(((dh.pct || {}).tmax_mean_c || 0) * 100) }) + "</div></div>" +
    '<div class="kpi"><div class="l">' + I("gauge", "sm") + t("index_label") + '</div><div class="v"><span class="badge ' + classBadge(dh.hx_class) + '" style="font-size:15px">' + t(classKey(dh.hx_class)) + '</span></div><div class="s">' + t("index_rank", { r: Math.round(dh.hx_rank), n: esc(dh.n_india) || "" }) + "</div></div></div>";
}
export function locCard() {
  var a = S.a;
  if (a.lat == null) return '<div class="callout">' + I("info") + "<div>" + t("tap_to_move") + "</div></div>";
  return placeBlock(a.where, a, a.method === "saved" ? "saved_place" : "detected") + (a.where ? districtKpis(a.where.district_heat) : "");
}
export function known() { var a = S.a; return a.lat != null && a.where && a.where.in_india !== false; }
export function setLoc(lat, lon, method, acc, ctrl, fly) {
  S.a.lat = lat; S.a.lon = lon; S.a.method = method; S.a.acc = acc || null; S.a.at = new Date().toISOString(); S.a.where = null; save();
  if (ctrl) ctrl.pin(lat, lon, acc, fly !== false);
  if ($("loccard")) $("loccard").innerHTML = locCard();
  return api("/api/where?lat=" + lat + "&lon=" + lon).then(function (w) {
    if (S.a.lat !== lat || S.a.lon !== lon) return;  // a newer fix arrived meanwhile
    S.a.where = w; save();
    if ($("loccard")) $("loccard").innerHTML = locCard();
    if ($("nx") && route() === "me" && S.step === 0) $("nx").disabled = w.in_india === false;
    if (ctrl) ctrl.select(w.district_heat && w.district_heat.id, w.ward && w.ward.ward_no);
  }).catch(function () { if ($("loccard")) $("loccard").innerHTML = locCard(); });
}
/* re-describe a saved place (e.g. saved before the district layer existed) without changing how it was found */
export function refreshWhere() {
  var a = S.a, lat = a.lat, lon = a.lon;
  return api("/api/where?lat=" + lat + "&lon=" + lon).then(function (w) {
    if (a.lat !== lat || a.lon !== lon) return;
    a.where = w; save();
    if ($("loccard")) $("loccard").innerHTML = locCard();
  }).catch(function () {});
}
export function needsRefresh() { var a = S.a; return a.lat != null && (!a.where || (!a.where.district_heat && a.where.in_india !== false)); }

export function searchBox(id) { return '<div class="search">' + I("search") + '<input class="input" id="' + id + '" type="search" autocomplete="off" enterkeyhint="search" placeholder="' + esc(t("search_ph")) + '" aria-label="' + esc(t("search_ph")) + '"><ul class="menu" id="' + id + '_r" role="listbox"></ul></div>'; }
export function bindSearch(id, onPick) {
  var inp = $(id), ul = $(id + "_r"), timer = null, items = [], seq = 0, active = -1;
  if (!inp) return;
  function paint() { ul.querySelectorAll("li[data-i]").forEach(function (li, i) { li.classList.toggle("active", i === active); }); }
  inp.oninput = function () {
    clearTimeout(timer); var q = inp.value.trim(); active = -1;
    if (q.length < 2) { ul.innerHTML = ""; return; }
    timer = setTimeout(function () {
      var my = ++seq;
      api("/api/search?q=" + encodeURIComponent(q)).then(function (d) {
        if (my !== seq) return; items = d.results;
        ul.innerHTML = items.length ? items.map(function (x, i) { return '<li role="option" data-i="' + i + '"><span class="ic">' + I(x.kind === "pin" ? "pin" : x.town ? "building" : "map", "sm") + "</span><div><b>" + esc(x.label) + "</b><span>" + esc(x.sub) + (x.approx ? " · " + t("approx") : "") + "</span></div></li>"; }).join("")
          : '<li class="none">' + t("no_results") + "</li>";
        ul.querySelectorAll("li[data-i]").forEach(function (li) { li.onpointerdown = function (e) { e.preventDefault(); }; li.onclick = function () { var it = items[+li.getAttribute("data-i")]; ul.innerHTML = ""; inp.value = it.label; inp.blur(); onPick(it); }; });
      }).catch(function () { if (my === seq) ul.innerHTML = '<li class="none">' + t("net_error") + "</li>"; });
    }, 250);
  };
  inp.onkeydown = function (e) {
    var lis = ul.querySelectorAll("li[data-i]");
    if (e.key === "ArrowDown" && lis.length) { e.preventDefault(); active = Math.min(active + 1, lis.length - 1); paint(); }
    else if (e.key === "ArrowUp" && lis.length) { e.preventDefault(); active = Math.max(active - 1, 0); paint(); }
    else if (e.key === "Enter") { e.preventDefault(); var li = lis[active < 0 ? 0 : active]; if (li) li.click(); }
    else if (e.key === "Escape") ul.innerHTML = "";
  };
  inp.onblur = function () { setTimeout(function () { ul.innerHTML = ""; }, 150); };
}
/* a search field in the style of a prompt card: input + round send button + results menu */
export function promptBox(id, cls) {
  return '<div class="prompt' + (cls ? " " + cls : "") + '">' + I("search") + '<input id="' + id + '" type="search" autocomplete="off" enterkeyhint="search" placeholder="' + esc(t("search_ph")) + '" aria-label="' + esc(t("search_ph")) + '">' +
    '<button class="send" id="' + id + 'go" type="button" aria-label="' + esc(t("search_go")) + '">' + I("arrow-r", "sm") + '</button><ul class="menu" id="' + id + '_r" role="listbox"></ul></div>';
}
export function bindPrompt(id, onPick) {
  bindSearch(id, onPick);
  $(id + "go").onclick = function () { var li = $(id + "_r").querySelector("li[data-i]"); if (li) li.click(); else $(id).focus(); };
}
export function bindGps(btnId, msgId, ctrlRef, after) {
  var b = $(btnId), m = $(msgId);
  if (!b) return;
  b.onclick = function () {
    b.disabled = true; m.innerHTML = '<span class="spin"></span><span>' + t("locating") + "</span>";
    locate(function (f) { if ($(msgId)) m.innerHTML = '<span class="spin"></span><span>' + t("refining", { a: accTxt(f.acc) }) + "</span>"; setLoc(f.lat, f.lon, "gps", f.acc, ctrlRef(), true); },
      function (err) {
        if (!$(btnId)) return;  // the user moved to another page meanwhile
        b.disabled = false;
        if (err) { m.innerHTML = '<div class="callout warn">' + I("alert") + "<div>" + t("gps_" + err) + "</div></div>"; return; }
        m.innerHTML = (S.a.acc || 0) > 1000 ? '<div class="callout warn">' + I("alert") + "<div>" + t("gps_rough", { a: accTxt(S.a.acc) }) + "</div></div>" : "";
        if (after) after();
      });
  };
}
