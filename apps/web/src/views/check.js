/* #/me - the personal check: four questions (place, roof, people, cooling), then the result with the hour-by-hour plan */
import { t } from "../i18n/index.js";
import { I, ART } from "../icons.js";
import { esc, fmt, hm, ranges, store, $ } from "../util.js";
import { S, save, LEVELS } from "../state.js";
import { api } from "../api.js";
import { render, root, pageHero, moodOf, card, skeletonCard, callout, bindRetry } from "../ui.js";
import { makeMap, mapTools, bindTools, mapFail } from "../map.js";
import { placeBlock, locCard, setLoc, refreshWhere, searchBox, bindSearch, bindGps, needsRefresh } from "../place.js";
import { fixesBlock, todayCard, districtCard, wardCard } from "./parts.js";

var STEPS = ["st_place", "st_roof", "st_people", "st_cooling"];
function stepper(n) { return '<div class="stepper">' + STEPS.map(function (k, i) { return '<div class="s' + (i <= n ? " on" : "") + (i === n ? " cur" : "") + '"' + (i === n ? ' aria-current="step"' : "") + "><i></i><span>" + (i + 1) + ". " + t(k) + "</span></div>"; }).join("") + "</div>"; }
function opt(v, art, k, desc, on, multi) { return '<button type="button" class="opt' + (multi ? " multi" : "") + (on ? " on" : "") + '" data-v="' + v + '" aria-pressed="' + (on ? "true" : "false") + '"><span class="art">' + art + "</span><span class=\"grow\"><b>" + t(k) + "</b>" + (desc ? '<span class="d">' + t(desc) + "</span>" : "") + '</span><span class="tick">' + I("check", "sm") + "</span></button>"; }
function actionbar(backOk, nextLabel, nextDisabled) { return '<div class="actionbar"><button type="button" class="btn secondary" id="bk"' + (backOk ? "" : " disabled") + ' aria-label="' + esc(t("back")) + '">' + I("arrow-l") + '<span class="hide-sm">' + t("back") + '</span></button><button type="button" class="btn primary" id="nx"' + (nextDisabled ? " disabled" : "") + ">" + nextLabel + I("arrow-r") + "</button></div>"; }

