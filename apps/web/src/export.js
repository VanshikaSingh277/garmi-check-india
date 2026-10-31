/* Exports of the ranking tables: CSV (UTF-8 with BOM so Excel shows Hindi names correctly), GeoJSON for GIS tools,
   and a printable one-page sheet per Delhi ward for a heat action plan annex */
import { saveCsv, saveFile } from "./native.js";
import { NATIVE } from "./config.js";
import { t } from "./i18n/index.js";
import { esc, fmt, title } from "./util.js";

function csv(name, rows) {
  saveCsv(name, "﻿" + rows.map(function (r) { return r.map(function (x) { var v = String(x == null ? "" : x); if (typeof x === "string" && /^[=+\-@\t\r]/.test(v)) v = "'" + v; return '"' + v.replace(/"/g, '""') + '"'; }).join(","); }).join("\n")).catch(function () {});
}
export function districtCsv(rows) {
  csv("india_district_heat_priorities.csv", [["rank", "district", "state", "index", "class", "summer_tmax_c", "summer_tmin_c", "wetbulb_max_c", "days_ge40", "share_65plus", "share_under5", "population_2025"]]
    .concat(rows.map(function (x) { return [Math.round(x.hx_rank), x.district, x.state, x.hx_index, x.hx_class, x.tmax_mean_c, x.tmin_mean_c, x.twb_max_mean_c, x.days_tmax_ge40, x.share_65plus, x.share_under5, x.pop_total]; })));
}
export function wardCsv(rows) {
  csv("delhi_ward_heat_priorities.csv", [["rank", "ward", "district", "hvi", "lst_day", "lst_night", "tree_frac", "pop_65plus"]]
    .concat(rows.map(function (w) { return [w.hvi_rank, w.ward_name, w.district, w.hvi, w.lst_day_mean_c, w.lst_night_mean_c, w.frac_tree, w.pop_65plus]; })));
}

var DIST_KEYS = ["id", "district", "state", "hx_rank", "hx_index", "hx_class", "tmax_mean_c", "tmin_mean_c", "twb_max_mean_c", "days_tmax_ge40", "share_65plus", "share_under5", "pop_total", "no_data"];
var WARD_KEYS = ["ward_no", "ward_name", "district", "hvi_rank", "hvi", "hvi_class", "lst_day_mean_c", "lst_night_mean_c", "frac_tree", "frac_built", "pop_total", "pop_65plus"];
function geojson(name, features, keys) {
  var fc = { type: "FeatureCollection", features: features.map(function (f) {
    var p = {}; keys.forEach(function (k) { if (f.properties[k] !== undefined) p[k] = f.properties[k]; });
    return { type: "Feature", properties: p, geometry: f.geometry };
  }) };
  saveFile(name, JSON.stringify(fc), "application/geo+json").catch(function () {});
}
export function districtGeojson(features) { geojson("india_district_heat_priorities.geojson", features, DIST_KEYS); }
export function wardGeojson(features) { geojson("delhi_ward_heat_priorities.geojson", features, WARD_KEYS); }

/* One ward on one page. The scenario row comes from /api/gov/scenario; numbers are printed as the API returns them. */
export function wardSheet(w, total, sc, lang, win) {  // win: opened by the click itself, so pop-up blockers allow it
  var row = function (k, v) { return "<tr><th>" + k + "</th><td>" + v + "</td></tr>"; };
  var signed = function (x) { return (x > 0 ? "+" : "") + fmt(x, 2); };
  var html = '<!doctype html><html lang="' + lang + '"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>' + esc(title(w.ward_name)) + "</title>" +
    "<style>body{font:15px/1.5 system-ui,sans-serif;max-width:720px;margin:24px auto;padding:0 16px;color:#111}h1{margin:0 0 4px}table{border-collapse:collapse;width:100%;margin:12px 0}th,td{text-align:left;padding:6px 8px;border-bottom:1px solid #ddd;vertical-align:top}th{width:45%;font-weight:600}.muted{color:#555;font-size:13px}@media print{body{margin:0}}</style></head><body>" +
    "<h1>" + esc(title(w.ward_name)) + '</h1><div class="muted">' + esc(w.district) + " · " + t("ward") + " " + esc(w.ward_no) + "</div>" +
    "<h2>" + t("sheet_heat") + "</h2><table>" +
    row(t("sheet_rank"), "#" + fmt(w.hvi_rank, 0) + " / " + total + " · HVI " + fmt(w.hvi, 2)) +
    row(t("day"), fmt(w.lst_day_mean_c)) + row(t("night"), fmt(w.lst_night_mean_c)) +
    row(t("trees"), fmt((w.frac_tree || 0) * 100, 0) + "%") +
    row(t("sheet_people"), fmt(w.pop_total, 0) + " · " + t("elderly65") + " " + fmt(w.pop_65plus, 0)) +
    row(t("drivers"), (w.drivers || []).map(function (z) { return t("drv_" + z.code); }).join("; ") || "–") + "</table>" +
    (sc ? "<h2>" + t("sheet_scenario", { pp: sc.pp }) + "</h2><table>" +
      row(t("sc_col_day"), signed(sc.row.day_c) + " (" + signed(sc.row.day_band_c[0]) + " … " + signed(sc.row.day_band_c[1]) + ")") +
      row(t("sc_col_night"), signed(sc.row.night_c)) + "</table>" + '<p class="muted">' + t("sc_caveat", { day: fmt(sc.model.day.cv_mae_c, 1), night: fmt(sc.model.night.cv_mae_c, 1) }) + "</p>" : "") +
    '<p class="muted">' + t("sheet_source") + "</p></body></html>";
  var name = "ward_" + String(w.ward_no).replace(/[^A-Za-z0-9_]/g, "") + "_heat_sheet.html";
  if (NATIVE) return saveFile(name, html, "text/html").catch(function () {});
  if (!win) return saveFile(name, html, "text/html");
  win.document.write(html); win.document.close(); win.focus(); win.print();
}
