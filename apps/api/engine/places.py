"""Offline India gazetteer: name any point in India and search places / PIN codes.

Data: GeoNames (www.geonames.org, CC BY 4.0) built by pipelines/places/build_gazetteer.py into
data/india_places.tsv.gz (549k populated places) and data/india_pins.tsv.gz (155k post offices, 19k PIN codes).
No third-party geocoder is called at runtime, so the user's location never leaves our server.
"""
import bisect
import csv
import gzip
import math
import os
import re
from functools import lru_cache

DATA = os.path.join(os.path.dirname(__file__), "..", "data")
CELL = 0.05  # grid index cell, degrees (~5 km)
INDIA_BBOX = (6.0, 68.0, 37.2, 97.6)  # lat_min, lon_min, lat_max, lon_max
# post-office names that are buildings/institutions, not neighbourhoods
NOT_LOCALITY = re.compile(r"\b(hospital|college|university|office|court|bhawan|bhavan|house|hotel|secretariat|building|campus|"
                          r"collectorate|factory|station|school|vidyalaya|kendra|board|mill|c\.?p\.?m\.?g|mrec|iit|nit|aiims|"
                          r"assembly|parliament|high court|air force|cantt? board|exchange|depot|plant|project|post|offices?|bldg|"
                          r"foreign|sorting|r\.?m\.?s|gpo|mandi samiti)\b", re.I)


def _km(lat1, lon1, lat2, lon2):
    p = math.pi / 180
    a = 0.5 - math.cos((lat2 - lat1) * p) / 2 + math.cos(lat1 * p) * math.cos(lat2 * p) * (1 - math.cos((lon2 - lon1) * p)) / 2
    return 12742 * math.asin(math.sqrt(max(a, 0.0)))