export function flowStep() {
  var a = S.a, app = root(), hero = pageHero({ id: "fm", title: t("flow_title"), extra: stepper(S.step), tip: t("flow_tip_" + S.step), mood: "happy" });
  /* the matka comments on each answer; the roof facts are the measured Delhi offsets (verified_numbers: roof.offset.*) */
  function say(k) { var b = $("bubble"); if (b) b.innerHTML = t(k); }
  function paint(isOn) { app.querySelectorAll(".opt").forEach(function (b) { var on = isOn(b.getAttribute("data-v")); b.classList.toggle("on", on); b.setAttribute("aria-pressed", on ? "true" : "false"); }); }
  if (S.step === 0) {
    render('<div class="layout even"><div class="mapbox"><div id="map" class="map" role="application" aria-label="' + esc(t("q_location")) + '"></div>' + mapTools("lt") + "</div>" +
      '<div class="stack"><div class="card"><h3 style="margin-bottom:12px">' + t("q_location") + '</h3><button type="button" class="btn primary block" id="gps">' + I("locate") + t("use_gps") + '</button><div class="statusline" id="gpsmsg" style="margin-top:10px"></div><div id="loccard" style="margin-top:14px">' + locCard() + "</div></div>" +
      '<div class="card"><div class="field"><span>' + t("or_pick") + "</span>" + searchBox("q") + '</div><p class="tiny muted" style="margin-top:10px">' + t("tap_to_move") + "</p></div></div></div>" +
      actionbar(false, t("confirm_loc"), a.lat == null || (a.where && a.where.in_india === false)), hero);
    var ctrl = null;
    makeMap({ el: "map", center: a.lat != null ? [a.lon, a.lat] : null, zoom: a.lat != null ? 12 : null, wards: "lines",
      onClick: function (ll) { setLoc(ll.lat, ll.lng, "map", null, ctrl, false); }, drag: function (ll) { setLoc(ll.lat, ll.lng, "map", null, ctrl, false); } })
      .then(function (c) { ctrl = c; bindTools("lt", c); if (a.lat != null) { c.pin(a.lat, a.lon, a.acc, false); if (a.where) c.select(a.where.district_heat && a.where.district_heat.id, a.where.ward && a.where.ward.ward_no); } })
      .catch(function () { mapFail("map"); });
    bindGps("gps", "gpsmsg", function () { return ctrl; });
    bindSearch("q", function (it) { setLoc(it.lat, it.lon, "search", null, ctrl, true); });
    if (needsRefresh()) refreshWhere();
  } else if (S.step === 1) {
    render('<div class="sheet"><h2>' + t("q_roof") + '</h2><div class="options">' + ["tin_top", "asbestos_top", "stone_slab_top", "rcc_brick_top", "lower_floor"].map(function (v) { return opt(v, ART(v), "roof_" + v, "roof_d_" + v, a.roof === v); }).join("") + "</div></div>" + actionbar(true, t("continue"), !a.roof), hero);
    if (a.roof) say("react_roof_" + a.roof);
    app.querySelectorAll(".opt").forEach(function (b) { b.onclick = function () {
      a.roof = b.getAttribute("data-v"); save(); paint(function (v) { return v === a.roof; }); $("nx").disabled = false; say("react_roof_" + a.roof);
    }; });
  } else if (S.step === 2) {
    var ppl = [["elderly", "elder", "p_elderly"], ["child", "baby", "p_child"], ["pregnant", "pregnant", "p_pregnant"], ["chronic", "heart", "p_chronic"], ["outdoor_worker", "hardhat", "p_outdoor_worker"], ["none", "smile", "p_none"]];
    var pOn = function (v) { return v === "none" ? a.vulnerable.length === 0 : a.vulnerable.indexOf(v) >= 0; };
    render('<div class="sheet"><h2>' + t("q_people") + '</h2><div class="options three">' + ppl.map(function (o) { return opt(o[0], I(o[1]), o[2], null, pOn(o[0]), true); }).join("") + "</div></div>" + actionbar(true, t("continue")), hero);
    app.querySelectorAll(".opt").forEach(function (b) { b.onclick = function () {
      var v = b.getAttribute("data-v"); if (v === "none") a.vulnerable = []; else { var i = a.vulnerable.indexOf(v); if (i >= 0) a.vulnerable.splice(i, 1); else a.vulnerable.push(v); }
      save(); paint(pOn); say(a.vulnerable.length ? "react_people" : "react_people_none");
    }; });
  } else {
    var d = a.devices, dev = [["fan", "fan", "d_fan"], ["cooler", "droplet", "d_cooler"], ["ac", "snow", "d_ac"], ["none", "ban", "d_none"]];
    var dOn = function (v) { return v === "none" ? !(d.fan || d.cooler || d.ac) : !!d[v]; };
    render('<div class="sheet"><h2>' + t("q_cooling") + '</h2><div class="options">' + dev.map(function (o) { return opt(o[0], I(o[1]), o[2], null, dOn(o[0]), true); }).join("") + "</div>" +
      (a.roof !== "lower_floor" ? '<div class="row between qrow"><b>' + t("q_roof_access") + '</b><div class="seg lg" id="ra"><button type="button" data-ra="1" class="' + (a.roof_access ? "on" : "") + '">' + t("yes") + '</button><button type="button" data-ra="0" class="' + (!a.roof_access ? "on" : "") + '">' + t("no") + "</button></div></div>" : "") +
      '<div class="row between qrow"><div><b>' + t("q_cross_vent") + '</b><div class="tiny muted">' + t("q_cross_vent_d") + '</div></div><div class="seg lg"><button type="button" data-cv="1" class="' + (a.cross_ventilation === true ? "on" : "") + '">' + t("yes") + '</button><button type="button" data-cv="0" class="' + (a.cross_ventilation === false ? "on" : "") + '">' + t("no_plain") + "</button></div></div>" +
      '<div class="qrow"><b>' + t("q_budget") + '</b><div class="tiny muted">' + t("q_budget_d") + '</div><div class="chips pick" style="margin-top:10px">' +
      ["free", "low", "medium", "high"].map(function (v) { return '<button type="button" class="chip' + (a.budget === v ? " on" : "") + '" data-bd="' + v + '" aria-pressed="' + (a.budget === v) + '">' + t("budget_" + v) + "</button>"; }).join("") + "</div></div>" +
      "</div>" + actionbar(true, t("see_status")), hero);
    app.querySelectorAll(".opt").forEach(function (b) { b.onclick = function () {
      var v = b.getAttribute("data-v"); if (v === "none") { a.devices = {}; d = a.devices; } else d[v] = !d[v];
      save(); paint(dOn); say(v === "none" ? "react_dev_none" : !d[v] ? "react_ok" : "react_dev_" + v);
    }; });
    app.querySelectorAll("[data-ra]").forEach(function (b) { b.onclick = function () {
      a.roof_access = b.getAttribute("data-ra") === "1"; save();
      app.querySelectorAll("[data-ra]").forEach(function (x) { x.classList.toggle("on", x === b); }); say(a.roof_access ? "react_roof_access" : "react_ok");
    }; });
    app.querySelectorAll("[data-cv]").forEach(function (b) { b.onclick = function () {
      a.cross_ventilation = b.getAttribute("data-cv") === "1"; save();
      app.querySelectorAll("[data-cv]").forEach(function (x) { x.classList.toggle("on", x === b); }); say(a.cross_ventilation ? "react_ok" : "react_no_breeze");
    }; });
    app.querySelectorAll("[data-bd]").forEach(function (b) { b.onclick = function () {
      a.budget = b.getAttribute("data-bd"); save();
      app.querySelectorAll("[data-bd]").forEach(function (x) { x.classList.toggle("on", x === b); x.setAttribute("aria-pressed", String(x === b)); }); say("react_budget");
    }; });
  }
  $("bk").onclick = function () { S.step = Math.max(0, S.step - 1); flowStep(); };
  $("nx").onclick = function () {
    if (S.step === 0 && (a.lat == null || (a.where && a.where.in_india === false))) return;
    if (S.step === 1 && !a.roof) return;
    if (S.step < 3) { S.step++; flowStep(); } else submit();
  };
}
function submit() {
  var hero = pageHero({ id: "fm", title: t("flow_title"), tip: t("loading"), mood: "happy" });
  render('<div class="card"><div class="row"><span class="spin"></span><span>' + t("loading") + "</span></div></div>" + skeletonCard(160) + "<br>" + skeletonCard(220), hero);
  var a = S.a;
  api("/api/status/individual", { lat: a.lat, lon: a.lon, roof: a.roof, vulnerable: a.vulnerable, devices: { fan: !!a.devices.fan, cooler: !!a.devices.cooler, ac: !!a.devices.ac }, roof_access: a.roof_access, cross_ventilation: a.cross_ventilation, budget: a.budget, lang: S.lang })
    .then(function (r) { S.result = r; S.step = 9; store("gc_last", { at: new Date().toISOString(), r: r }); resultView(); })
    .catch(function () {
      /* offline: show the last result we have, clearly labelled with its time */
      var last = store("gc_last");
      if (last) { S.result = last.r; S.result._offline = last.at; S.step = 9; resultView(); }
      else { render(callout("alert", t("net_error") + ' <button class="btn sm secondary" type="button" data-retry>' + t("retry") + "</button>", "warn"), hero); bindRetry(submit); }
    });
}

