/* Delhi ward cooling scenario (government view): turn part of the hottest wards' built-up or bare land into tree cover and
   see the estimated change in surface temperature, by day and by night, with the people covered. Model: /api/gov/scenario.
   "Best use of a budget" asks /api/gov/plan_trees which wards to plant for the most cooling where people live; with a
   rupee budget it can also ask /api/gov/plan_coolroofs which wards' sheet-roof homes to treat. Trees are a ward surface
   temperature and cool roofs an indoor air temperature, so the two are shown side by side and never added. */
import { t } from "../i18n/index.js";
import { esc, fmt, inr, title, $ } from "../util.js";
import { api } from "../api.js";
import { card, callout } from "../ui.js";

var PP = [5, 10, 20, 30], TOP = [10, 20, 50, 0], KM2 = [2, 5, 10, 20], CR = [1, 5, 10, 25], SPLIT = [25, 50, 75],
  GOALS = ["people", "elderly", "vulnerable"], CAP_PP = 20, CRORE = 1e7;
var SC = { mode: "even", pp: 10, from: "built", top: 20, km2: 5, goal: "people", unit: "km2", cr: 5, what: "trees", split: 50 };

function seg(id, opts, cur, label) {
  return '<div class="seg wrap" id="' + id + '" role="group">' + opts.map(function (o) { return '<button type="button" data-v="' + o + '" class="' + (String(o) === String(cur) ? "on" : "") + '" aria-pressed="' + (String(o) === String(cur)) + '">' + label(o) + "</button>"; }).join("") + "</div>";
}
function field(label, html) { return '<div><div class="tiny muted">' + label + "</div>" + html + "</div>"; }
function signed(x) { return (x > 0 ? "+" : "") + fmt(x, 2); }
function crore(x) { return t("sc_cr", { n: fmt(x / CRORE, 2).replace(/\.00$/, "") }); }
function kpi(label, v) { return '<div class="kpi"><div class="l">' + label + '</div><div class="v">' + v + "</div></div>"; }
function src(s) { return ' <a class="tiny" href="' + esc(s.url) + '" target="_blank" rel="noopener">' + esc(s.title) + "</a>"; }
function rupees() { return SC.mode === "plan" && SC.unit === "inr"; }
function trees() { return !rupees() || SC.what !== "roofs"; }

export function scenarioCard() {
  var plan = SC.mode === "plan";
  var body = '<p class="muted" style="margin-top:0">' + t("sc_intro") + "</p>" +
    '<div class="stack" style="gap:10px">' +
    "<div>" + seg("scMode", ["even", "plan"], SC.mode, function (k) { return t("sc_mode_" + k); }) + "</div>" +
    (!plan
      ? field(t("sc_wards"), seg("scTop", TOP, SC.top, function (n) { return n ? t("sc_top", { n: n }) : t("sc_all"); })) +
        field(t("sc_trees"), seg("scPp", PP, SC.pp, function (n) { return "+" + n + " " + t("sc_pp"); }))
      : field(t("sc_unit"), seg("scUnit", ["km2", "inr"], SC.unit, function (k) { return t("sc_unit_" + k); })) +
        (SC.unit === "km2"
          ? field(t("sc_budget"), seg("scKm2", KM2, SC.km2, function (n) { return n + " km²"; }))
          : field(t("sc_budget_inr"), seg("scCr", CR, SC.cr, function (n) { return crore(n * CRORE); })) +
            field(t("sc_what"), seg("scWhat", ["trees", "roofs", "both"], SC.what, function (k) { return t("sc_what_" + k); })) +
            (SC.what === "both" ? field(t("sc_split"), seg("scSplit", SPLIT, SC.split, function (n) { return n + "% / " + (100 - n) + "%"; })) : "")) +
        field(t("sc_goal"), seg("scGoal", GOALS, SC.goal, function (k) { return t("sc_goal_" + k); }))) +
    (trees() ? field(t("sc_from"), seg("scFrom", ["built", "bare"], SC.from, function (k) { return t("sc_from_" + k); })) : "") +
    "</div>" + '<div id="scOut" style="margin-top:16px"></div>';
  return '<div id="scCard">' + card("trend", t("sc_title"), body) + "</div>";
}

