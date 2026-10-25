/* "Measure it in your home": a family logs one room reading a day (same time each day) before and after starting a fix.
   Each reading is paired with the outside air for that hour from the forecast the server already has for this spot,
   and the effect is worked out from the indoor-minus-outdoor gap (POST /api/fix_effect), so a hotter week after the fix
   doesn't make it look as if it failed. Readings stay on this device (localStorage); nothing is uploaded. */
import { t } from "../i18n/index.js";
import { I } from "../icons.js";
import { esc, fmt, store, $ } from "../util.js";
import { S } from "../state.js";
import { api } from "../api.js";
import { callout } from "../ui.js";

var KEY = "gc_readings";
function today() { var d = new Date(); return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0"); }
function load() { return store(KEY) || { fix: null, start: null, days: {} }; }
function persist(m) { store(KEY, m); }
function split(m) {
  var before = [], after = [];
  Object.keys(m.days).sort().forEach(function (d) { (m.start && d >= m.start ? after : before).push(m.days[d]); });
  return { before: before, after: after };
}
/* fixes worth measuring: the ones that change the room, not the "lowers your exposure" ones */
function candidates(r) {
  var out = [];
  ["quick", "moderate", "long", "today"].forEach(function (tier) {
    ((r.fixes.fixes || {})[tier] || []).forEach(function (f) { if (["exposure", "harm"].indexOf(f.effect.kind) < 0) out.push(f); });
  });
  return out;
}

export function mountMeasure(el, r) {
  var m = load(), fixes = candidates(r);
  function paint(msg) {
    var s = split(m), fix = fixes.filter(function (f) { return f.id === m.fix; })[0];
    var opts = '<option value="">' + t("measure_pick") + "</option>" + fixes.map(function (f) { return "<option value=\"" + esc(f.id) + "\"" + (f.id === m.fix ? " selected" : "") + ">" + esc(f.title) + "</option>"; }).join("");
    el.innerHTML = '<p class="small muted">' + t("measure_intro") + "</p>" +
      '<label class="field" style="margin-top:12px"><span>' + t("measure_which") + '</span><select class="input" id="mfix">' + opts + "</select></label>" +
      '<div class="row" style="margin-top:12px;gap:8px;align-items:flex-end"><label class="field grow"><span>' + t("measure_reading") + '</span><input class="input" id="mtemp" type="number" inputmode="decimal" step="0.1" min="10" max="55" placeholder="°C"></label>' +
      '<button type="button" class="btn primary" id="msave">' + I("check", "sm") + t("measure_save") + "</button></div>" +
      '<p class="tiny muted" style="margin-top:6px">' + t("measure_time_hint") + "</p>" +
      (m.fix ? (m.start ? '<p class="small" style="margin-top:12px">' + I("clock", "sm") + " " + t("measure_started", { d: esc(m.start) }) + "</p>"
        : '<button type="button" class="btn secondary sm" id="mstart" style="margin-top:12px">' + t("measure_start") + "</button>") : "") +
      '<div class="kpis" style="margin-top:12px"><div class="kpi"><div class="l">' + t("measure_before") + '</div><div class="v">' + s.before.length + '</div></div><div class="kpi"><div class="l">' + t("measure_after") + '</div><div class="v">' + s.after.length + "</div></div></div>" +
      '<div id="mresult" style="margin-top:12px"></div>' + (msg || "") +
      '<p class="tiny muted" style="margin-top:12px">' + I("lock", "sm") + " " + t("measure_private") + (Object.keys(m.days).length ? ' · <button type="button" class="linkbtn" id="mclear">' + t("measure_clear") + "</button>" : "") + "</p>";
    $("mfix").onchange = function () { m = { fix: this.value || null, start: null, days: m.fix === this.value ? m.days : {} }; persist(m); paint(); };
    $("msave").onclick = save;
    if ($("mstart")) $("mstart").onclick = function () { m.start = today(); persist(m); paint(); };
    if ($("mclear")) $("mclear").onclick = function () { m = { fix: m.fix, start: null, days: {} }; persist(m); paint(); };
    if (fix && s.before.length >= 3 && s.after.length >= 3) result(s);
    else if (fix) $("mresult").innerHTML = '<p class="small muted">' + t("measure_need", { b: Math.max(0, 3 - s.before.length), a: Math.max(0, 3 - s.after.length) }) + "</p>";
  }
  function save() {
    var v = parseFloat($("mtemp").value);
    if (!m.fix) return paint(callout("info", t("measure_pick_first")));
    if (isNaN(v) || v < 10 || v > 55) return paint(callout("alert", t("measure_bad_value"), "warn"));
    $("msave").disabled = true;
    api("/api/outdoor?lat=" + S.a.lat + "&lon=" + S.a.lon).then(function (o) {
      m.days[today()] = { indoor_c: v, outdoor_c: o.outdoor_c, time: o.time };   // one reading per day: a second one replaces the first
      persist(m); paint(callout("check", t("measure_saved", { o: fmt(o.outdoor_c, 1) })));
    }).catch(function () { paint(callout("alert", t("net_error"), "warn")); });
  }
  function result(s) {
    api("/api/fix_effect", { before: s.before, after: s.after }).then(function (res) {
      if (!$("mresult")) return;
      $("mresult").innerHTML = res.status === "ok"
        ? callout("thermo", "<b>" + t("measure_result_title") + "</b><br>" + t(res.effect_c >= 0 ? "measure_result_cooler" : "measure_result_warmer", { e: fmt(Math.abs(res.effect_c), 1), lo: fmt(res.range_c[0], 1), hi: fmt(res.range_c[1], 1), b: esc(res.days.before), a: esc(res.days.after) }), "info")
        : "";
    }).catch(function () {});
  }
  paint();
}