/* ---------- result ---------- */
function gaugeSVG(idx) {
  var cx = 120, cy = 118, r = 92, cols = ["--low", "--mod", "--high", "--ext"], out = "";
  function pt(a) { var q = a * Math.PI / 180; return (cx + r * Math.cos(q)).toFixed(1) + " " + (cy - r * Math.sin(q)).toFixed(1); }
  for (var i = 0; i < 4; i++) out += '<path d="M' + pt(180 - i * 45 - 3) + " A" + r + " " + r + " 0 0 1 " + pt(180 - (i + 1) * 45 + 3) + '" style="stroke:var(' + cols[i] + ");opacity:" + (i === idx ? 1 : 0.22) + '" stroke-width="20" fill="none" stroke-linecap="round"/>';
  /* the needle is drawn pointing up and rotated into place, so CSS can swing it in from "low" */
  return '<svg class="gauge" viewBox="0 0 240 132" role="img" aria-label="' + esc(t("level_" + LEVELS[idx])) + '">' + out + '<g class="needle" style="--a:' + (idx * 45 + 22.5 - 90) + 'deg"><line x1="' + cx + '" y1="' + cy + '" x2="' + cx + '" y2="' + (cy - (r - 36)) + '" style="stroke:var(--ink)" stroke-width="5" stroke-linecap="round"/></g><circle cx="' + cx + '" cy="' + cy + '" r="9" style="fill:var(--ink)"/></svg>';
}
function reasonText(r) { return t("reason_" + r.code, { v: Array.isArray(r.value) ? r.value.join(", ") : r.value, t: r.threshold }); }
function planView(r) {
  var p = r.plan, hasIn = p.basis === "indoor", hot = {};
  (p.hottest || []).forEach(function (h) { hot[h] = 1; });
  var chips = "";
  if (hasIn) {
    if (p.open.length) chips += '<span class="planchip open">' + I("window", "sm") + t("plan_open", { r: ranges(p.open) }) + "</span>";
    if (p.close.length) chips += '<span class="planchip shut">' + I("curtain", "sm") + t("plan_close", { r: ranges(p.close) }) + "</span>";
  }
  if (p.fan_avoid.length) chips += '<span class="planchip bad">' + I("fan", "sm") + t("plan_fan_avoid", { r: ranges(p.fan_avoid) }) + "</span>";
  if (p.fan_not_enough.length) chips += '<span class="planchip warn">' + I("fan", "sm") + t("plan_fan_ne", { r: ranges(p.fan_not_enough) }) + "</span>";
  if (!p.fan_avoid.length && !p.fan_not_enough.length) chips += '<span class="planchip ok">' + I("fan", "sm") + t("plan_fan_ok") + "</span>";
  if (p.hottest.length) chips += '<span class="planchip hot">' + I("flame", "sm") + t(hasIn ? "plan_hottest" : "plan_hottest_out", { r: p.hottest.join(", ") }) + "</span>";
  var H = p.hours, row = function (label, cells) { return "<tr><th>" + label + "</th>" + cells + "</tr>"; };
  var grid = '<div class="hourgrid"><table>' +
    row("", H.map(function (h) { return '<td class="time">' + h.time.slice(11, 13) + "</td>"; }).join("")) +
    row(t("row_out"), H.map(function (h) { return "<td>" + fmt(h.outdoor, 0) + "</td>"; }).join("")) +
    (hasIn ? row(t("row_room"), H.map(function (h) { return '<td class="' + (hot[hm(h.time)] ? "hot" : "") + '">' + fmt(h.indoor, 0) + "</td>"; }).join("")) +
      row(t("row_window"), H.map(function (h) { return '<td class="w-' + h.window + '" title="' + esc(t("w_" + h.window)) + '">' + (h.window === "open" ? I("window", "sm") : h.window === "close" ? I("curtain", "sm") : "–") + "</td>"; }).join("")) : "") +
    row(t("row_fan"), H.map(function (h) { var c = h.fan === "fan_helps" ? "f-ok" : h.fan === "fan_not_enough_alone" ? "f-ne" : "f-avoid"; return '<td class="' + c + '" title="' + esc(t(h.fan)) + '">' + I("fan", "sm") + "</td>"; }).join("")) + "</table></div>";
  var leg = '<div class="legendrow">' + (hasIn ? '<span><i style="background:var(--primary-soft);border:1px solid var(--primary)"></i>' + t("w_open") + '</span><span><i style="background:var(--surface-3)"></i>' + t("w_close") + "</span>" : "") +
    '<span><i style="background:var(--low-soft);border:1px solid var(--low)"></i>' + t("leg_helps") + '</span><span><i style="background:var(--mod-soft);border:1px solid var(--mod)"></i>' + t("leg_ne") + '</span><span><i style="background:var(--ext-soft);border:1px solid var(--ext)"></i>' + t("leg_avoid") + "</span></div>";
  return '<div class="planchips">' + chips + "</div>" + grid + leg + '<div class="callout ' + (hasIn ? "info" : "warn") + '" style="margin-top:14px">' + I(hasIn ? "info" : "alert") + "<div>" + t(hasIn ? "plan_note" : "plan_no_windows") + "</div></div>";
}
/* hover or drag across the temperature chart to read any hour */
var CHART = null;
function chartSVG(hours, outdoor, fan) {
  var hasIn = hours && hours.length > 1;
  var src = hasIn ? hours : (outdoor || []).map(function (o) { return { time: o.time, outdoor: o.t }; });
  if (src.length < 2) return "";
  var narrow = window.innerWidth < 600, W = narrow ? 360 : 680, H = narrow ? 230 : 250, L = 34, R = 10, T = 20, B = 30, n = src.length, step = narrow ? 6 : 3;
  var vals = []; src.forEach(function (x) { vals.push(x.outdoor); if (hasIn) vals.push(x.low, x.high); });
  var lim = fan ? fan.limits_c : null; if (lim) vals.push(lim.not_enough_from);
  var lo = Math.floor(Math.min.apply(null, vals) - 1), hi = Math.ceil(Math.max.apply(null, vals) + 1);
  function X(i) { return L + (W - L - R) * i / (n - 1); } function Y(v) { return T + (H - T - B) * (hi - v) / (hi - lo); }
  var body = "";
  if (hasIn) {
    var band = src.map(function (x, i) { return X(i) + "," + Y(x.high); }).join(" ") + " " + src.slice().reverse().map(function (x, j) { return X(n - 1 - j) + "," + Y(x.low); }).join(" ");
    body += '<polygon points="' + band + '" style="fill:var(--high);opacity:.16"/><path d="' + src.map(function (x, i) { return (i ? "L" : "M") + X(i) + "," + Y(x.indoor); }).join(" ") + '" fill="none" style="stroke:var(--high)" stroke-width="3" stroke-linejoin="round"/>';
  }
  var grid = ""; for (var v = Math.ceil(lo / 2) * 2; v <= hi; v += 2) grid += '<line x1="' + L + '" x2="' + (W - R) + '" y1="' + Y(v) + '" y2="' + Y(v) + '" stroke="currentColor" opacity=".14"/><text x="' + (L - 6) + '" y="' + (Y(v) + 4) + '" font-size="12" text-anchor="end" fill="currentColor">' + v + "°</text>";
  var xl = ""; src.forEach(function (x, i) { if (i % step === 0) xl += '<text x="' + X(i) + '" y="' + (H - 10) + '" font-size="12" text-anchor="middle" fill="currentColor">' + x.time.slice(11, 16) + "</text>"; });
  var limLine = lim && lim.not_enough_from >= lo && lim.not_enough_from <= hi ? '<line x1="' + L + '" x2="' + (W - R) + '" y1="' + Y(lim.not_enough_from) + '" y2="' + Y(lim.not_enough_from) + '" style="stroke:var(--ext)" stroke-dasharray="6 5" stroke-width="2"/><text x="' + (W - R) + '" y="' + (Y(lim.not_enough_from) - 6) + '" font-size="12" text-anchor="end" style="fill:var(--ext)">' + esc(t("fan_line")) + " " + lim.not_enough_from + "°</text>" : "";
  CHART = { src: src, hasIn: hasIn, X: X, Y: Y, n: n, W: W, L: L, R: R };
  return '<div class="chartwrap"><svg class="chart" viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="' + esc(t("chart_title")) + '">' + grid + xl + limLine + body +
    '<path d="' + src.map(function (x, i) { return (i ? "L" : "M") + X(i) + "," + Y(x.outdoor); }).join(" ") + '" fill="none" style="stroke:var(--nariyal-deep)" stroke-width="3" stroke-linejoin="round"/>' +
    '<g class="scrub" visibility="hidden"><line y1="' + T + '" y2="' + (H - B) + '" style="stroke:var(--ink)" stroke-width="1.5" stroke-dasharray="3 3"/><circle r="5" class="so" style="fill:var(--nariyal-deep)"/>' + (hasIn ? '<circle r="5" class="si" style="fill:var(--high)"/>' : "") + "</g>" +
    '<rect class="scrub-hit" x="' + L + '" y="' + T + '" width="' + (W - L - R) + '" height="' + (H - T - B) + '" fill="transparent"/></svg>' +
    '<div class="scrub-tip" hidden></div></div><p class="tiny muted" style="margin-top:4px">' + t("scrub_hint") + "</p>" +
    '<div class="legendrow"><span><i style="background:var(--nariyal-deep)"></i>' + t("outside") + "</span>" + (hasIn ? '<span><i style="background:var(--high)"></i>' + t("inside_range") + "</span>" : "") + '<span><i style="background:var(--ext)"></i>' + t("fan_line") + "</span></div>";
}
function bindScrub(box) {
  var svg = box && box.querySelector("svg.chart"); if (!svg || !CHART) return;
  var c = CHART, g = svg.querySelector(".scrub"), tip = box.querySelector(".scrub-tip");
  function at(e) {
    var r = svg.getBoundingClientRect(), vx = (e.clientX - r.left) * c.W / r.width;
    var i = Math.max(0, Math.min(c.n - 1, Math.round((vx - c.L) / (c.W - c.L - c.R) * (c.n - 1)))), x = c.src[i], px = c.X(i);
    g.setAttribute("visibility", "visible");
    g.querySelector("line").setAttribute("x1", px); g.querySelector("line").setAttribute("x2", px);
    var so = g.querySelector(".so"); so.setAttribute("cx", px); so.setAttribute("cy", c.Y(x.outdoor));
    var si = g.querySelector(".si"); if (si) { si.setAttribute("cx", px); si.setAttribute("cy", c.Y(x.indoor)); }
    tip.hidden = false;
    tip.innerHTML = "<b>" + esc(x.time.slice(11, 16)) + "</b><span>" + t("outside") + " " + fmt(x.outdoor, 1) + "°</span>" + (c.hasIn ? "<span>" + t("row_room") + " " + fmt(x.low, 0) + "–" + fmt(x.high, 0) + "°</span>" : "");
    var left = px / c.W * r.width; tip.style.left = Math.max(0, Math.min(r.width - tip.offsetWidth, left - tip.offsetWidth / 2)) + "px";
  }
  function off() { g.setAttribute("visibility", "hidden"); tip.hidden = true; }
  svg.addEventListener("pointermove", at); svg.addEventListener("pointerdown", at); svg.addEventListener("pointerleave", off);
}
function sosCard() {
  return '<div class="card sos"><div class="card-h"><div class="ic">' + I("alert") + "</div><h3>" + t("signs") + "</h3></div><p><b>" + t("exhaustion") + ":</b> " + t("sx_ex") + "</p><p><b>" + t("stroke") + ":</b> " + t("sx_st") + "</p><p>" + t("cool_first") + '</p><div class="calls"><a href="tel:108">' + I("phone") + "108</a><a href=\"tel:112\">" + I("phone") + "112</a></div></div>";
}
export function resultView() {
  var r = S.result, k = r.risk.level, w = r.weather, ind = r.indoor, fan = r.fan, p = r.place, a = S.a;
  var idx = Math.max(0, LEVELS.indexOf(k)), hasIn = ind.next24 && ind.next24.length > 0;
  var reasons = r.risk.reasons.map(function (x) { return '<li class="' + (x.raise ? "up" : "") + '">' + I(x.raise ? "arrow-up" : x.code === "no_household_raise_mild_heat" ? "info" : "thermo", "sm") + "<span>" + esc(reasonText(x)) + "</span></li>"; }).join("");
  var offline = r._offline ? callout("alert", t("offline_note", { t: esc(new Date(r._offline).toLocaleString(S.lang === "hi" ? "hi-IN" : "en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })) }), "warn", "margin-bottom:16px") : "";
  var summary = '<div class="card summary"><div class="stack">' + placeBlock(p, a, null) + '<div class="row"><span class="badge">' + I("clock", "sm") + t("updated", { t: hm(w.fetched_at) }) + "</span>" + (r._offline ? '<span class="badge moderate">' + t("offline_badge") + "</span>" : "") + '</div><div class="row"><button type="button" class="btn secondary sm" id="chgloc">' + I("pin", "sm") + t("change_place") + '</button><button type="button" class="btn secondary sm" id="chg">' + I("edit", "sm") + t("change") + "</button></div></div>" +
    "<div>" + gaugeSVG(idx) + '<div class="level ' + k + '"><div class="tiny muted">' + t("level_title") + '</div><div class="name">' + t("level_" + k) + "</div></div></div>" +
    '<div><h3 style="margin-bottom:10px">' + t("reasons_title") + '</h3><ul class="reasons">' + reasons + "</ul></div></div>";
  var td = w.today || {}, tm = w.tomorrow || {};
  var kpis = '<div class="kpis" style="margin:16px 0 20px"><div class="kpi"><div class="l">' + I("sun", "sm") + t("today") + " · " + t("feels_max") + '</div><div class="v"><span data-count="' + fmt(td.hi_max, 0) + '">' + fmt(td.hi_max, 0) + '</span><small>°C</small></div><div class="s">' + t("air_max") + " " + fmt(td.tmax, 0) + "° · " + t("wetbulb") + " " + fmt(td.twb_max, 0) + "°</div></div>" +
    '<div class="kpi"><div class="l">' + I("cloud", "sm") + t("tomorrow") + " · " + t("feels_max") + '</div><div class="v"><span data-count="' + fmt(tm.hi_max, 0) + '">' + fmt(tm.hi_max, 0) + '</span><small>°C</small></div><div class="s">' + t("air_max") + " " + fmt(tm.tmax, 0) + "° · " + t("wetbulb") + " " + fmt(tm.twb_max, 0) + "°</div></div>" +
    (hasIn && ind.peak ? '<div class="kpi"><div class="l">' + I("home", "sm") + t("room_peak") + " · " + hm(ind.peak.time) + '</div><div class="v">' + fmt(ind.peak.low, 0) + "–" + fmt(ind.peak.high, 0) + "<small>°C</small></div></div>" : "") +
    (hasIn && ind.night_min ? '<div class="kpi"><div class="l">' + I("moon", "sm") + t("room_night") + '</div><div class="v">' + fmt(ind.night_min.low, 0) + "–" + fmt(ind.night_min.high, 0) + "<small>°C</small></div></div>" : "") + "</div>";
  var note = ind.note_code === "outside_training_range" ? callout("alert", t("indoor_hidden", { t1: ind.applicability.trained_t_c[0], t2: ind.applicability.trained_t_c[1], h1: ind.applicability.trained_rh_pct[0], h2: ind.applicability.trained_rh_pct[1] }), "warn", "margin-top:12px")
    : ind.note_code === "not_validated_here" ? callout("info", t("indoor_not_validated"), "warn", "margin-top:12px") : callout("info", t("indoor_note"), "", "margin-top:12px");
  if (ind.roof_proxy && hasIn) note += callout("info", t("roof_proxy_note"), "", "margin-top:8px");
  var plan = '<div class="card"><div class="card-h"><div class="ic">' + I("clock") + "</div><h3>" + t("plan_title") + '</h3><div class="seg" id="ptabs" role="tablist"><button type="button" role="tab" data-t="plan" class="' + (S.ptab === "plan" ? "on" : "") + '" aria-selected="' + (S.ptab === "plan") + '">' + t("tab_plan") + '</button><button type="button" role="tab" data-t="temp" class="' + (S.ptab === "temp" ? "on" : "") + '" aria-selected="' + (S.ptab === "temp") + '">' + t("tab_temp") + '</button></div></div><div id="pbody" role="tabpanel"></div></div>';
  var fixes = card("list", t("fixes_title"), fixesBlock(r.fixes));
  var measure = '<details class="acc" id="measure"><summary>' + I("thermo") + t("measure_title") + I("chev-r", "chev") + '</summary><div class="body" id="measurebody"></div></details>';
  var howAcc = '<details class="acc"><summary>' + I("cpu") + t("how_short") + I("chev-r", "chev") + '</summary><div class="body">' +
    [["how_k_risk", "how_v_risk"], ["how_k_indoor", hasIn ? "how_v_indoor" : "how_v_indoor_off"], ["how_k_fan", fan.basis === "outdoor" ? "how_v_fan_out" : "how_v_fan"], ["how_k_windows", hasIn ? "how_v_windows" : "plan_no_windows"], ["how_k_fixes", "how_v_fixes"]]
      .map(function (x) { return '<div class="kv" style="display:block"><b style="display:block;text-align:left">' + t(x[0]) + '</b><span class="small muted">' + t(x[1]) + "</span></div>"; }).join("") +
    '<a class="btn ghost sm" href="#/how" style="margin-top:8px">' + t("read_more") + I("arrow-r", "sm") + "</a></div></details>";
  render(offline + summary + kpis + '<div class="layout"><div class="stack">' + todayCard(r.fixes) + plan + fixes + measure + '</div><div class="stack">' + districtCard(p.district_heat, "mmap") + wardCard(p.ward) + sosCard() + howAcc + "</div></div>",
    pageHero({ id: "rm", eyebrow: t("level_title"), title: t("level_" + k), sub: esc(p.label || p.district || ""), mood: moodOf(k), tip: t("res_tip_" + k) }));
  function paintPlan() { $("pbody").innerHTML = S.ptab === "plan" ? planView(r) : chartSVG(ind.next24, ind.outdoor24, fan) + note; if (S.ptab !== "plan") bindScrub($("pbody")); }
  paintPlan();
  document.querySelectorAll("#ptabs button").forEach(function (b) { b.onclick = function () {
    S.ptab = b.getAttribute("data-t");
    document.querySelectorAll("#ptabs button").forEach(function (x) { x.classList.toggle("on", x === b); x.setAttribute("aria-selected", String(x === b)); });
    paintPlan();
  }; });
  $("measure").addEventListener("toggle", function () {
    if ($("measure").open && !$("measure")._m) { $("measure")._m = 1; import("./measure.js").then(function (m) { m.mountMeasure($("measurebody"), r); }); }
  });
  $("chg").onclick = function () { S.step = 1; S.result = null; flowStep(); };
  $("chgloc").onclick = function () { S.step = 0; S.result = null; flowStep(); };
  if ($("mmap")) makeMap({ el: "mmap", center: [a.lon, a.lat], zoom: 8.5, wards: p.in_delhi ? "lines" : null })
    .then(function (c) { c.pin(a.lat, a.lon, a.acc, false); c.select(p.district_heat && p.district_heat.id, p.ward && p.ward.ward_no); }).catch(function () { mapFail("mmap"); });
}
