/* Everything that differs between the website and the Android / iOS app lives here. Each Capacitor plugin is imported
   lazily, so the website never downloads native code and the app loads a plugin the first time it is needed. */
import { NATIVE } from "./config.js";

/* Watch the device position for up to 15 s, keep the most accurate fix, stop early once within 50 m.
   onFix(best) runs on every better fix; onEnd(errorCode | null) runs once. */
export function locate(onFix, onEnd) {
  if (NATIVE) return locateNative(onFix, onEnd);
  if (!window.isSecureContext) return onEnd("insecure");
  if (!navigator.geolocation) return onEnd("unsupported");
  var best = null, done = false, id = null, timer = null;
  function finish(code) { if (done) return; done = true; if (id != null) navigator.geolocation.clearWatch(id); clearTimeout(timer); onEnd(best ? null : code); }
  id = navigator.geolocation.watchPosition(function (p) {
    var c = p.coords;
    if (!best || c.accuracy < best.acc) { best = { lat: c.latitude, lon: c.longitude, acc: c.accuracy }; onFix(best); }
    if (c.accuracy <= 50) finish(null);
  }, function (e) { finish(e.code === 1 ? "denied" : e.code === 3 ? "timeout" : "unavailable"); }, { enableHighAccuracy: true, maximumAge: 0, timeout: 20000 });
  timer = setTimeout(function () { finish("timeout"); }, 15000);
}

function locateNative(onFix, onEnd) {
  var best = null, done = false, id = null, timer = null, G = null;
  function finish(code) { if (done) return; done = true; clearTimeout(timer); if (G && id != null) G.clearWatch({ id: id }); onEnd(best ? null : code); }
  import("@capacitor/geolocation").then(function (m) {
    G = m.Geolocation;
    return G.checkPermissions().then(function (p) { return p.location === "granted" ? p : G.requestPermissions({ permissions: ["location"] }); });
  }).then(function (p) {
    if (p.location !== "granted") return finish("denied_app");
    timer = setTimeout(function () { finish("timeout"); }, 15000);
    return G.watchPosition({ enableHighAccuracy: true, maximumAge: 0, timeout: 20000 }, function (pos, err) {
      if (err || !pos) return finish(/denied|permission/i.test(String(err && err.message)) ? "denied_app" : "unavailable");
      var c = pos.coords;
      if (!best || c.accuracy < best.acc) { best = { lat: c.latitude, lon: c.longitude, acc: c.accuracy }; onFix(best); }
      if (c.accuracy <= 50) finish(null);
    }).then(function (wid) { id = wid; if (done) G.clearWatch({ id: wid }); });
  }).catch(function (e) { finish(/disabled|services/i.test(String(e && e.message)) ? "unavailable" : "denied_app"); });
}

/* File export: a download on the website; on a phone, write the file to the cache and open the share sheet
   (WhatsApp, Drive, Files...), which is how people actually move a file off a phone */
export function saveCsv(name, text) { return saveFile(name, text, "text/csv"); }
export function saveFile(name, text, type) {
  if (!NATIVE) {
    var a = document.createElement("a"), url = URL.createObjectURL(new Blob([text], { type: type }));
    a.href = url; a.download = name; a.click();
    setTimeout(function () { URL.revokeObjectURL(url); }, 4000);
    return Promise.resolve();
  }
  return Promise.all([import("@capacitor/filesystem"), import("@capacitor/share")]).then(function (m) {
    var FS = m[0].Filesystem;
    return FS.writeFile({ path: name, data: text, directory: m[0].Directory.Cache, encoding: m[0].Encoding.UTF8 })
      .then(function (r) { return m[1].Share.share({ title: name, files: [r.uri] }); });
  });
}

/* status bar colour follows the theme; Android's back button walks back through screens, then leaves the app */
export function initNative(onBack) {
  if (!NATIVE) return;
  document.documentElement.classList.add("native");
  import("@capacitor/app").then(function (m) {
    m.App.addListener("backButton", function (e) { if (onBack()) return; if (e.canGoBack) history.back(); else m.App.exitApp(); });
  });
  import("@capacitor/splash-screen").then(function (m) { m.SplashScreen.hide(); });
}
/* light = light text, for when the top of the screen is the dark sky or the dark theme */
var barLight = null;
export function setStatusBar(light) {
  if (!NATIVE || light === barLight) return;
  barLight = light;
  import("@capacitor/status-bar").then(function (m) {
    m.StatusBar.setStyle({ style: light ? m.Style.Dark : m.Style.Light }).catch(function () {});
  });
}
