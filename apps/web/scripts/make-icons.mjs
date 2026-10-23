/* Draws the app icon and splash from the matka logo (the same artwork as the favicon) into:
     public/icon-192.png, public/icon-512.png      web app manifest
     resources/icon*.png, resources/splash*.png    source images for `npx capacitor-assets generate` (Android + iOS)
   Run: node scripts/make-icons.mjs */
import sharp from "sharp";
import { mkdirSync } from "node:fs";

const MATKA = '<g fill="none" stroke="#FFFDF8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8.5 3h7"/><path d="M9.5 3v2.4c0 .5-.3 1-.8 1.3C6 8.2 4.5 10.7 4.5 13.6c0 4.1 3.4 7.4 7.5 7.4s7.5-3.3 7.5-7.4c0-2.9-1.5-5.4-4.2-6.9-.5-.3-.8-.8-.8-1.3V3"/><path d="M4.8 12.2c2.4 1.2 4.8 1.2 7.2 0s4.8-1.2 7.2 0"/></g>';
/* square icon: orange tile, logo in the middle 60% (inside the Android adaptive-icon safe zone) */
const icon = (bg) => `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024">${bg ? '<rect width="1024" height="1024" fill="#eb6928"/>' : ""}<g transform="translate(205 205) scale(25.6)">${MATKA}</g></svg>`;
/* splash: dusk-sky gradient with the logo tile in the centre */
const splash = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 2732 2732"><defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#190922"/><stop offset=".65" stop-color="#5b2a5e"/><stop offset="1" stop-color="#ee8a68"/></linearGradient></defs><rect width="2732" height="2732" fill="url(#g)"/><rect x="1110" y="1110" width="512" height="512" rx="112" fill="#eb6928"/><g transform="translate(1212 1212) scale(12.8)">${MATKA}</g></svg>`;

mkdirSync("resources", { recursive: true });
const png = (svg, size, out) => sharp(Buffer.from(svg)).resize(size, size).png().toFile(out);
await Promise.all([
  png(icon(true), 192, "public/icon-192.png"),
  png(icon(true), 512, "public/icon-512.png"),
  png(icon(true), 1024, "resources/icon-only.png"),
  png(icon(false), 1024, "resources/icon-foreground.png"),
  sharp({ create: { width: 1024, height: 1024, channels: 4, background: "#eb6928" } }).png().toFile("resources/icon-background.png"),
  png(splash, 2732, "resources/splash.png"),
  png(splash, 2732, "resources/splash-dark.png")
]);
console.log("icons written");
