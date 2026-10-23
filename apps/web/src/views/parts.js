/* cards shared by the personal result, the colony view and the government view */
import { t } from "../i18n/index.js";
import { I } from "../icons.js";
import { esc, fmt, pct, inr, classBadge, classKey } from "../util.js";
import { card } from "../ui.js";

var SOL_IC = { night_ventilation: "moon", hydrate_shade: "droplet", cool_roof_coating: "roller", lime_whitewash: "brush", modroof: "layers", avoid_translucent_sheets: "ban", cooling_room: "snow", water_points: "tap", outdoor_work_hours: "clock", cool_roof_program: "building" };
function whyChips(s) {
  return (s.why || []).map(function (w) {
    if (w.indexOf("roof:") === 0) return '<span class="badge primary">' + I("home", "sm") + t("why_roof") + ": " + esc(t("roof_" + w.slice(5))) + "</span>";
    if (w === "roof_access") return '<span class="badge primary">' + I("check", "sm") + t("why_roof_access") + "</span>";
    if (w === "avoid_harm") return '<span class="badge extreme">' + I("alert", "sm") + t("why_avoid_harm") + "</span>";
    return "";
  }).join("");
}
function fixCard(s, avoid) {
  return '<details class="fix' + (avoid ? " avoid" : "") + '"><summary><span class="ic">' + I(SOL_IC[s.id] || "check") + '</span><div class="grow"><div class="t">' + esc(s.name) + '</div><div class="w">' + esc(s.what) + '</div><div class="badges why">' + whyChips(s) + "</div></div>" + I("chev-r", "chev") + "</summary>" +
    '<div class="body">' + (s.effect ? "<p><b>" + t("effect") + ":</b> " + esc(s.effect) + "</p>" : "") +
    (s.cost && s.cost !== "—" ? "<p><b>" + t("cost") + ":</b> " + esc(s.cost) + (s.cost_status && s.cost_status.indexOf("UNVERIFIED") === 0 ? " (" + t("not_verified") + ")" : "") + "</p>" : "") +
    (s.time && s.time !== "—" ? "<p><b>" + t("time") + ":</b> " + esc(s.time) + " · " + esc(s.who) + "</p>" : "") + "</div></details>";
}
export function fixesBlock(sol, sections) {
  var html = "", tiers = ["free", "low", "medium", "high"];
  var items = [].concat(sol.free || [], sol.cooling || []);
  if (sections.indexOf("health") >= 0) items = items.concat(sol.health || []);
  tiers.forEach(function (tr) { var g = items.filter(function (x) { return x.tier === tr; }); if (g.length) html += '<div class="tiergroup"><h4>' + t("tier_" + tr) + "</h4>" + g.map(function (x) { return fixCard(x); }).join("") + "</div>"; });
  var other = items.filter(function (x) { return tiers.indexOf(x.tier) < 0; });
  if (other.length) html += '<div class="tiergroup">' + other.map(function (x) { return fixCard(x); }).join("") + "</div>";
  if (sol.avoid && sol.avoid.length) html += '<div class="tiergroup"><h4>' + t("avoid") + "</h4>" + sol.avoid.map(function (x) { return fixCard(x, true); }).join("") + "</div>";
  if (sol.skipped && sol.skipped.length) html += '<details class="acc" style="margin-top:16px"><summary>' + I("eye-off") + t("skipped_title") + I("chev-r", "chev") + '</summary><div class="body"><ul class="skipped">' +
    sol.skipped.map(function (x) { return "<li>" + I(SOL_IC[x.id] || "x", "sm") + "<div><b>" + esc(x.name) + "</b> — " + t("skip_" + x.reason) + "</div></li>"; }).join("") + "</ul></div></details>";
  return html;
}
export function districtCard(dh, mapId) {
  if (!dh) return "";
  return '<div class="card"><div class="card-h"><div class="ic">' + I("map") + "</div><h3>" + t("your_district") + ": " + esc(dh.district) + '</h3><span class="badge ' + classBadge(dh.hx_class) + '">' + t(classKey(dh.hx_class)) + "</span></div>" +
    (mapId ? '<div class="mapbox" style="margin-bottom:14px;box-shadow:none"><div class="map mini" id="' + mapId + '"></div></div>' : "") +
    '<div class="kpis"><div class="kpi"><div class="l">' + t("summer_tmax") + '</div><div class="v">' + fmt(dh.tmax_mean_c) + '<small>°C</small></div></div><div class="kpi"><div class="l">' + t("summer_tmin") + '</div><div class="v">' + fmt(dh.tmin_mean_c) + "<small>°C</small></div></div>" +
    '<div class="kpi"><div class="l">' + t("summer_twb") + '</div><div class="v">' + fmt(dh.twb_max_mean_c) + '<small>°C</small></div></div><div class="kpi"><div class="l">' + t("hot_days40") + '</div><div class="v">' + fmt(dh.days_tmax_ge40, 0) + "</div></div></div>" +
    '<div style="margin-top:10px"><div class="kv"><span>' + t("share65") + "</span><b>" + pct(dh.share_65plus) + '</b></div><div class="kv"><span>' + t("share_u5") + "</span><b>" + pct(dh.share_under5) + '</b></div><div class="kv"><span>' + t("pop_label") + "</span><b>" + inr(dh.pop_total) + '</b></div><div class="kv"><span>' + t("index_label") + "</span><b>" + t("index_rank", { r: Math.round(dh.hx_rank), n: dh.n_india || "" }) + "</b></div></div>" +
    "</div>";
}
export function wardCard(w) {
  if (!w) return "";
  return card("building", t("delhi_ward_title") + " — " + esc(w.ward), '<div class="kpis"><div class="kpi"><div class="l">' + t("surface_heat") + '</div><div class="v">' + fmt(w.lst_day_c) + '<small>°C</small></div><div class="s">' + t("hotter_than", { p: Math.round((w.lst_day_pct || 0) * 100) }) + '</div></div><div class="kpi"><div class="l">' + t("night_ground") + '</div><div class="v">' + fmt(w.lst_night_c) + "<small>°C</small></div></div></div>" +
    (w.drivers && w.drivers.length ? '<p class="small" style="margin-top:12px"><b>' + t("why_hot") + ":</b> " + w.drivers.map(function (d) { return t("drv_" + d.code); }).join(" · ") + "</p>" : ""));
}