export function bindScenario(wards) {
  [["scTop", "top"], ["scPp", "pp"], ["scFrom", "from"], ["scKm2", "km2"], ["scGoal", "goal"], ["scMode", "mode"],
    ["scUnit", "unit"], ["scCr", "cr"], ["scWhat", "what"], ["scSplit", "split"]].forEach(function (x) {
    var box = $(x[0]); if (!box) return;
    box.onclick = function (e) {
      var b = e.target.closest("button[data-v]"); if (!b) return;
      var v = b.getAttribute("data-v"); SC[x[1]] = /^(from|goal|mode|unit|what)$/.test(x[1]) ? v : +v;
      if (/^(mode|unit|what)$/.test(x[1])) { $("scCard").outerHTML = scenarioCard(); return bindScenario(wards); }
      box.querySelectorAll("button").forEach(function (o) { o.classList.toggle("on", o === b); o.setAttribute("aria-pressed", String(o === b)); });
      run(wards);
    };
  });
  run(wards);
}

function treesHtml(d) {
  var s = d.summary, m = d.model, plan = SC.mode === "plan";
  var rows = d.wards.slice().sort(function (a, b) { return a.day_c - b.day_c; }).slice(0, plan ? 40 : 12).map(function (w) {
    return "<tr><td><b>" + esc(title(w.ward_name)) + '</b><div class="tiny muted">' + esc(w.district) + '</div></td><td class="num">' + fmt(w.tree_now * 100, 0) + "% → " + fmt(w.tree_after * 100, 0) + '%</td><td class="num">' + signed(w.day_c) + ' <span class="tiny muted">(' + signed(w.day_band_c[0]) + " … " + signed(w.day_band_c[1]) + ')</span></td><td class="num">' + signed(w.night_c) + "</td></tr>";
  }).join("");
  return '<div class="kpis">' + kpi(t("sc_k_wards"), s.wards) + kpi(t("sc_k_people"), inr(s.pop_total)) + kpi(t("sc_k_65"), inr(s.pop_65plus)) +
    kpi(t("sc_k_area"), fmt(s.area_converted_km2, 1) + " km²") + kpi(t("sc_k_day"), signed(s.day_c_pop_weighted) + " °C") + kpi(t("sc_k_night"), signed(s.night_c_pop_weighted) + " °C") + "</div>" +
    (s.night_c_pop_weighted > 0 ? callout("info", t("sc_night_warm"), "warn", "margin-top:12px") : "") +
    (plan ? '<p class="tiny muted" style="margin:12px 0 0">' + t("sc_plan_note", { cap: CAP_PP, used: fmt(d.area_used_km2, 1), km2: fmt(d.area_km2, 1) }) + "</p>" : "") +
    (plan && d.cost ? '<p style="margin:8px 0 0"><b>' + t("sc_cost", { inr: inr(d.cost.inr), per: inr(d.cost.inr_per_km2) }) + "</b>" + src(d.cost.source) + "</p>" : "") +
    '<div class="tablewrap" style="margin-top:12px"><table class="data"><thead><tr><th>' + t("ward") + '</th><th class="num">' + t("trees") + '</th><th class="num">' + t("sc_col_day") + '</th><th class="num">' + t("sc_col_night") + "</th></tr></thead><tbody>" + rows + "</tbody></table></div>" +
    '<p class="tiny muted" style="margin-bottom:0">' + t("sc_caveat", { day: fmt(m.day.cv_mae_c, 1), night: fmt(m.night.cv_mae_c, 1) }) + "</p>";
}

