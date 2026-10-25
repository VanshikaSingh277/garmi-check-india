/* cards shared by the personal result, the colony view and the government view */
import { t } from "../i18n/index.js";
import { I } from "../icons.js";
import { esc, fmt, pct, inr, classBadge, classKey } from "../util.js";
import { card } from "../ui.js";

var SOL_IC = { night_ventilation: "window", hydrate_shade: "droplet", cool_roof_coating: "roller", lime_whitewash: "brush", modroof: "layers",
  avoid_translucent_sheets: "ban", cooling_room: "snow", water_points: "tap", outdoor_work_hours: "clock", cool_roof_program: "building",
  fam_vulnerable_care: "heart", fam_fan_limits: "fan", fam_cooler_dry: "droplet", fam_cooler_humid: "droplet", fam_night_fan_pull: "moon",
  fam_outdoor_work: "hardhat", fam_wet_screen: "curtain", fam_external_shade: "sun", fam_roof_insulation: "layers", fam_shade_tree: "sparkles",
  col_buddy_checks: "users", col_bulk_cool_roofs: "roller", col_shade_structures: "sun", col_trees_dense_native: "sparkles",
  col_trees_sparse_ventilated: "sparkles", col_cool_paving: "map", col_water_revival: "droplet", gov_local_alerts: "alert",
  gov_vulnerability_index: "gauge", gov_cool_roof_code: "book", gov_urban_forest: "sparkles" };
