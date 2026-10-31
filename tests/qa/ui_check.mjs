// Browser QA cases (needs Node, `npm i puppeteer-core` in this folder, and Microsoft Edge). Server on :8000.
// Usage: node tests/qa/ui_check.mjs out.json ; then python tests/qa/p1_qa.py <server-log> out.json
// Phase 1 browser cases: P1-01, P1-03, P1-05, P1-07, P1-08, P1-18, P1-23. Writes [[id, title, ok, note], ...] to argv[2].
import puppeteer from "puppeteer-core";
import fs from "fs";
const BASE = "http://localhost:8000/";
const OUT = process.argv[2];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const b = await puppeteer.launch({ executablePath: "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe", headless: "new", args: ["--no-sandbox", "--enable-unsafe-swiftshader"] });
const res = [];
const csp = [];

async function result(lang, place) {
  const p = await b.newPage();
  await p.setViewport({ width: 1280, height: 900 });
  const errs = [];
  p.on("pageerror", (e) => errs.push("pageerror " + e.message));
  p.on("console", (m) => { const t = m.text(); if (/Content Security Policy|CSP violation/i.test(t)) csp.push(t); else if (m.type() === "error" && !/favicon|tile\.openstreetmap/.test(t)) errs.push(t); });
  await p.evaluateOnNewDocument((s) => {
    document.addEventListener("securitypolicyviolation", (e) => console.error("CSP violation: " + e.violatedDirective + " " + e.blockedURI));
    if (!sessionStorage.getItem("seeded")) { sessionStorage.setItem("seeded", 1); localStorage.clear(); localStorage.setItem("gc_state", JSON.stringify(s)); }
  }, { lang, a: { lat: place.lat, lon: place.lon, method: "search" } });
  await p.goto(BASE + "#/app", { waitUntil: "networkidle2" }); await sleep(2500);
  for (let i = 0; i < 3; i++) {   // the home screen re-renders once the place loads: retry the tap
    try { await p.waitForSelector('a.entry[href="#/me"]', { timeout: 15000 }); await p.click('a.entry[href="#/me"]'); await p.waitForSelector('.opt[data-v="tin_top"]', { timeout: 8000 }); break; }
    catch (e) { await sleep(2000); }
  }
  await sleep(800);
  await p.click('.opt[data-v="tin_top"]'); await p.click("#nx"); await sleep(600);
  await p.click('.opt[data-v="elderly"]'); await p.click("#nx"); await sleep(600);
  await p.click('.opt[data-v="fan"]'); await p.click('.opt[data-v="cooler"]').catch(() => {});
  await p.click("#nx");
  await p.waitForSelector(".card.summary", { timeout: 60000 }); await sleep(2500);
  const r = await p.evaluate(() => {
    const app = document.getElementById("app"), txt = app.innerText;
    return { txt, all: app.textContent, lvl: (document.querySelector(".card.summary .level")||{className:""}).className.replace("level","").trim(), level: !!document.querySelector(".card.summary .level .name"), reasons: document.querySelectorAll(".card.summary ul.reasons li").length,
      home: !!document.querySelector(".homerisk"), plan: !!document.querySelector(".hourgrid"), fixes: document.querySelectorAll(".fix").length,
      roomKpi: [...document.querySelectorAll(".kpi .l")].some((e) => /Room|कमरे/.test(e.innerText) && /°|peak|सबसे|रात|night/i.test(e.innerText)) };
  });
  await p.close();
  return { ...r, errs };
}

// an uncaught failure must not leave the browser running: its pages pile up as blank "Thandak" windows
try {
const delhiEn = await result("en", { lat: 28.6139, lon: 77.209 });
res.push(["P1-01", "Family result still works (browser)", delhiEn.level && delhiEn.reasons > 0 && delhiEn.home && delhiEn.plan && delhiEn.fixes > 0 && !delhiEn.errs.length,
  `level=${delhiEn.level} reasons=${delhiEn.reasons} yourHome=${delhiEn.home} plan=${delhiEn.plan} fixes=${delhiEn.fixes} errors=${delhiEn.errs.slice(0, 2).join("; ") || "none"}`]);
const coolerShown = /cooler should help|Too humid for the cooler/.test(delhiEn.txt);
const hot = delhiEn.lvl !== "low", leftOut = /threshold is verified/.test(delhiEn.all);
res.push(["P1-05", "Cooler cards are off (browser)", !coolerShown && (leftOut || !hot), `level=${delhiEn.lvl}; cooler card shown=${coolerShown}; left-out line=${leftOut} (expected only on a Moderate+ day)`]);
res.push(["P1-07", "No prices without a verified source (browser)", !/₹\s?\d/.test(delhiEn.txt), `₹ figure on screen=${/₹\s?\d/.test(delhiEn.txt)}`]);
res.push(["P1-08", "Numbers in advice are filled in (browser)", !delhiEn.txt.includes("{n:"), `placeholder on screen=${delhiEn.txt.includes("{n:")}`]);
const jaipur = await result("en", { lat: 26.9124, lon: 75.7873 });
res.push(["P1-03", "Outside Delhi: no room numbers (browser)", !jaipur.roomKpi && jaipur.plan, `room number tiles=${jaipur.roomKpi}; plan shown=${jaipur.plan}`]);
const delhiHi = await result("hi", { lat: 28.6139, lon: 77.209 });
const latinLines = delhiHi.txt.split("\n").filter((l) => l.trim().length > 25 && !/[ऀ-ॿ]/.test(l) && !/^[\d\s°C:–.,%-]+$/.test(l) && !/©|Open-Meteo|CC BY/.test(l));   // licence credits stay as written
res.push(["P1-23", "Hindi parity (browser)", delhiHi.level && delhiHi.fixes > 0 && latinLines.length === 0 && !delhiHi.txt.includes("{n:"),
  `fixes=${delhiHi.fixes}; long English-only lines: ${latinLines.slice(0, 3).join(" / ") || "none"}`]);

// P1-18: every page under the CSP
const p = await b.newPage();
p.on("console", (m) => { const t = m.text(); if (/Content Security Policy|CSP violation/i.test(t)) csp.push(t); });
await p.evaluateOnNewDocument(() => document.addEventListener("securitypolicyviolation", (e) => console.error("CSP violation: " + e.violatedDirective + " " + e.blockedURI)));
for (const r of ["#/", "#/app", "#/area", "#/gov", "#/how", "#/sources"]) { await p.goto(BASE + r, { waitUntil: "networkidle2" }).catch(() => {}); await sleep(3000); }
const maps = await p.evaluate(() => document.querySelectorAll(".maplibregl-canvas").length);
res.push(["P1-18", "Site works under the CSP (browser)", csp.length === 0, `CSP violations: ${csp.slice(0, 3).join(" / ") || "none"}; map canvases on last page: ${maps}`]);
} finally {
  await b.close();
}
fs.writeFileSync(OUT, JSON.stringify(res));
console.log(res.map((r) => (r[2] ? "PASS " : "FAIL ") + r[0] + " " + r[3]).join("\n"));
