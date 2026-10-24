/* #/app - the app's home, in two steps: first "where are you" (search or GPS); once the place is known, today's heat
   there and the three ways in (me / colony / government) */
import { t } from "../i18n/index.js";
import { I } from "../icons.js";
import { esc, fmt, hm, $ } from "../util.js";
import { S } from "../state.js";
import { api } from "../api.js";
import { render, pageHero, setMascot, moodOf, fx, wxCredit } from "../ui.js";
import { promptBox, bindPrompt, bindGps, setLoc, refreshWhere, known, needsRefresh } from "../place.js";
import { route } from "../router.js";
import { warmMaps } from "../map.js";

export function appHome() {
  var a = S.a, k = known(), finding = !k || S.finding || /\/find$/.test(location.hash);
  var find = '<div class="ph-find">' + promptBox("hq") + '<button class="btn white block gps-btn" id="hgps" type="button">' + I("locate") + t("use_gps") + '</button><div class="statusline" id="hmsg"></div>' +
    (k ? '<button type="button" class="linkbtn on-sky" id="cancelfind">' + t("back") + "</button>" : "") + "</div>";
  var hero = pageHero({ id: "ahm", title: t(finding ? "hero_title" : "home_title"), mood: "happy", tip: t(k && !finding ? "app_tip_loading" : "app_tip_empty"), extra: finding ? find : "" });
  render(finding && !k ? '<section class="heat" id="nowcard">' + heatCard("empty") + "</section>"
    : '<section class="heat" id="nowcard">' + heatCard(null) + "</section>" + roles(), hero);
  function done() { S.finding = false; if (/\/find$/.test(location.hash)) history.replaceState(null, "", "#/app"); appHome(); }
  if (finding) {
    bindPrompt("hq", function (it) { setLoc(it.lat, it.lon, "search", null, null).then(done); });
    bindGps("hgps", "hmsg", function () { return null; }, done);
    if ($("cancelfind")) $("cancelfind").onclick = done;
    if (k) $("hq").focus();
  }
  /* on the card, not the button: the card is redrawn when the forecast arrives */
  $("nowcard").onclick = function (e) { if (e.target.closest("#chgplace")) { S.finding = true; appHome(); } };
  if (!S._rw && needsRefresh()) { S._rw = true; refreshWhere().then(function () { if (route() === "app") appHome(); }); }
  if (k) api("/api/weather?lat=" + a.lat + "&lon=" + a.lon).then(function (w) {
    var c = $("nowcard"); if (!c) return;
    var lvl = (w.today || {}).hi_level || "low";
    c.className = "heat " + lvl; c.innerHTML = heatCard(w); fx();
    if (!finding) setMascot("ahm", moodOf(lvl), t("app_tip", { b: t("level_" + lvl) }));
  }).catch(function () { var c = $("nowcard"); if (c) c.innerHTML = heatCard("offline"); });
  /* the next screen most people open has a map: fetch it while they read this one */
  if ("requestIdleCallback" in window) requestIdleCallback(warmMaps, { timeout: 4000 }); else setTimeout(warmMaps, 2500);
}
/* step two of the app: the place is known, now who is it for */
function roles() {
  return '<section class="entries"><h2>' + t("roles_title") + '</h2><div class="entry-list">' +
    [["me", "thermo", "individual"], ["area", "users", "society"], ["gov", "landmark", "government"]].map(function (r) {
      return '<a class="entry" href="#/' + r[0] + '"><span class="eic">' + I(r[1]) + "</span><b>" + t(r[2]) + "</b><span class=\"sub\">" + t(r[2] + "_sub") + "</span>" + I("chev-r", "go") + "</a>"; }).join("") + "</div></section>";
}
/* current heat: band colour on the left edge (set on the section), temperature as the biggest thing on screen */
function heatCard(w) {
  var a = S.a;
  if (w === "empty") return '<div class="top"><span class="where">' + I("pin", "sm") + t("now_title") + '</span></div><div class="body"><div><div class="temp muted" aria-hidden="true">--°</div><p class="empty">' + t("now_pick") + "</p></div></div>";
  var lab = a.where.label || "", st = a.where.state && lab.indexOf(a.where.state) < 0 ? ", " + a.where.state : "";  // no "Delhi, Delhi"
  var head = '<div class="top"><span class="where">' + I("pin", "sm") + esc(lab + st) + '</span><button type="button" class="linkbtn small" id="chgplace">' + t("change_place") + "</button></div>";
  if (w === "offline") return head + '<div class="callout warn" style="margin-top:14px">' + I("alert") + "<div>" + t("net_error") + "</div></div>";
  if (!w) return head + '<div class="skeleton" style="height:120px;margin-top:14px"></div>';
  var n = w.now || {}, td = w.today || {}, tm = w.tomorrow || {}, lvl = td.hi_level || "low";
  return head + '<div class="body"><div><div class="temp"><span data-count="' + fmt(n.t, 0) + '">' + fmt(n.t, 0) + '</span>°</div><p class="feels">' + t("air_now") + " · " + t("feels") + " <b>" + fmt(n.hi, 0) + "°</b> · " + fmt(n.rh, 0) + "% RH</p></div>" +
    '<div><div class="small muted">' + t("today_band") + '</div><div class="bandname"><i aria-hidden="true"></i>' + t("level_" + lvl) + "</div>" +
    '<div class="stats" style="margin-top:16px"><div class="stat"><div class="l">' + t("today_max") + '</div><div class="v"><span data-count="' + fmt(td.hi_max, 0) + '">' + fmt(td.hi_max, 0) + '</span><small>°C</small></div></div><div class="stat"><div class="l">' + t("tomorrow_max") + '</div><div class="v"><span data-count="' + fmt(tm.hi_max, 0) + '">' + fmt(tm.hi_max, 0) + "</span><small>°C</small></div></div></div></div></div>" +
    '<div class="foot-row"><span class="tiny muted">' + t("updated", { t: hm(n.time) }) + "</span>" + wxCredit() + "</div>";
}
