/* Build-time settings (Vite env files: .env, .env.app). The website is served by the API itself, so it calls "/api/...";
   the Android / iOS app runs from the device and needs the full server address in VITE_API_BASE. */
import { Capacitor } from "@capacitor/core";

export const NATIVE = Capacitor.isNativePlatform();
export const API_BASE = (import.meta.env.VITE_API_BASE || "").replace(/\/$/, "");
/* OpenStreetMap's public tiles are for light use only; point this at your own or a paid tile server before a large launch */
export const TILE_URL = import.meta.env.VITE_TILE_URL || "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
/* the app ships the district and ward outlines inside its bundle (no 2 MB download on every launch); the website
   fetches them from the API so a pipeline re-run shows up without a new frontend build */
export const GEO = NATIVE
  ? { districts: "data/india_districts.geojson", wards: "data/wards.geojson" }
  : { districts: API_BASE + "/api/india/districts.geojson", wards: API_BASE + "/api/wards.geojson" };
