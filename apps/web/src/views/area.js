/* #/area - colony / society / RWA: the district (and Delhi ward) heat profile, a cool-roof cost calculator and shared fixes */
import { t } from "../i18n/index.js";
import { esc, inr, classBadge, $ } from "../util.js";
import { S } from "../state.js";
import { api } from "../api.js";
import { render, pageHero, setMascot, moodOf, card, skeletonCard, callout, failBox, bindRetry } from "../ui.js";
import { makeMap, mapTools, bindTools, mapFail } from "../map.js";
import { placeBlock, searchBox, bindSearch } from "../place.js";
import { fixesBlock, districtCard, wardCard } from "./parts.js";

export function areaView() {
  var a = S.a;
  render('<div class="layout even"><div class="mapbox sticky-side"><div id="map" class="map"></div>' + mapTools("st") + "</div>" +
    '<div class="stack"><div class="card">' + searchBox("q") + '</div><div id="soc" class="stack"></div></div></div>', pageHero({ id: "am", title: t("soc_title"), sub: t("pick_ward_tap"), tip: t("area_tip"), mood: "happy" }));
  M.ctrl = null; M.last = null;
  makeMap({ el: "map", center: a.lat != null ? [a.lon, a.lat] : null, zoom: a.lat != null ? 7.5 : null, wards: "lines", onClick: function (ll) { showArea(ll.lat, ll.lng); } })
    .then(function (c) { M.ctrl = c; bindTools("st", c); mark(); }).catch(function () { mapFail("map"); });
  bindSearch("q", function (it) { showArea(it.lat, it.lon); });
  /* the saved place's numbers load alongside the map library instead of waiting for it */
  if (a.lat != null) showArea(a.lat, a.lon);
  else $("soc").innerHTML = callout("info", t("pick_ward_tap"));
}
/* the map may finish loading before or after the area data: whichever comes second marks the place */
var M = { ctrl: null, last: null }, seq = 0;
function mark() { var c = M.ctrl, l = M.last; if (c && l) { c.pin(l.lat, l.lon, null, true); c.select(l.dist, l.ward); } }
function showArea(lat, lon) {
  var box = $("soc"), my = ++seq; if (!box) return;
  box.innerHTML = skeletonCard(80) + skeletonCard(200);
  api("/api/area?lat=" + lat + "&lon=" + lon + "&lang=" + S.lang).then(function (d) {
    if (my !== seq || !$("soc")) return;  // a newer tap, or the user left the page
    var wh = d.where, dh = d.district, e = d.coolroof_effect_c;
    M.last = { lat: lat, lon: lon, dist: dh.id, ward: wh.ward && wh.ward.ward_no }; mark();
    setMascot("am", moodOf(classBadge(dh.hx_class)), t("area_tip_d", { d: esc(dh.district) }));
    box.innerHTML = '<div class="card">' + placeBlock(wh, null, null) + "</div>" + districtCard(dh) + wardCard(wh.ward) +
      card("rupee", t("calc_title"), '<div class="stack"><label class="field"><span>' + t("roof_area") + ' <b id="rav" class="num"></b></span><input type="range" id="ra" min="20" max="5000" step="10" value="500"></label>' +
        '<label class="field"><span>' + t("households") + ' <b id="hhv" class="num"></b></span><input type="range" id="hh" min="1" max="500" step="1" value="20"></label>' +
        '<div class="kpis"><div class="kpi"><div class="l">' + t("total_cost") + '</div><div class="v" id="ct"></div></div><div class="kpi"><div class="l">' + t("per_hh") + '</div><div class="v" id="cp"></div></div><div class="kpi"><div class="l">' + t("cooler_by") + '</div><div class="v">' + esc(e.india_low) + "–" + esc(e.india_high) + "<small>°C</small></div></div></div>" +
        "</div>") +
      card("list", t("fixes_title"), fixesBlock(d.solutions));
    function calc() { var ra = +$("ra").value, hh = +$("hh").value, cst = ra * d.coolroof_cost_inr_per_m2; $("rav").textContent = inr(ra) + " m²"; $("hhv").textContent = hh; $("ct").textContent = "₹" + inr(cst); $("cp").textContent = "₹" + inr(cst / hh); }
    $("ra").oninput = calc; $("hh").oninput = calc; calc();
  }).catch(function (err) {
    if (my !== seq || !$("soc")) return;
    /* 404 = the point is outside India; anything else is a network problem worth retrying */
    if (String(err && err.message) === "404") box.innerHTML = callout("alert", t("outside_india"), "warn");
    else { box.innerHTML = failBox("net_error"); bindRetry(function () { showArea(lat, lon); }); }
  });
}