var SHOWN_TIERS = ["quick", "moderate", "long"];
/* "because" lines from the server, minus the generic ones that every fix in the list would carry */
function because(f) {
  return (f.because || []).filter(function (b) { return b.code !== "always" && b.code !== "heat_level"; })
    .map(function (b) { return '<span class="badge ' + (b.code === "avoid_harm" ? "extreme" : "primary") + '">' + esc(b.text) + "</span>"; }).join("");
}
function body(f) {
  var e = f.effect || {};
  return '<div class="body">' + (f.steps && f.steps.length ? '<ul class="steps">' + f.steps.map(function (x) { return "<li>" + esc(x) + "</li>"; }).join("") + "</ul>" : "") +
    (f.caution ? '<p class="caution">' + I("alert", "sm") + esc(f.caution) + "</p>" : "") +
    (e.text ? "<p><b>" + t("effect") + ":</b> " + esc(e.text) + (e.note ? " " + esc(e.note) : "") + "</p>" : "") +
    (f.cost_text ? "<p><b>" + t("cost") + ":</b> " + esc(f.cost_text) + (/^UNVERIFIED/.test(f.cost_status || "") ? " (" + t("not_verified") + ")" : "") + "</p>" : "") +
    (f.time ? "<p><b>" + t("time") + ":</b> " + esc(f.time) + (f.who ? " · " + esc(f.who) : "") + "</p>" : "") + "</div>";
}
function fixCard(f, avoid) {
  return '<details class="fix' + (avoid ? " avoid" : "") + '"><summary><span class="ic">' + I(SOL_IC[f.id] || "check") + '</span><div class="grow"><div class="t">' + esc(f.title) +
    (!avoid ? ' <span class="badge">' + t("tier_" + f.cost) + "</span>" : "") + '</div><div class="badges why">' + because(f) + "</div></div>" + I("chev-r", "chev") + "</summary>" + body(f) + "</details>";
}
/* today's actions for this home, from today's forecast and the family's answers */
export function todayCard(fx) {
  var list = (fx && fx.fixes && fx.fixes.today) || [];
  if (!list.length) return "";
  return '<div class="card today"><div class="card-h"><div class="ic">' + I("sun") + "</div><h3>" + t("today_title") + '</h3></div><p class="tiny muted" style="margin:-6px 0 12px">' + t("today_sub") + "</p>" +
    list.map(function (f) { return fixCard(f); }).join("") + "</div>";
}
/* the fix list: quick wins, this season, long term, what to avoid, and what was left out and why */
export function fixesBlock(fx) {
  var html = "", F = (fx && fx.fixes) || {};
  SHOWN_TIERS.forEach(function (tr) { var g = F[tr] || []; if (g.length) html += '<div class="tiergroup"><h4>' + t("tier_" + tr) + "</h4>" + g.map(function (x) { return fixCard(x); }).join("") + "</div>"; });
  if (F.today && fx.category !== "family") html = (F.today.length ? '<div class="tiergroup"><h4>' + t("today_title") + "</h4>" + F.today.map(function (x) { return fixCard(x); }).join("") + "</div>" : "") + html;
  if (F.avoid && F.avoid.length) html += '<div class="tiergroup"><h4>' + t("avoid") + "</h4>" + F.avoid.map(function (x) { return fixCard(x, true); }).join("") + "</div>";
  var ex = (fx && fx.excluded) || [];
  if (ex.length) html += '<details class="acc" style="margin-top:16px"><summary>' + I("eye-off") + t("skipped_title") + I("chev-r", "chev") + '</summary><div class="body"><ul class="skipped">' +
    ex.map(function (x) { return "<li>" + I(SOL_IC[x.id] || "x", "sm") + "<div><b>" + esc(x.title) + "</b> — " + esc(x.reason.text) + "</div></li>"; }).join("") + "</ul></div></details>";
  return html;
}
export function districtCard(dh, mapId) {
  if (!dh) return "";
  return '<div class="card"><div class="card-h"><div class="ic">' + I("map") + "</div><h3>" + t("your_district") + ": " + esc(dh.district) + '</h3><span class="badge ' + classBadge(dh.hx_class) + '">' + t(classKey(dh.hx_class)) + "</span></div>" +
    (mapId ? '<div class="mapbox" style="margin-bottom:14px;box-shadow:none"><div class="map mini" id="' + mapId + '"></div></div>' : "") +
    '<div class="kpis"><div class="kpi"><div class="l">' + t("summer_tmax") + '</div><div class="v">' + fmt(dh.tmax_mean_c) + '<small>°C</small></div></div><div class="kpi"><div class="l">' + t("summer_tmin") + '</div><div class="v">' + fmt(dh.tmin_mean_c) + "<small>°C</small></div></div>" +
    '<div class="kpi"><div class="l">' + t("summer_twb") + '</div><div class="v">' + fmt(dh.twb_max_mean_c) + '<small>°C</small></div></div><div class="kpi"><div class="l">' + t("hot_days40") + '</div><div class="v">' + fmt(dh.days_tmax_ge40, 0) + "</div></div></div>" +
    '<div style="margin-top:10px"><div class="kv"><span>' + t("share65") + "</span><b>" + pct(dh.share_65plus) + '</b></div><div class="kv"><span>' + t("share_u5") + "</span><b>" + pct(dh.share_under5) + '</b></div><div class="kv"><span>' + t("pop_label") + "</span><b>" + inr(dh.pop_total) + '</b></div><div class="kv"><span>' + t("index_label") + "</span><b>" + t("index_rank", { r: Math.round(dh.hx_rank), n: esc(dh.n_india) || "" }) + "</b></div></div>" +
    "</div>";
}
export function wardCard(w) {
  if (!w) return "";
  return card("building", t("delhi_ward_title") + " — " + esc(w.ward), '<div class="kpis"><div class="kpi"><div class="l">' + t("surface_heat") + '</div><div class="v">' + fmt(w.lst_day_c) + '<small>°C</small></div><div class="s">' + t("hotter_than", { p: Math.round((w.lst_day_pct || 0) * 100) }) + '</div></div><div class="kpi"><div class="l">' + t("night_ground") + '</div><div class="v">' + fmt(w.lst_night_c) + "<small>°C</small></div></div></div>" +
    (w.drivers && w.drivers.length ? '<p class="small" style="margin-top:12px"><b>' + t("why_hot") + ":</b> " + w.drivers.map(function (d) { return t("drv_" + d.code); }).join(" · ") + "</p>" : ""));
}
