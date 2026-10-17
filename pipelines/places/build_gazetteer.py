"""Build the offline India gazetteer used by /api/where and /api/search.

Sources (CC BY 4.0, credit "GeoNames, www.geonames.org"):
  - https://download.geonames.org/export/zip/IN.zip            postal codes (PIN -> post office, district, state, lat/lon, accuracy)
  - https://download.geonames.org/export/dump/IN.zip           all Indian place names (villages, towns, city sections)
  - https://download.geonames.org/export/dump/admin1CodesASCII.txt, admin2Codes.txt   state / district names

Usage: python3 -I build_gazetteer.py <site-packages-dir> <raw-dir> <out-dir>
  <raw-dir> holds zip/ex/IN.txt, dump/ex/IN.txt, admin/admin1CodesASCII.txt, admin/admin2Codes.txt
Outputs (in <out-dir>): india_places.tsv.gz, india_pins.tsv.gz, india_admin.json
"""
import json
import re
import sys

sys.path.insert(0, sys.argv[1])
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

RAW, OUT = sys.argv[2], sys.argv[3]

# ---------- admin names (canonical, ASCII) ----------
a1 = pd.read_csv(f"{RAW}/admin/admin1CodesASCII.txt", sep="\t", header=None, dtype=str, names=["code", "name", "ascii", "id"])
a1 = a1[a1.code.str.startswith("IN.")]
STATES = dict(zip(a1.code.str[3:], a1.ascii))
a2 = pd.read_csv(f"{RAW}/admin/admin2Codes.txt", sep="\t", header=None, dtype=str, names=["code", "name", "ascii", "id"], quoting=3)
a2 = a2[a2.code.str.startswith("IN.")]
DISTRICTS = {c[3:]: re.sub(r"\s+District$", "", n, flags=re.I).strip() for c, n in zip(a2.code, a2.ascii)}

# ---------- populated places ----------
d = pd.read_csv(f"{RAW}/dump/ex/IN.txt", sep="\t", header=None, dtype=str, keep_default_na=False, quoting=3,
                names=["id", "name", "ascii", "alt", "lat", "lon", "fclass", "fcode", "cc", "cc2", "a1", "a2", "a3", "a4",
                       "pop", "elev", "dem", "tz", "mod"])
p = d[(d.fclass == "P") & (~d.fcode.isin(["PPLQ", "PPLH", "PPLW"]))].copy()  # drop abandoned / historical / destroyed
p["pop"] = pd.to_numeric(p["pop"], errors="coerce").fillna(0).astype(int)
p["lat"] = pd.to_numeric(p.lat).round(5)
p["lon"] = pd.to_numeric(p.lon).round(5)
p["st"] = p.a1.map(lambda c: STATES.get(c, ""))
p["dt"] = (p.a1 + "." + p.a2).map(lambda c: DISTRICTS.get(c, ""))
p["name"] = np.where(p.ascii.str.len() > 0, p.ascii, p.name)


def search_aliases(row):
    """Other spellings for towns with a population figure (Bangalore/Bengaluru, Devanagari names...)."""
    if row["pop"] <= 0 or not row["alt"]:
        return ""
    keep = []
    for a in row["alt"].split(","):
        a = a.strip()
        # keep proper-cased Latin spellings (Bangalore, Gurgaon) and Devanagari names; drop machine transliterations and airport codes
        latin_ok = a.isascii() and a[0].isupper() and not a.isupper() and not re.search(r"\d", a)
        if 2 < len(a) <= 40 and (latin_ok or re.fullmatch(r"[ऀ-ॿ\s]+", a)) and a.lower() != row["name"].lower():
            keep.append(a)
    return "|".join(dict.fromkeys(keep))[:400]


p["alias"] = p.apply(search_aliases, axis=1)
places = p[["name", "lat", "lon", "fcode", "pop", "st", "dt", "alias"]].sort_values("pop", ascending=False)
places.to_csv(f"{OUT}/india_places.tsv.gz", sep="\t", index=False, compression="gzip")

# ---------- PIN codes ----------
z = pd.read_csv(f"{RAW}/zip/ex/IN.txt", sep="\t", header=None, dtype=str, keep_default_na=False,
                names=["cc", "pin", "place", "state", "s_code", "district", "d_code", "sub", "sub_code", "lat", "lon", "acc"])
z["lat"] = pd.to_numeric(z.lat)
z["lon"] = pd.to_numeric(z.lon)
z["acc"] = pd.to_numeric(z.acc).astype(int)
# India Post state names -> GeoNames canonical names; Leh & Kargil are in Ladakh UT since 31 Oct 2019
fix_state = {"Jammu & Kashmir": "Jammu and Kashmir", "Pondicherry": "Puducherry", "Andaman & Nicobar Islands": "Andaman and Nicobar"}
z["state"] = z.state.replace(fix_state)
z.loc[z.district.isin(["Leh", "Kargil"]), "state"] = "Ladakh"


def clean_po(name):
    n = re.sub(r"\b(H\.?O|S\.?O|B\.?O|G\.?P\.?O)\.?$", "", name.strip(), flags=re.I).strip(" .-")
    return re.sub(r"\s*\([^)]*\)\s*$", "", n).strip()


z["place_clean"] = z.place.map(clean_po)

