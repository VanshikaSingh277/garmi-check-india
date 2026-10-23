/* Two builds from one codebase:
     npm run build      -> dist/ for the website (served by the FastAPI app, calls /api on the same origin)
     npm run build:app  -> dist-app/ for Capacitor (Android / iOS): reads .env.app for the server address and bundles the
                           district / ward outlines from apps/api/data so maps open instantly and offline */
import { defineConfig } from "vite";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const DATA = resolve(__dirname, "../api/data");
const GEO = ["india_districts.geojson", "wards.geojson"];

/* minify the outlines on the way in (the source files are pretty-printed) */
function bundleGeo() {
  return {
    name: "thandak-bundle-geo",
    generateBundle() {
      for (const f of GEO) this.emitFile({ type: "asset", fileName: "data/" + f, source: JSON.stringify(JSON.parse(readFileSync(resolve(DATA, f), "utf8"))) });
    }
  };
}

export default defineConfig(({ mode }) => ({
  base: "./",
  plugins: mode === "app" ? [bundleGeo()] : [],
  build: {
    target: ["es2020", "chrome90", "safari15"],
    outDir: mode === "app" ? "dist-app" : "dist",  // separate, so an app build never replaces the website the server is serving
    emptyOutDir: true,
    assetsInlineLimit: 2048,
    chunkSizeWarningLimit: 1200  // maplibre is ~1 MB but sits in its own lazy chunk
  },
  server: { proxy: { "/api": "http://127.0.0.1:8000" } },
  preview: { proxy: { "/api": "http://127.0.0.1:8000" } }
}));
