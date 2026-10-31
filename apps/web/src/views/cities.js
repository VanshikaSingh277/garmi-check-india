/* City surface-heat hotspots (government view, scope "cities"): 1 km squares of pre-monsoon surface temperature for each
   city with a satellite grid, the hottest named places and their main reasons, plus how surface and air temperature
   compare at weather stations. Data: /api/gov/hotspots. */
import { t } from "../i18n/index.js";
import { I } from "../icons.js";
import { esc, fmt, pct, $ } from "../util.js";
import { S } from "../state.js";
import { api } from "../api.js";
import { render, card, callout, skeletonCard, failBox, bindRetry } from "../ui.js";
import { makeMap, addCells, legend, popup, mapFail } from "../map.js";

var LIST = null, CITY = {}, STOPS = [-3, -1.5, 0, 1.5, 3];
function signed(x) { return (x > 0 ? "+" : "") + fmt(x, 1); }

export function citiesView(hero, bindScope) {
  if (!LIST) {
    render(skeletonCard(60) + "<br>" + skeletonCard(380), hero); bindScope();
    api("/api/gov/hotspots").then(function (d) { LIST = d; citiesView(hero, bindScope); })
      .catch(function () { render(failBox(), hero); bindScope(); bindRetry(function () { citiesView(hero, bindScope); }); });
    return;
  }
  if (!S.gcity || !LIST.cities.some(function (c) { return c.key === S.gcity; })) S.gcity = LIST.cities[0].key;
  var d = CITY[S.gcity];
  if (!d) {
    render(skeletonCard(60) + "<br>" + skeletonCard(380), hero); bindScope();
    api("/api/gov/hotspots?city=" + S.gcity).then(function (x) { CITY[S.gcity] = x; citiesView(hero, bindScope); })
      .catch(function () { render(failBox(), hero); bindScope(); bindRetry(function () { citiesView(hero, bindScope); }); });
    return;
  }
  var pick = '<div class="seg wrap" id="cityPick" role="group">' + LIST.cities.map(function (c) { return '<button type="button" data-city="' + esc(c.key) + '" class="' + (c.key === S.gcity ? "on" : "") + '" aria-pressed="' + (c.key === S.gcity) + '">' + esc(c.name) + "</button>"; }).join("") + "</div>";
  var kpi = function (label, v) { return '<div class="kpi"><div class="l">' + label + '</div><div class="v">' + v + "</div></div>"; };
  var kpis = '<div class="kpis" style="margin:16px 0">' + kpi(t("hc_median"), fmt(d.lst_median_c) + "<small>°C</small>") + kpi(t("hc_p90"), fmt(d.lst_p90_block_c) + "<small>°C</small>") +
    kpi(t("hc_cells"), d.cells.length) + kpi(t("hc_scenes"), d.lst_scenes) + "</div>";
  var rows = d.hottest.map(function (h, i) {
    return '<tr data-i="' + i + '" tabindex="0"><td class="num"><span class="rankpill">' + (i + 1) + "</span></td><td><b>" + esc(h.place) + '</b></td><td class="num">' + fmt(h.lst_c) + '</td><td class="num">' + signed(h.vs_city_c) + '</td><td class="num">' + pct(h.tree) + '</td><td class="tiny">' + h.drivers.map(function (z) { return t("drv_" + z); }).join("; ") + "</td></tr>";
  }).join("");
  var a = d.air_check, air = a ? callout("info", t("hc_air", { d: fmt(a.all_pairs.lst_minus_air_median_c, 1), lo: fmt(a.all_pairs.lst_minus_air_p10_p90_c[0], 1), hi: fmt(a.all_pairs.lst_minus_air_p10_p90_c[1], 1), n: a.pairs, s: a.stations.length }), "", "margin-top:16px") : "";
  render(pick + kpis +
    '<div class="mapbox" style="margin-bottom:20px"><div id="map" class="map"></div>' + legend(STOPS, " °C", "hc_legend", 1) + "</div>" +
    card("flame", t("hc_hottest", { c: esc(d.name) }), '<div class="tablewrap" style="border:0"><table class="data"><thead><tr><th class="num">#</th><th>' + t("hc_place") + '</th><th class="num">' + t("hc_lst") + '</th><th class="num">' + t("hc_vs") + '</th><th class="num">' + t("trees") + "</th><th>" + t("drivers") + '</th></tr></thead><tbody id="hcRows">' + rows + "</tbody></table></div>" +
      '<p class="tiny muted" style="margin-bottom:0">' + t("hc_note", { km: fmt(d.cells_km, 1), y1: d.lst_years[0], y2: d.lst_years[d.lst_years.length - 1], mae: fmt(d.model.cv_mae_c, 1), base: fmt(d.model.baseline_mae_c, 1) }) + "</p>") + air, hero);
  bindScope();
  $("cityPick").onclick = function (e) { var b = e.target.closest("button[data-city]"); if (!b) return; S.gcity = b.getAttribute("data-city"); citiesView(hero, bindScope); };
  var ctrl = null, mean = function (k) { return d.cells.reduce(function (s, c) { return s + c[k]; }, 0) / d.cells.length; };
  makeMap({ el: "map", center: [mean("lon"), mean("lat")], zoom: 10,
    onClick: function (ll) {
      if (!ctrl) return;
      var f = ctrl.map.queryRenderedFeatures(ctrl.map.project(ll), { layers: ["hcf"] })[0]; if (!f) return;
      var p = f.properties, dr = JSON.parse(p.drivers || "[]");
      popup(ctrl, ll, "<b>" + fmt(p.lst_c) + " °C</b> (" + signed(p.vs_city_c) + " °C " + t("hc_vs_short") + ")<br>" + t("trees") + " " + pct(p.tree) + " · " + t("hc_built") + " " + pct(p.built) + (dr.length ? "<br>" + dr.map(function (z) { return t("drv_" + z); }).join("; ") : ""));
    } }).then(function (c) { ctrl = c; return addCells(c, d.cells, d.cells_km, "vs_city_c", STOPS); }).catch(function () { mapFail("map"); });
  $("hcRows").onclick = function (e) {
    var tr = e.target.closest("tr[data-i]"); if (!tr || !ctrl) return;
    var h = d.hottest[+tr.getAttribute("data-i")]; ctrl.map.flyTo({ center: [h.lon, h.lat], zoom: 13, speed: 1.4 });
  };
}
