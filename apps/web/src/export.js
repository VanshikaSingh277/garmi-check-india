/* CSV exports of the ranking tables (UTF-8 with BOM so Excel shows Hindi names correctly) */
import { saveCsv } from "./native.js";

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
