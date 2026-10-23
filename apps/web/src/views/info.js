/* #/how (method and models) and #/sources (every data source and verified number) */
import { t } from "../i18n/index.js";
import { I } from "../icons.js";
import { esc, fmt, $ } from "../util.js";
import { api } from "../api.js";
import { render, pageHero, card, skeletonCard, timeline, failBox, bindRetry } from "../ui.js";

export function howView() {
  render('<div class="sheet">' + timeline() + "</div>" +
    '<section class="section"><h2>' + t("models_title") + '</h2><div class="grid g3" id="models">' + skeletonCard(160) + skeletonCard(160) + skeletonCard(160) + "</div></section>" +
    '<section class="section"><div class="grid g2">' + card("list", t("pick_title"), '<ol class="flow">' + [1, 2, 3, 4, 5].map(function (i) { return "<li>" + t("pick_" + i) + "</li>"; }).join("") + "</ol>") +
    '<div class="stack">' + card("shield", t("why_rules_title"), '<p class="muted">' + t("why_rules_d") + "</p>") + card("sparkles", t("ai_title"), '<p class="muted">' + t("ai_d") + "</p>") + "</div></div></section>" +
    '<section class="section">' + card("info", t("limits_title"), '<ul class="bullets">' + [1, 2, 3, 4].map(function (i) { return "<li>" + t("lim_" + i) + "</li>"; }).join("") + '</ul><a class="btn ghost sm" style="margin-top:12px" href="#/sources">' + t("open_sources") + I("arrow-r", "sm") + "</a>") + "</section>", pageHero({ id: "hw", eyebrow: t("nav_how"), title: t("how_title"), sub: t("how_sub"), tip: t("how_tip"), mood: "happy" }));
  api("/api/about").then(function (d) {
    if (!$("models")) return;
    var m = function (v, l) { return '<div class="metric"><b>' + v + "</b><span>" + l + "</span></div>"; };
    $("models").innerHTML = card("home", t("m1_t"), '<p class="muted small">' + t("m1_d") + '</p><div class="metrics">' + m("±" + fmt(d.indoor.mae_c), t("m1_a")) + (d.indoor.rule_mae_c ? m("±" + fmt(d.indoor.rule_mae_c), t("m1_b")) : "") + m(d.indoor.homes, t("m1_c")) + "</div>") +
      card("map", t("m2_t"), '<p class="muted small">' + t("m2_d") + '</p><div class="metrics">' + m(d.districts.n, t("m2_a")) + m(fmt(d.districts.spearman_equal_vs_pca, 2), t("m2_b")) + m((d.districts.years || []).length, t("m2_c")) + "</div>") +
      card("building", t("m3_t"), '<p class="muted small">' + t("m3_d") + '</p><div class="metrics">' + m(fmt(d.wards.r2, 2), t("m3_a")) + m(d.wards.n_wards, t("m3_b")) + "</div>");
  }).catch(function () { if ($("models")) $("models").innerHTML = ""; });
}

/* data caveats for the district ranking and the Delhi ward table (the pipeline writes them in English into the check files) */
var NOTES = ["district_note", "index_note", "dist_note_1", "dist_note_2", "dist_note_3", "dist_note_4", "dist_note_5", "dist_note_6", "gov_note_wards", "gov_note_roofs", "gov_note_hvi"];
function notesList() { return '<ul class="bullets small">' + NOTES.map(function (k) { return "<li>" + t(k) + "</li>"; }).join("") + "</ul>"; }
export function sourcesView() {
  var hero = pageHero({ id: "sr", title: t("sources_title"), sub: t("trust_sourced"), tip: t("src_tip"), mood: "happy" });
  render(skeletonCard(300), hero);
  api("/api/sources").then(function (d) {
    if (location.hash.indexOf("#/sources") !== 0) return;
    var badge = function (st) { var s = String(st || ""); var c = /^Verified|^Done|^Computed/.test(s) ? "low" : /UNVERIFIED|DISPUTED/.test(s) ? "extreme" : /Reported|To verify/.test(s) ? "moderate" : ""; return '<span class="badge ' + c + '">' + esc(s.length > 48 ? s.slice(0, 46) + "…" : s) + "</span>"; };
    var head = function (keys) { return "<thead><tr>" + keys.map(function (k) { return "<th>" + t(k) + "</th>"; }).join("") + "</tr></thead>"; };
    render('<div class="card" style="padding:0;overflow:hidden"><div class="tablewrap" style="border:0;border-radius:0"><table class="data">' + head(["src_col_id", "src_col_source", "src_col_used", "src_col_year", "src_col_licence", "status_label"]) + "<tbody>" +
      d.sources.map(function (s) { var u = (String(s.url).match(/https?:\/\/[^\s;]+/) || [""])[0]; return '<tr><td><span class="rankpill">' + esc(s.id) + "</span></td><td><b>" + esc(s.source) + "</b>" + (u ? '<div class="tiny"><a target="_blank" rel="noopener" href="' + esc(u) + '">' + I("link", "sm") + " " + t("src_link") + "</a></div>" : "") + "</td><td class=\"small\">" + esc(s.used_for) + "</td><td>" + esc(s.year) + '</td><td class="small">' + esc(s.licence) + "</td><td>" + badge(s.status) + "</td></tr>"; }).join("") + "</tbody></table></div></div>" +
      '<section class="section"><h2>' + t("vn_title") + '</h2><p class="muted" style="margin:-6px 0 14px">' + t("vn_sub") + '</p><div class="card" style="padding:0;overflow:hidden"><div class="tablewrap" style="border:0;border-radius:0"><table class="data">' + head(["vn_col_key", "status_label", "src_col_source"]) + "<tbody>" +
      d.verified_numbers.map(function (v) { return '<tr><td class="small"><code>' + esc(v.key) + "</code></td><td>" + badge(v.status) + '</td><td class="small">' + esc(v.source) + "</td></tr>"; }).join("") + "</tbody></table></div></div></section>" +
      '<section class="section">' + card("info", t("notes"), notesList()) + "</section>", hero);
  }).catch(function () { render(failBox(), hero); bindRetry(sourcesView); });
}
