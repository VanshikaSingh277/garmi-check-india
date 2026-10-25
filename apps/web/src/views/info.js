/* #/how: method and models */
import { t } from "../i18n/index.js";
import { esc, fmt, $ } from "../util.js";
import { api } from "../api.js";
import { render, pageHero, card, skeletonCard, timeline } from "../ui.js";

export function howView() {
  render('<div class="sheet">' + timeline() + "</div>" +
    '<section class="section"><h2>' + t("models_title") + '</h2><div class="grid g3" id="models">' + skeletonCard(160) + skeletonCard(160) + skeletonCard(160) + "</div></section>" +
    '<section class="section"><div class="grid g2">' + card("list", t("pick_title"), '<ol class="flow">' + [1, 2, 3, 4, 5].map(function (i) { return "<li>" + t("pick_" + i) + "</li>"; }).join("") + "</ol>") +
    '<div class="stack">' + card("shield", t("why_rules_title"), '<p class="muted">' + t("why_rules_d") + "</p>") + card("sparkles", t("ai_title"), '<p class="muted">' + t("ai_d") + "</p>") + "</div></div></section>" +
    '<section class="section">' + card("info", t("limits_title"), '<ul class="bullets">' + [1, 2, 3, 4].map(function (i) { return "<li>" + t("lim_" + i) + "</li>"; }).join("") + '</ul>') + "</section>", pageHero({ id: "hw", eyebrow: t("nav_how"), title: t("how_title"), sub: t("how_sub"), tip: t("how_tip"), mood: "happy" }));
  api("/api/about").then(function (d) {
    if (!$("models")) return;
    var m = function (v, l) { return '<div class="metric"><b>' + v + "</b><span>" + l + "</span></div>"; };
    $("models").innerHTML = card("home", t("m1_t"), '<p class="muted small">' + t("m1_d") + '</p><div class="metrics">' + m("±" + fmt(d.indoor.mae_c), t("m1_a")) + (d.indoor.rule_mae_c ? m("±" + fmt(d.indoor.rule_mae_c), t("m1_b")) : "") + m(esc(d.indoor.homes), t("m1_c")) + "</div>") +
      card("map", t("m2_t"), '<p class="muted small">' + t("m2_d") + '</p><div class="metrics">' + m(esc(d.districts.n), t("m2_a")) + m(fmt(d.districts.spearman_equal_vs_pca, 2), t("m2_b")) + m((d.districts.years || []).length, t("m2_c")) + "</div>") +
      card("building", t("m3_t"), '<p class="muted small">' + t("m3_d") + '</p><div class="metrics">' + m(fmt(d.wards.r2, 2), t("m3_a")) + m(esc(d.wards.n_wards), t("m3_b")) + "</div>");
  }).catch(function () { if ($("models")) $("models").innerHTML = ""; });
}