function roofsHtml(d) {
  var s = d.summary, e = d.effect.indoor_drop_c, c = d.cost;
  var rows = d.wards.slice(0, 40).map(function (w) {
    return "<tr><td><b>" + esc(title(w.ward_name)) + '</b><div class="tiny muted">' + esc(w.district) + '</div></td><td class="num">' + inr(w.homes) + ' <span class="tiny muted">/ ' + inr(w.eligible_homes) + '</span></td><td class="num">' + inr(w.people) + '</td><td class="num">₹' + inr(w.inr) + "</td></tr>";
  }).join("");
  return '<div class="kpis">' + kpi(t("sc_k_wards"), s.wards) + kpi(t("sc_k_homes"), inr(s.homes)) + kpi(t("sc_k_people"), inr(s.people)) +
    kpi(t("sc_k_65"), inr(s.pop_65plus)) + kpi(t("sc_k_indoor"), t("sc_indoor_range", { lo: fmt(e[0], 1), hi: fmt(e[1], 2) })) + "</div>" +
    (s.homes ? "" : callout("info", t("sc_roofs_none"), "warn", "margin-top:12px")) +
    '<p style="margin:12px 0 0"><b>' + t("sc_roof_cost", { inr: inr(c.inr), home: inr(c.inr_per_home), m2: fmt(c.roof_m2, 0), per: inr(c.inr_per_m2) }) + "</b>" + src(c.source) + "</p>" +
    '<div class="tablewrap" style="margin-top:12px"><table class="data"><thead><tr><th>' + t("ward") + '</th><th class="num">' + t("sc_col_homes") + '</th><th class="num">' + t("sc_k_people") + '</th><th class="num">' + t("sc_col_inr") + "</th></tr></thead><tbody>" + rows + "</tbody></table></div>" +
    '<p class="tiny muted" style="margin-bottom:0">' + t("sc_roofs_note", { lo: fmt(e[0], 1), hi: fmt(e[1], 2) }) + src(d.effect.source) + "</p>";
}

function head(k) { return '<h3 style="margin:16px 0 8px">' + t(k) + "</h3>"; }

function runBudget(out) {
  var total = SC.cr * CRORE, share = SC.what === "both" ? SC.split / 100 : SC.what === "trees" ? 1 : 0;
  var tq = share > 0 ? api("/api/gov/plan_trees?budget_inr=" + Math.round(total * share) + "&from=" + SC.from + "&objective=" + SC.goal + "&max_pp=" + CAP_PP) : null;
  var rq = share < 1 ? api("/api/gov/plan_coolroofs?budget_inr=" + Math.round(total * (1 - share)) + "&objective=" + SC.goal) : null;
  return Promise.all([tq, rq]).then(function (r) {
    if (!$("scOut")) return;
    var tr = r[0], rf = r[1], spent = (tr && tr.cost ? tr.cost.inr : 0) + (rf && rf.cost ? rf.cost.inr : 0);
    out.innerHTML = (spent ? '<p style="margin:0"><b>' + t("sc_spent", { used: crore(spent), budget: crore(total) }) + "</b></p>" : "") +
      (tr && rf ? '<p class="tiny muted" style="margin:4px 0 0">' + t("sc_separate") + "</p>" : "") +
      (tr ? head("sc_h_trees") + (tr.missing.length ? callout("info", t("sc_trees_missing"), "warn") : treesHtml(tr)) : "") +
      (rf ? head("sc_h_roofs") + (rf.missing.length ? callout("info", t("sc_roofs_missing"), "warn") : roofsHtml(rf)) : "");
  });
}

function run(wards) {
  var out = $("scOut"); if (!out) return;
  out.innerHTML = '<div class="row"><span class="spin"></span><span>' + t("loading") + "</span></div>";
  var fail = function () { if ($("scOut")) $("scOut").innerHTML = callout("alert", t("net_error"), "warn"); };
  if (rupees()) { runBudget(out).catch(fail); return; }
  var pick = wards.slice().sort(function (a, b) { return a.hvi_rank - b.hvi_rank; });
  if (SC.top) pick = pick.slice(0, SC.top);
  var q = SC.mode === "plan" ? "/api/gov/plan_trees?area_km2=" + SC.km2 + "&from=" + SC.from + "&objective=" + SC.goal + "&max_pp=" + CAP_PP
    : "/api/gov/scenario?tree_pp=" + SC.pp + "&from=" + SC.from + (SC.top ? "&wards=" + pick.map(function (w) { return encodeURIComponent(w.ward_no); }).join(",") : "");
  api(q).then(function (d) { if ($("scOut")) $("scOut").innerHTML = treesHtml(d); }).catch(fail);
}
