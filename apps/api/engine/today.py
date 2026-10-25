"""Today actions and per-person advice (spec §7.2-7.3). Numbers in the texts come from the forecast (hours) or
verified_numbers.csv; the fan limits come from rules.fan_limits on the cautious (high) end of the room range.
- With an AC, outside power-cut hours, "fan alone not enough / not safe" becomes "run the AC" (never "turn off the fan").
- Without a cooler or AC, the fallback is "keep skin and clothes wet and use the fan, or move somewhere cooler".
- Outdoor workers: their work hours are judged on the OUTDOOR heat index and air temperature.
- Power cuts: during cut hours the home is planned without fan, cooler or AC.
- No per-person level: only higher_risk_today (bool) with reasons, fan state and actions."""
import json
import os
from functools import lru_cache

from . import people as P
from . import rules
from .solutions import fill_numbers

DATA = os.path.join(os.path.dirname(__file__), "..", "data", "actions.json")
WORK_DEFAULT = ("06:00", "19:00")       # daytime, when an outdoor worker gave no hours (design choice)
CARE = {"older", "infant", "child", "pregnant", "condition", "medicine"}


@lru_cache(maxsize=1)
def texts() -> dict:
    with open(DATA, encoding="utf-8") as f:
        return json.load(f)


def _t(section: str, key: str, lang: str) -> str:
    v = texts()[section][key]
    return v.get(lang) or v["en"]


def in_window(hhmm: str, win) -> bool:
    a, b = win
    return a <= hhmm < b if a <= b else (hhmm >= a or hhmm < b)      # a window may cross midnight


def ranges(times: list[str]) -> list[list[str]]:
    """['14:00', '15:00', '17:00'] (hourly, in order) -> [['14:00', '16:00'], ['17:00', '18:00']]."""
    out: list[list[str]] = []
    for t in times:
        end = f"{(int(t[:2]) + 1) % 24:02d}:00"
        if out and out[-1][1] == t:
            out[-1][1] = end
        else:
            out.append([t, end])
    return out


def fmt(rs: list[list[str]], lang: str) -> str:
    sep = " और " if lang == "hi" else ", "
    return sep.join(f"{a}–{b}" for a, b in rs)


def build(persons: list[dict], hours: list[dict], nxt: list[dict], plan: dict, level_idx: int, devices: dict,
          power_cut_hours: list, lang: str) -> dict:
    """persons: [{age_band, pregnant, conditions, medicine_classes, lives_alone, outdoor_work, work_start, work_end,
    work_type, nickname}]; hours: room estimate rows with 'high' (empty when there is none); nxt: outdoor rows."""
    by_time = {h["time"]: h for h in hours}
    has_cooling = bool(devices.get("cooler") or devices.get("ac"))
    fallback = _t("fallback", "with_cooling" if has_cooling else "no_cooling", lang)
    cut = [r["time"][11:16] for r in nxt if any(in_window(r["time"][11:16], w) for w in power_cut_hours or [])]
    actions: list[dict] = []

    def add(code: str, hours_: list | None = None, person: int | None = None, **values):
        text = fill_numbers(_t("actions", code, lang)).format(H=fmt(hours_ or [], lang), **values)
        row = {"code": code, "text": text}
        if hours_:
            row["hours"] = hours_
        if person is not None:
            row["person"] = person
        actions.append(row)

    # household actions
    if plan.get("close"):
        add("close_windows", plan["close"])
    if plan.get("open"):
        add("open_windows", plan["open"])
    if cut and set(cut) & set(plan.get("hottest") or []):
        add("power_cut_hot", ranges([t for t in cut if t in plan["hottest"]]))

    groups = [P.fan_group(p) for p in persons] or [("adult", False)]
    strict = rules.strictest([g for g, _ in groups])
    lim = rules.fan_limits(strict)
    if devices.get("ac"):
        ac_hours = [r["time"][11:16] for r in nxt if r["time"][11:16] not in cut
                    and (by_time.get(r["time"], {}).get("high") or r["t"]) >= lim["not_enough_from"]]
        if ac_hours:
            add("use_ac_hours", ranges(ac_hours))

    per_person = []
    for i, p in enumerate(persons):
        group, precautionary = groups[i]
        label = (p.get("nickname") or "").strip() or _t("roles", P.role(p), lang)
        reasons = P.care_reasons(p)
        avoid, enough = [], []
        for r in nxt:
            hhmm = r["time"][11:16]
            if devices.get("ac") and hhmm not in cut:
                continue                                            # the AC covers this hour
            temp = by_time.get(r["time"], {}).get("high") or r["t"]
            state = rules.fan_state(temp, group)
            if state == "avoid_fan_alone":
                avoid.append(hhmm)
            elif state == "fan_not_enough_alone":
                enough.append(hhmm)
        mine_before = len(actions)
        if avoid:
            add("fan_not_safe_for_person", ranges(avoid), i, label=label, fallback=fallback)
        elif enough:
            add("fan_not_enough_for_person", ranges(enough), i, label=label, fallback=fallback)
        work_hot: list[str] = []
        if p.get("outdoor_work"):
            win = (p.get("work_start") or WORK_DEFAULT[0], p.get("work_end") or WORK_DEFAULT[1])
            work_hot = [r["time"][11:16] for r in nxt if in_window(r["time"][11:16], win)
                        and rules.base_from_heat_index(max(r["hi"], r["t"])) >= 2]
            if work_hot:
                add("work_hours_hot", ranges(work_hot), i, label=label)
        hot = level_idx >= 1
        if hot and "lives_alone" in reasons and level_idx >= 2:
            add("check_on_alone", None, i, label=label)
        if hot and "infant" in reasons:
            add("infant_care", None, i, label=label)
        if hot and p.get("medicine_classes"):
            names = ", ".join(_t("medicine_classes", m, lang) for m in dict.fromkeys(p["medicine_classes"]))
            add("medicine_doctor", None, i, label=label, classes=names)
        if hot and set(p.get("conditions") or []) & {"heart", "kidney", "unspecified"}:
            add("fluid_limit", None, i, label=label)
        if hot and CARE & set(reasons):
            if not has_cooling and plan.get("hottest"):
                add("go_cooler", ranges(sorted(plan["hottest"])), i, label=label)
            add("extra_care", None, i, label=label)
        mine = [a["code"] for a in actions[mine_before:]]
        per_person.append({"person": i, "label": label, "fan_group": group, "precautionary": precautionary,
                           "fan_avoid_hours": ranges(avoid), "fan_not_enough_hours": ranges(enough), "work_hours_hot": ranges(work_hot),
                           "higher_risk_today": bool(avoid or work_hot or (hot and CARE & set(reasons))),
                           "reasons": reasons, "actions": mine})
    return {"per_person": per_person, "today_actions": actions, "fan_group": strict}
