/* #/gov - government / ward office: all-India district ranking (or Delhi wards), map, sortable table, CSV, schemes */
import { t } from "../i18n/index.js";
import { I } from "../icons.js";
import { esc, fmt, pct, inr, title, classBadge, classKey, HEAT_VAR, $ } from "../util.js";
import { S } from "../state.js";
import { api } from "../api.js";
import { render, pageHero, card, skeletonCard, failBox, bindRetry, MOTION } from "../ui.js";
import { makeMap, mapTools, bindTools, mapFail, legend, popup, WARD_STOPS, DELHI } from "../map.js";
import { districtCsv, wardCsv } from "../export.js";
import { fixesBlock } from "./parts.js";

var SCHEMES = [["scheme_1", "https://ndma.gov.in/sites/default/files/PDF/Guidelines/Heatwaveguidelines.pdf"],
  ["scheme_2", "https://ncdc.mohfw.gov.in/uploads/pdf/4.%20Heat%20wave%20advisory%20for%20State%20Health%20department_2026.pdf"],
  ["scheme_3", "https://www.downtoearth.org.in/climate-change/india-updates-disaster-list-to-include-heatwaves-and-lightning-after-finance-commission-push"]];
var DATA = {};

export function govView() {
  var inDelhi = !!(S.a.where && S.a.where.in_delhi);
  if (!inDelhi) S.gscope = "india";
  var india = S.gscope !== "delhi", key = S.lang + "|" + (india ? "india|" + S.gstate : "delhi");  // the fixes come back in the page language
  var hero = pageHero({ id: "gm", title: t("gov_title"), sub: t("government_sub"), tip: t("gov_tip"), mood: "happy", extra: inDelhi ? '<div class="seg lg" id="scope"><button type="button" data-scope="india" class="' + (india ? "on" : "") + '">' + I("map", "sm") + t("scope_india") + '</button><button type="button" data-scope="delhi" class="' + (!india ? "on" : "") + '">' + I("building", "sm") + t("scope_delhi") + "</button></div>" : "" });
  if (!DATA[key]) {
    render(skeletonCard(60) + "<br>" + skeletonCard(380), hero);
    bindScope();
    var q = india ? "/api/gov/rank?scope=india&limit=800&lang=" + S.lang + (S.gstate ? "&state=" + encodeURIComponent(S.gstate) : "") : "/api/gov/rank?scope=delhi&limit=300&lang=" + S.lang;
    api(q).then(function (d) { DATA[key] = d; if (location.hash.indexOf("#/gov") === 0) govView(); })
      .catch(function () { render(failBox(), hero); bindScope(); bindRetry(govView); });
    return;
  }
  var d = DATA[key], rows = india ? d.districts : d.wards;
  var cols = india ? [["hx_rank", "#", 1], ["district", t("col_district")], ["hx_index", t("col_index"), 1], ["tmax_mean_c", t("col_tmax"), 1], ["tmin_mean_c", t("col_tmin"), 1], ["twb_max_mean_c", t("col_twb"), 1], ["days_tmax_ge40", t("col_hot40"), 1], ["share_65plus", t("col_65"), 1], ["pop_total", t("col_pop"), 1]]
    : [["hvi_rank", "#", 1], ["ward_name", t("ward")], ["hvi", "HVI", 1], ["lst_day_mean_c", t("day"), 1], ["lst_night_mean_c", t("night"), 1], ["frac_tree", t("trees"), 1], ["pop_65plus", t("elderly65"), 1], ["drivers", t("drivers")]];
  var vh = india ? rows.filter(function (x) { return x.hx_class === "Very high"; }) : [];
  var kpis = india ? '<div class="kpis" style="margin-bottom:16px"><div class="kpi"><div class="l">' + I("map", "sm") + t("kpi_shown") + '</div><div class="v"><span data-count="' + rows.length + '">' + rows.length + '</span></div></div><div class="kpi"><div class="l">' + I("flame", "sm") + t("kpi_vh") + '</div><div class="v"><span data-count="' + vh.length + '">' + vh.length + '</span></div></div><div class="kpi"><div class="l">' + I("users", "sm") + t("kpi_people_vh") + '</div><div class="v">' + inr(vh.reduce(function (s, x) { return s + (x.pop_total || 0); }, 0)) + '</div></div><div class="kpi"><div class="l">' + I("sun", "sm") + t("kpi_mean_tmax") + '</div><div class="v">' + fmt(rows.reduce(function (s, x) { return s + x.tmax_mean_c; }, 0) / Math.max(rows.length, 1)) + "<small>°C</small></div></div></div>" : "";
  var tools = '<div class="toolbar">' + (india ? '<select class="input" id="st" style="max-width:260px" aria-label="' + esc(t("state_all")) + '"><option value="">' + t("state_all") + "</option>" + d.states.map(function (x) { return "<option" + (x === S.gstate ? " selected" : "") + ">" + esc(x) + "</option>"; }).join("") + "</select>" : "") +
    '<div class="search">' + I("search") + '<input class="input" id="gf" type="search" placeholder="' + esc(t("filter_ph")) + '" aria-label="' + esc(t("filter_ph")) + '" value="' + esc(S.gfilter) + '"></div><button type="button" class="btn secondary" id="csv">' + I("download") + t("download_csv") + "</button></div>";
  render(kpis + tools + '<div class="mapbox" style="margin-bottom:20px"><div id="map" class="map"></div>' + (india ? mapTools("gt") : legend(WARD_STOPS, "", "layer_index", 2)) + "</div>" +
    '<div class="card" style="padding:0;overflow:hidden"><div style="padding:16px 20px 8px" class="row between"><h3>' + t("rank_label") + '</h3><span class="tiny muted">' + t("sort_hint") + '</span></div><div id="tbl"></div></div>' +
    '<div class="layout" style="margin-top:20px"><div>' + card("list", t("todo"), fixesBlock(d.solutions)) + '</div><div class="stack">' +
    card("book", t("schemes"), '<ul class="bullets">' + SCHEMES.map(function (s) { return '<li><a target="_blank" rel="noopener" href="' + s[1] + '">' + t(s[0]) + "</a></li>"; }).join("") + "</ul>") + "</div></div>", hero);
  bindScope();
  var ctrl = null;
  function table() {
    var f = S.gfilter.trim().toLowerCase(), nameKey = india ? "district" : "ward_name";
    var list = rows.filter(function (x) { return !f || String(x[nameKey]).toLowerCase().indexOf(f) >= 0 || String(x.state || x.district || "").toLowerCase().indexOf(f) >= 0; });
    var s = S.gsort && S.gsort.scope === key ? S.gsort : { k: india ? "hx_rank" : "hvi_rank", dir: 1 };
    list = list.slice().sort(function (p, q) { var x = p[s.k], y = q[s.k]; if (typeof x === "string") return s.dir * String(x).localeCompare(String(y)); return s.dir * ((x == null ? -1e9 : x) - (y == null ? -1e9 : y)); });
    var shown = list.slice(0, S.glimit);
    var cell = function (x, c) {
      var v = x[c[0]];
      if (c[0] === "hx_rank" || c[0] === "hvi_rank") return '<td class="num"><span class="rankpill">' + Math.round(v) + "</span></td>";
      if (c[0] === "district") return "<td><b>" + esc(v) + '</b><div class="tiny muted">' + esc(x.state) + "</div></td>";
      if (c[0] === "ward_name") return "<td><b>" + esc(title(v)) + '</b><div class="tiny muted">' + esc(x.district) + "</div></td>";
      if (c[0] === "hx_index" || c[0] === "hvi") { var cls = india ? classBadge(x.hx_class) : (v > WARD_STOPS[4] ? "vhigh" : v > WARD_STOPS[2] ? "high" : v > WARD_STOPS[0] ? "moderate" : "low"); return '<td class="num"><span class="meterbar"><i style="width:' + Math.round(v * 100) + "%;background:var(--" + (HEAT_VAR[cls] || "ink-muted") + ')"></i></span>' + fmt(v, 2) + "</td>"; }
      if (c[0] === "share_65plus" || c[0] === "frac_tree") return '<td class="num">' + pct(v) + "</td>";
      if (c[0] === "pop_total" || c[0] === "pop_65plus") return '<td class="num">' + inr(v) + "</td>";
      if (c[0] === "days_tmax_ge40") return '<td class="num">' + fmt(v, 0) + "</td>";
      if (c[0] === "drivers") return '<td class="tiny">' + (v || []).map(function (z) { return t("drv_" + z.code); }).join("; ") + "</td>";
      return '<td class="num">' + fmt(v) + "</td>";
    };
    $("tbl").innerHTML = '<div class="tablewrap" style="border:0;border-radius:0"><table class="data"><thead><tr>' + cols.map(function (c) { return '<th data-k="' + c[0] + '" class="' + (c[2] ? "num " : "") + (s.k === c[0] ? "sorted" : "") + '" aria-sort="' + (s.k === c[0] ? (s.dir > 0 ? "ascending" : "descending") : "none") + '">' + c[1] + " " + I(s.k === c[0] ? (s.dir > 0 ? "arrow-up" : "sort") : "sort", "sm") + "</th>"; }).join("") + "</tr></thead><tbody>" +
      shown.map(function (x, i) { return '<tr data-i="' + i + '" tabindex="0">' + cols.map(function (c) { return cell(x, c); }).join("") + "</tr>"; }).join("") + "</tbody></table></div>" +
      (list.length > shown.length ? '<div style="padding:14px 20px"><button type="button" class="btn secondary sm" id="more">' + t("show_more") + " (" + (list.length - shown.length) + ")</button></div>" : "");
    /* one listener for the whole table instead of one per row (800 districts) */
    $("tbl").onclick = function (e) {
      var th = e.target.closest("th[data-k]");
      if (th) { var k2 = th.getAttribute("data-k"); S.gsort = { scope: key, k: k2, dir: s.k === k2 ? -s.dir : 1 }; return table(); }
      var tr = e.target.closest("tbody tr"); if (tr) fly(tr);
    };
    $("tbl").onkeydown = function (e) { var tr = e.key === "Enter" && e.target.closest("tbody tr"); if (tr) fly(tr); };
    if ($("more")) $("more").onclick = function (e) { e.stopPropagation(); S.glimit += 100; table(); };
    /* click (or Enter on) a row to fly the map to that district / ward */
    function fly(tr) {
      var x = shown[+tr.getAttribute("data-i")]; if (!ctrl || !x || x.lat == null) return;
      ctrl.select(india ? x.id : null, india ? null : x.ward_no);
      ctrl.map.flyTo({ center: [x.lon, x.lat], zoom: india ? 6.5 : 12, speed: 1.4 });
      document.querySelectorAll("#tbl tr.sel").forEach(function (r) { r.classList.remove("sel"); }); tr.classList.add("sel");
      $("map").scrollIntoView({ behavior: MOTION ? "smooth" : "auto", block: "center" });
    }
  }
  table();
  var ft = null;
  $("gf").oninput = function (e) { clearTimeout(ft); ft = setTimeout(function () { S.gfilter = e.target.value; S.glimit = 60; table(); }, 120); };
  if (india) $("st").onchange = function (e) { S.gstate = e.target.value; S.glimit = 60; govView(); };
  $("csv").onclick = function () { if (india) districtCsv(rows); else wardCsv(rows); };
  var first = india && S.gstate && rows[0] ? rows[0] : null;
  makeMap({ el: "map", center: india ? (first ? [first.lon, first.lat] : null) : DELHI.center, zoom: india ? (first ? 5.8 : null) : DELHI.zoom, wards: india ? null : "fill",
    onClick: function (ll, dp, wp) {
      if (!ctrl) return;
      var pop = !india && wp ? "<b>" + esc(title(wp.ward_name)) + "</b><br>" + esc(wp.district) + "<br>HVI " + fmt(wp.hvi, 2) + " · " + t(classKey(wp.hvi_class)) + "<br>" + t("day") + " " + fmt(wp.lst_day_mean_c) + " · " + t("night") + " " + fmt(wp.lst_night_mean_c)
        : dp && dp.hx_index != null ? "<b>" + esc(dp.district) + "</b><br>" + esc(dp.state || "") + "<br>" + t("index_label") + " " + fmt(dp.hx_index, 2) + " · " + t(classKey(dp.hx_class)) + " (#" + Math.round(dp.hx_rank) + ")<br>" + t("col_tmax") + " " + fmt(dp.tmax_mean_c) + " °C · " + t("col_tmin") + " " + fmt(dp.tmin_mean_c) + " °C<br>" + t("col_twb") + " " + fmt(dp.twb_max_mean_c) + " °C · " + t("col_65") + " " + pct(dp.share_65plus) : null;
      if (!pop) return;
      ctrl.select(dp && dp.id, wp && wp.ward_no);
      popup(ctrl, ll, pop);
    } }).then(function (c) { ctrl = c; if (india) bindTools("gt", c); }).catch(function () { mapFail("map"); });
}
function bindScope() { document.querySelectorAll("#scope button").forEach(function (b) { b.onclick = function () { S.gscope = b.getAttribute("data-scope"); S.gfilter = ""; S.glimit = 60; govView(); }; }); }