# GeoNames' India postal coordinates are often wrong inside cities: accuracy 1 rows are "estimated" (Leh 194101 sits
# ~170 km west of Leh) and some accuracy 3/4 rows were matched to the wrong same-named village (Koramangala 560034 is
# put ~33 km north of Koramangala). Re-anchor each post office on a same-named GeoNames place IN THE SAME DISTRICT.
# District names differ between India Post and GeoNames, so compare normalised names (+ a few renamed-district aliases).
DIST_ALIAS = {"bengaluru": "bangalore urban", "bangalore": "bangalore urban", "gurgaon": "gurugram", "mysuru": "mysore",
              "belagavi": "belgaum", "kalaburagi": "gulbarga", "mangaluru": "dakshina kannada", "prayagraj": "allahabad",
              "raigarh mh": "raigad", "ahmedabad": "ahmadabad", "kanchipuram": "kancheepuram", "tiruvallur": "thiruvallur"}


def norm_dist(d):
    d = re.sub(r"\bdistrict\b", "", re.sub(r"[^a-z ]", " ", str(d).lower()))
    d = re.sub(r"\s+", " ", d).strip()
    return DIST_ALIAS.get(d, d)


def same_district(a, b):
    """exact normalised match, or the same first word (India Post 'Mumbai' vs GeoNames 'Mumbai Suburban')."""
    return a == b or (a and b and a.split()[0] == b.split()[0] and (" " not in a or " " not in b))


cand = {}
for name, la, lo, st, dt, pp in zip(p.name.str.lower(), p.lat, p.lon, p.st, p.dt.map(norm_dist), p["pop"]):
    cand.setdefault(name, []).append((la, lo, st, dt, pp))
moved = 0
for i in z.index:
    cs = cand.get(z.at[i, "place_clean"].lower())
    if not cs:
        continue
    zd, zst, la0, lo0 = norm_dist(z.at[i, "district"]), z.at[i, "state"], z.at[i, "lat"], z.at[i, "lon"]
    exact = [c for c in cs if c[3] == zd]
    loose = [c for c in cs if same_district(c[3], zd) and c[2] == zst]
    pool = exact or loose
    if not pool:
        continue
    b = min(pool, key=lambda c: (c[0] - la0) ** 2 + ((c[1] - lo0) * np.cos(np.radians(la0))) ** 2)  # nearest same-named place
    dkm = 111 * np.hypot(b[0] - la0, (b[1] - lo0) * np.cos(np.radians(la0)))
    if dkm > 2:
        z.at[i, "lat"], z.at[i, "lon"], z.at[i, "acc"] = b[0], b[1], 2  # 2 = re-anchored by name+district match (ours)
        moved += 1
# Second pass, per PIN: post offices of one PIN are close together. Where some offices were re-anchored, move the
# offices still lying > 15 km from their median onto it (fixes 'Faing'/'Spituk' 194101 still at the bad estimate).
for pin, g in z.groupby("pin"):
    ok = g[g.acc == 2]
    if ok.empty:
        continue
    mla, mlo = ok.lat.median(), ok.lon.median()
    far = g[(g.acc != 2) & (111 * np.hypot(g.lat - mla, (g.lon - mlo) * np.cos(np.radians(mla))) > 15)]
    z.loc[far.index, ["lat", "lon", "acc"]] = [mla, mlo, 2]
    moved += len(far)
z["dnorm"] = z.district.map(norm_dist)
places["dnorm"] = places.dt.map(norm_dist)  # same normalisation at runtime lets the API check PIN rows against the place's district
places.to_csv(f"{OUT}/india_places.tsv.gz", sep="\t", index=False, compression="gzip")
# The city each post office belongs to, by a gravity score pop / (km + 1)^2 over towns >= 20,000 people within 25 km
# (so Andheri -> Mumbai, not the nearer but smaller Powai; Noida stays Noida rather than Delhi). Used to rank search results.
from scipy.spatial import cKDTree  # noqa: E402  (build-time only)


def unit(lat, lon):
    la, lo = np.radians(lat), np.radians(lon)
    return np.c_[np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)]


towns = p[p["pop"] >= 20000][["name", "lat", "lon", "pop"]].reset_index(drop=True)
tree = cKDTree(unit(towns.lat.values, towns.lon.values))
hits = tree.query_ball_point(unit(z.lat.values, z.lon.values), r=25 / 6371.0)
z_town, z_town_pop = [], []
for (la, lo), idx in zip(zip(z.lat.values, z.lon.values), hits):
    best, best_s = None, 0.0
    for t in idx:
        dkm = 111 * np.hypot(towns.lat[t] - la, (towns.lon[t] - lo) * np.cos(np.radians(la)))
        s = towns["pop"][t] / (dkm + 1) ** 2
        if s > best_s:
            best, best_s = t, s
    z_town.append(towns.name[best] if best is not None else "")
    z_town_pop.append(int(towns["pop"][best]) if best is not None else 0)
z["town"], z["town_pop"] = z_town, z_town_pop
pins = z[["pin", "place", "place_clean", "district", "dnorm", "state", "lat", "lon", "acc", "town", "town_pop"]].copy()
pins["lat"] = pins.lat.round(5)
pins["lon"] = pins.lon.round(5)
pins.to_csv(f"{OUT}/india_pins.tsv.gz", sep="\t", index=False, compression="gzip")

json.dump({"states": sorted(set(STATES.values())), "n_districts": len(DISTRICTS),
           "source": "GeoNames (www.geonames.org), CC BY 4.0; downloaded 2026-10-15",
           "notes": ["District names follow GeoNames admin2 and may not include districts created recently (e.g. Rajasthan 2023-24).",
                     "PIN coordinates are post-office estimates, not exact boundaries."]},
          open(f"{OUT}/india_admin.json", "w"), indent=1)
print(f"places {len(places)} (with aliases {int((places.alias != '').sum())}); pins {len(pins)} unique {pins.pin.nunique()}; "
      f"post offices re-anchored by name+district {moved}")
