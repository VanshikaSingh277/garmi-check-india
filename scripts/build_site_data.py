"""Package model outputs for the website (apps/api/data). Re-run after any pipeline/model update.
Usage: python scripts/build_site_data.py <pylib_or_empty>"""
import json, os, shutil, sys
if len(sys.argv) > 1 and sys.argv[1]:
    sys.path.insert(0, sys.argv[1])
import pandas as pd, geopandas as gpd  # noqa: E401,E402

R = os.path.join(os.path.dirname(__file__), "..")
D = os.path.join(R, "apps", "api", "data")
os.makedirs(D, exist_ok=True)
for src, dst in [("docs/verified_numbers.csv", "verified_numbers.csv"), ("ml/indoor/indoor_xgb_model.json", "indoor_xgb_model.json"),
                 ("ml/indoor/indoor_model_card.json", "indoor_model_card.json"), ("ml/model_a/model_a_card_fullrun.json", "model_a_card.json"),
                 ("ml/hvi/hvi_checks.json", "hvi_checks.json")]:
    shutil.copy(os.path.join(R, src), os.path.join(D, dst))

WORDS = {"ndbi": "built_paved", "f_built": "dense_buildings", "f_tree": "few_trees", "ndvi": "little_greenery", "mndwi": "dry_surfaces",
         "f_water": "no_water", "dist_water_m": "far_from_water", "albedo": "bright_dry_ground", "f_bare": "bare_ground",
         "elevation_m": "low_lying", "f_crop": "farmland_effect", "f_green_low": "dry_grass_scrub"}
shap = pd.read_csv(os.path.join(R, "ml/model_a/ward_mean_shap.csv")).set_index("ward_no")


def drivers(wno):
    if wno not in shap.index:
        return []
    s = shap.loc[wno].drop(labels=[c for c in shap.columns if c not in WORDS]).sort_values(ascending=False)
    return [{"code": WORDS[k], "shap_c": round(float(v), 2)} for k, v in s.items() if v > 0.05][:3]


h = pd.read_csv(os.path.join(R, "ml/hvi/delhi_ward_hvi.csv"))
keep = ["ward_no", "ward_name", "district", "area_km2", "lst_day_mean_c", "lst_day_p90_c", "lst_night_mean_c", "frac_tree", "frac_built",
        "frac_water", "pop_total", "pop_under5", "pop_65plus", "pop_density_per_km2", "c2011_share_metal_sheet", "c2011_share_stone_slab",
        "dusib_jj_clusters_in_district", "hvi", "hvi_rank", "hvi_class", "hvi_E", "hvi_S", "hvi_A"]
h = h[keep].copy()
h["drivers"] = h.ward_no.map(drivers)
g = gpd.read_file(os.path.join(R, "data/derived/delhi_ward_features.geojson"))[["ward_no", "geometry"]]
g = g.merge(h, on="ward_no", how="inner")
g["geometry"] = g.geometry.simplify(0.0003)
for c in ["lst_day_mean_c", "lst_day_p90_c", "lst_night_mean_c"]:
    g[c] = g[c].round(1)
for c in ["frac_tree", "frac_built", "frac_water", "c2011_share_metal_sheet", "c2011_share_stone_slab", "hvi", "hvi_E", "hvi_S", "hvi_A"]:
    g[c] = g[c].round(3)
for c in ["pop_total", "pop_under5", "pop_65plus", "pop_density_per_km2"]:
    g[c] = g[c].round(0)
pts = g.to_crs(32643).geometry.representative_point().to_crs(4326)
g["lat"] = pts.y.round(5); g["lon"] = pts.x.round(5)
cent = dict(zip(g.ward_no, zip(g.lat, g.lon)))
g["drivers"] = g["drivers"].map(json.dumps)
g.to_file(os.path.join(D, "wards.geojson"), driver="GeoJSON")
rank = h.sort_values("hvi", ascending=False).drop(columns=["drivers"]).to_dict("records")
for r, row in zip(rank, h.sort_values("hvi", ascending=False).drivers):
    r["drivers"] = row
    r["lat"], r["lon"] = cent.get(r["ward_no"], (None, None))
json.dump({"generated": "2026-10-15", "wards": rank}, open(os.path.join(D, "gov_rank.json"), "w"))
# sources table (parsed from docs/sources.md)
rows = [l.strip().strip("|").split("|") for l in open(os.path.join(R, "docs/sources.md"), encoding="utf-8") if l.startswith("| S")]
json.dump([{"id": r[0].strip(), "source": r[1].strip(), "used_for": r[2].strip(), "year": r[3].strip(), "licence": r[4].strip(), "url": r[5].strip(),
            "status": r[6].strip() if len(r) > 6 else ""} for r in rows],
          open(os.path.join(D, "sources.json"), "w"), ensure_ascii=False, indent=1)
print("site data ->", D, sorted(os.listdir(D)))
print("wards:", len(g), "| size wards.geojson KB:", os.path.getsize(os.path.join(D, "wards.geojson")) // 1024)
