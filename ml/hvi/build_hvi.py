"""Phase 3 - Model B: Heat Vulnerability Index per ward (scored index, not trained - no heat-illness labels exist).

HVI = E + S - A (equal weights), each indicator min-max scaled 0-1 across Delhi wards, result rescaled 0-1.
E exposure   : Landsat pre-monsoon day LST mean; MODIS night LST mean
S sensitivity: vulnerable people per km2 (under-5 + 65+, WorldPop 2025); JJ clusters per lakh people (district, DUSIB 2022);
               metal-sheet roof share and stone-slab roof share (district, Census 2011 - OLD)
A adaptive   : tree fraction; water fraction (WorldCover 2021)
Excluded: AC/cooler share (NFHS-5 is state-level only -> no spatial variation).
Checks: (1) PCA-weighted variant vs equal weights (Spearman); (2) Delhi HAP 2024-25 Landsat-2019 hotspot wards.
Usage: python build_hvi.py <pylib> <ward_features.csv> <out_dir>
"""
import os, sys
sys.path.insert(0, sys.argv[1])
import numpy as np, pandas as pd  # noqa: E401,E402
from scipy.stats import spearmanr  # noqa: E402
from sklearn.decomposition import PCA  # noqa: E402

f = pd.read_csv(sys.argv[2]); OUT = sys.argv[3]; os.makedirs(OUT, exist_ok=True)
f = f[f.ward_no.notna()].copy()
dist_pop = f.groupby("district").pop_total.transform("sum")
f["jj_per_lakh"] = f.dusib_jj_clusters_in_district / (dist_pop / 1e5)
f["vuln_people_per_km2"] = (f.pop_under5 + f.pop_65plus) / f.area_km2
IND = {"E": ["lst_day_mean_c", "lst_night_mean_c"],
       "S": ["vuln_people_per_km2", "jj_per_lakh", "c2011_share_metal_sheet", "c2011_share_stone_slab"],
       "A": ["frac_tree", "frac_water"]}
sc = pd.DataFrame(index=f.index)
for cols in IND.values():
    for c in cols:
        x = f[c].astype(float); sc[c] = (x - x.min()) / (x.max() - x.min())
E, S, A = (sc[IND[k]].mean(axis=1) for k in "ESA")
raw = E + S - A
f["hvi_E"], f["hvi_S"], f["hvi_A"] = E.round(3), S.round(3), A.round(3)
f["hvi"] = ((raw - raw.min()) / (raw.max() - raw.min())).round(3)
f["hvi_rank"] = f.hvi.rank(ascending=False, method="min").astype(int)
f["hvi_class"] = pd.qcut(f.hvi, 5, labels=["Very low", "Low", "Moderate", "High", "Very high"])
# PCA check (A indicators sign-flipped so 'higher = more vulnerable')
M = sc.copy().fillna(sc.median())
print('NaN per indicator before fill:', sc.isna().sum()[sc.isna().sum()>0].to_dict())
for c in IND["A"]:
    M[c] = 1 - M[c]
pca = PCA(n_components=1).fit(M.values)
w = np.abs(pca.components_[0]); w = w / w.sum()
pca_hvi = M.values @ w
rho = spearmanr(f.hvi, pca_hvi).correlation
print("PCA PC1 explained var %.2f | weights:" % pca.explained_variance_ratio_[0], dict(zip(M.columns, np.round(w, 3))))
print("Spearman(equal-weight HVI, PCA-weighted HVI) = %.3f" % rho)
# External check: hotspot wards named in Delhi HAP 2024-25 (Landsat 8, 30 May 2019)
hap = ["HARKESH NAGAR", "KHYALA", "WAZIR PUR", "BIJWASAN", "VISHWAS NAGAR", "HARI NAGAR", "JAHANGIR PURI", "DELHI GATE", "SHASTRI PARK"]
f["lst_day_pct"] = f.lst_day_mean_c.rank(pct=True).round(3)
f["hvi_pct"] = f.hvi.rank(pct=True).round(3)
chk = f[f.ward_name.str.upper().str.contains("|".join(hap), na=False)][["ward_no", "ward_name", "district", "lst_day_mean_c", "lst_day_pct", "hvi", "hvi_pct"]]
print("\nHAP 2019 hotspot wards found in our ward file:", len(chk))
print(chk.to_string(index=False))
if len(chk):
    print("median LST-day percentile of HAP hotspot wards: %.2f (0.50 = city median)" % chk.lst_day_pct.median())
f.to_csv(os.path.join(OUT, "delhi_ward_hvi.csv"), index=False)
print("\nTop 15 wards by HVI:\n", f.sort_values("hvi", ascending=False)[["hvi_rank", "ward_name", "district", "hvi", "hvi_E", "hvi_S", "hvi_A", "lst_day_mean_c", "lst_night_mean_c", "frac_tree"]].head(15).to_string(index=False))
pd.Series({"pca_pc1_var": float(pca.explained_variance_ratio_[0]), "spearman_equal_vs_pca": float(rho)}).to_json(os.path.join(OUT, "hvi_checks.json"))