class _Grid:
    """Tiny spatial index: points bucketed in CELL-degree cells; search grows ring by ring."""

    def __init__(self, lats, lons):
        self.lats, self.lons, self.cells = lats, lons, {}
        for i, (la, lo) in enumerate(zip(lats, lons)):
            self.cells.setdefault((int(la // CELL), int(lo // CELL)), []).append(i)

    def near(self, lat, lon, radius_km, keep=None):
        """Indices within radius_km sorted by distance (optionally filtered by keep(i))."""
        ci, cj = int(lat // CELL), int(lon // CELL)
        rings = int(radius_km / (111 * CELL * max(math.cos(math.radians(lat)), 0.3))) + 1
        out = []
        for di in range(-rings, rings + 1):
            for dj in range(-rings, rings + 1):
                for i in self.cells.get((ci + di, cj + dj), ()):
                    if keep is None or keep(i):
                        d = _km(lat, lon, self.lats[i], self.lons[i])
                        if d <= radius_km:
                            out.append((d, i))
        out.sort()
        return out


def _rows(name):
    with gzip.open(os.path.join(DATA, name), "rt", encoding="utf-8", newline="") as f:
        yield from csv.DictReader(f, delimiter="\t")


@lru_cache(maxsize=1)
def _places():
    P = {"name": [], "lat": [], "lon": [], "kind": [], "pop": [], "st": [], "dt": [], "dnorm": [], "alias": []}
    for r in _rows("india_places.tsv.gz"):
        P["name"].append(r["name"]); P["lat"].append(float(r["lat"])); P["lon"].append(float(r["lon"]))
        P["kind"].append(r["fcode"]); P["pop"].append(int(r["pop"] or 0)); P["st"].append(r["st"]); P["dt"].append(r["dt"])
        P["dnorm"].append(r["dnorm"]); P["alias"].append(r["alias"])
    P["grid"] = _Grid(P["lat"], P["lon"])
    # prefix-search index on lower-case names and aliases
    keys = [(n.lower(), i) for i, n in enumerate(P["name"])]
    for i, al in enumerate(P["alias"]):
        if al:
            keys += [(a.lower(), i) for a in al.split("|")]
    keys.sort()
    P["keys"], P["key_s"] = keys, [k for k, _ in keys]
    return P


@lru_cache(maxsize=1)
def _pins():
    Z = {"pin": [], "place": [], "clean": [], "district": [], "dnorm": [], "state": [], "lat": [], "lon": [], "acc": [], "town": [], "town_pop": []}
    for r in _rows("india_pins.tsv.gz"):
        Z["pin"].append(r["pin"]); Z["place"].append(r["place"]); Z["clean"].append(r["place_clean"])
        Z["district"].append(r["district"]); Z["dnorm"].append(r["dnorm"]); Z["state"].append(r["state"])
        Z["lat"].append(float(r["lat"])); Z["lon"].append(float(r["lon"])); Z["acc"].append(int(r["acc"]))
        Z["town"].append(r["town"]); Z["town_pop"].append(int(r["town_pop"] or 0))
    Z["grid"] = _Grid(Z["lat"], Z["lon"])
    by_pin = {}
    for i, p in enumerate(Z["pin"]):
        by_pin.setdefault(p, []).append(i)
    Z["by_pin"], Z["pin_s"] = by_pin, sorted(by_pin)
    keys = sorted((c.lower(), i) for i, c in enumerate(Z["clean"]) if c)
    Z["keys"], Z["key_s"] = keys, [k for k, _ in keys]
    return Z


def warm():
    _places(); _pins()


def _pin_centre(rows):
    """Medoid of a PIN's post offices: the point with most sibling offices within 5 km (robust to a stray row)."""
    Z = _pins()
    pts = list({(Z["lat"][i], Z["lon"][i]): i for i in rows}.items())
    best = max(pts, key=lambda pi: (sum(_km(pi[0][0], pi[0][1], q[0][0], q[0][1]) <= 5 for q in pts), Z["acc"][pi[1]]))
    return best[0][0], best[0][1], Z["acc"][best[1]]


def _same_district(a, b):
    return a == b or (a and b and a.split()[0] == b.split()[0] and (" " not in a or " " not in b))


GENERIC = {"sector", "block", "colony", "phase", "pocket", "extension", "nagar", "village", "town", "city", "camp", "market"}


def describe(lat: float, lon: float) -> dict:
    """Name a point: locality, town/city, district, state, PIN. Distances let the UI say 'near'."""
    P, Z = _places(), _pins()
    in_bbox = INDIA_BBOX[0] <= lat <= INDIA_BBOX[2] and INDIA_BBOX[1] <= lon <= INDIA_BBOX[3]
    near_places = P["grid"].near(lat, lon, 30) if in_bbox else []
    if not near_places:
        return {"in_india": False}
    # state / district from the nearest populated places that carry them
    st = next((P["st"][i] for _, i in near_places if P["st"][i]), "")
    dt = next((P["dt"][i] for _, i in near_places[:40] if P["dt"][i]), "")
    dn = next((P["dnorm"][i] for _, i in near_places[:40] if P["dnorm"][i]), "")
    if not dt or dt.endswith("Division"):
        # a few GeoNames 'districts' in Maharashtra are revenue divisions - use India Post's district of the nearest office
        po_any = Z["grid"].near(lat, lon, 8)
        if po_any:
            dt = Z["district"][po_any[0][1]]
            dn = Z["dnorm"][po_any[0][1]]
    # PIN: GeoNames postal points are unreliable inside cities, so only offer a PIN when nearby post offices of the SAME
    # district agree (>= 2 offices, or one within 1 km). Otherwise say nothing rather than show a wrong PIN.
    # Only GeoNames-located offices (acc 3/4) count; our name-matched re-anchors (acc 2) are good enough for search, not for this.
    po = Z["grid"].near(lat, lon, 2.5, keep=lambda i: Z["acc"][i] >= 3 and (not dn or _same_district(Z["dnorm"][i], dn)))
    votes, rows = {}, {}
    for d, i in po[:10]:
        votes[Z["pin"][i]] = votes.get(Z["pin"][i], 0) + 1 / (d + 0.3)
        rows.setdefault(Z["pin"][i], set()).add(round(d, 2))
    pin = max(votes, key=votes.get) if votes else None
    if pin and not (len(rows[pin]) >= 2 and votes[pin] >= 0.6 * sum(votes.values())):
        pin = None  # fewer than two distinct agreeing offices, or no clear majority
    pin_km = min(rows[pin]) if pin else None
    # neighbourhood: nearest GeoNames populated place within 2.5 km with a real name (main gazetteer coordinates are good)
    loc, loc_km = None, None
    for d, i in near_places:
        if d > 2.5:
            break
        n = P["name"][i]
        if len(n) >= 4 and n.lower() not in GENERIC and not NOT_LOCALITY.search(n):
            loc, loc_km = n, d
            break
    # town / city: gravity score pop / (km + 1)^2 over towns >= 20,000 people within 25 km (Andheri -> Mumbai, Noida -> Noida)
    town, best = None, 0.0
    for d, i in near_places:
        if d <= 25 and P["pop"][i] >= 20000 and P["pop"][i] / (d + 1) ** 2 > best:
            town, best = P["name"][i], P["pop"][i] / (d + 1) ** 2
    if town and loc and town.lower() in loc.lower():
        loc = None if town.lower() == loc.lower() else loc
    label = ", ".join(x for x in [loc, town or (None if loc else P["name"][near_places[0][1]])] if x)
    return {"in_india": True, "label": label or dt or st, "locality": loc, "locality_km": round(loc_km, 1) if loc_km is not None else None,
            "town": town, "district": dt, "state": st, "pin": pin, "pin_km": round(pin_km, 1) if pin_km is not None else None,
            "source": "GeoNames (CC BY 4.0)"}


def search(q: str, limit: int = 8) -> list:
    """PIN code (full or prefix) or place name (prefix, aliases incl. Hindi). Towns rank above villages."""
    q = (q or "").strip()
    if len(q) < 2:
        return []
    out = []
    Z = _pins()
    if q.isdigit():
        if len(q) < 3:
            return []
        j = bisect.bisect_left(Z["pin_s"], q)
        for pin in Z["pin_s"][j:j + 40]:
            if not pin.startswith(q) or len(out) >= limit:
                break
            rows = Z["by_pin"][pin]
            lat, lon, acc = _pin_centre(rows)
            names = list(dict.fromkeys(Z["clean"][i] for i in rows if Z["clean"][i] and not NOT_LOCALITY.search(Z["clean"][i])))[:3]
            r0 = rows[0]
            out.append({"kind": "pin", "label": f"PIN {pin} · " + ", ".join(names or [Z["clean"][r0]]),
                        "sub": f'{Z["district"][r0]}, {Z["state"][r0]}', "lat": lat, "lon": lon, "pin": pin, "approx": acc <= 2})
        return out
    P = _places()
    ql = q.lower()
    cand = {}
    j = bisect.bisect_left(P["key_s"], ql)
    for k, i in P["keys"][j:j + 4000]:
        if not k.startswith(ql):
            break
        exact = k == ql
        score = (2 if exact else 0) + math.log10(P["pop"][i] + 10) + (1.5 if P["kind"][i].startswith("PPLA") or P["kind"][i] == "PPLC" else 0)
        if i not in cand or score > cand[i][0]:
            cand[i] = (score, "place")
    j = bisect.bisect_left(Z["key_s"], ql)
    seen_pins = set()
    for k, i in Z["keys"][j:j + 2000]:
        if not k.startswith(ql):
            break
        key = (Z["clean"][i].lower(), Z["pin"][i])
        if key in seen_pins or NOT_LOCALITY.search(Z["clean"][i]):
            continue
        seen_pins.add(key)
        cand[("pin", i)] = ((2 if k == ql else 0) + 0.6 * math.log10(Z["town_pop"][i] + 10) + (0.5 if Z["acc"][i] >= 3 else 0), "pin")
    ranked = sorted(cand.items(), key=lambda kv: -kv[1][0])
    seen = set()
    for key, (score, kind) in ranked:
        if kind == "place":
            i = key
            dt_i = "" if P["dt"][i].endswith("Division") else P["dt"][i]  # GeoNames lists some Maharashtra divisions as districts
            item = {"kind": "place", "label": P["name"][i], "sub": ", ".join(x for x in [dt_i, P["st"][i]] if x),
                    "lat": P["lat"][i], "lon": P["lon"][i], "town": P["pop"][i] >= 20000}
        else:
            i = key[1]
            where = ", ".join(dict.fromkeys(x for x in [Z["town"][i], Z["district"][i], Z["state"][i]] if x))
            item = {"kind": "locality", "label": Z["clean"][i], "sub": f'PIN {Z["pin"][i]} · {where}',
                    "lat": Z["lat"][i], "lon": Z["lon"][i], "pin": Z["pin"][i], "approx": Z["acc"][i] <= 2}
        sig = (item["label"].lower(), item["sub"].split("·")[-1].strip().lower())
        if sig in seen:
            continue
        seen.add(sig)
        out.append(item)
        if len(out) >= limit:
            break
    return out
