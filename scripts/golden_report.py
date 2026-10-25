"""Write docs/launch/GATE_P3_safety.md: the 12 golden safety cases (BACKEND_SPEC §10.1) with our actual outputs,
reasons and the verified_numbers.csv rows each one used. Offline (fixed forecasts).  Usage: python scripts/golden_report.py"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "..", "tests"), os.path.join(HERE, "..", "apps", "api")]
import conftest  # noqa: E402, F401  (throwaway database and test-only secrets)
from golden_cases import CASES  # noqa: E402

rows = []
for cid, title, fn in CASES:
    r, ok, expected = fn()
    risk = r["risk"]
    keys = sorted({x["source"]["key"] for x in risk["reasons"] if x.get("source")} | {r["fan"]["sources"][0]["key"]})
    pp = r["per_person"]
    out = (f"level **{risk['level']}** ({risk['station']}, headline {risk['headline_day']}); fan group {r['fan']['group']}"
           f" (avoid from {r['fan']['limits_c']['avoid_from']:g} °C); actions: {', '.join(a['code'] for a in r['today_actions']) or '—'}"
           + ("; per person: " + "; ".join(f"{p['label']}: higher_risk_today={p['higher_risk_today']}" for p in pp) if pp else ""))
    reasons = ", ".join(f"{x['code']}" + (f" ({x['value']})" if x.get("value") is not None else "") for x in risk["reasons"])
    rows.append(f"| {cid} | {title} | {expected} | {out} | {reasons} | {', '.join(keys)} | {'PASS' if ok else 'FAIL'} |")

doc = f"""# Gate after Phase 3: safety review

The 12 golden cases from BACKEND_SPEC §10.1, run through `/api/status/individual` with fixed test forecasts
(`tests/golden_cases.py`; regenerate with `python scripts/golden_report.py`). Generated {time.strftime('%Y-%m-%d %H:%M')}.

**Recommended:** a doctor or public-health person reviews this table, the per-person texts in
`apps/api/data/actions.json` and the fix texts in `apps/api/data/fixes.json`, together with the product owner.

| # | Case | Expected | Our output | Reasons | CSV rows used | Result |
|---|---|---|---|---|---|---|
{chr(10).join(rows)}

## What the reviewer should look at
- Fan limits per person (older 35/38 °C, anticholinergic 37 °C, others precautionary on the older limits) and that "fan alone not safe"
  never tells a family without a cooler or AC to switch the fan off.
- The infant line (WHO, "not even water"), the medicine and fluid lines ("don't stop them; ask a doctor"), and the "go somewhere cooler" line.
- That household factors never change the level (G5) and that IMD's warning only raises it (G12).
- Open items in `docs/TEAM_TODO.md`: AC setpoint, water interval and warm-night limit have no verified source, so no text uses them.

## Sign-off

| Reviewer | Role | Date | Decision (go / fix first) | Notes |
|---|---|---|---|---|
| | | | | |
"""
with open(os.path.join(HERE, "..", "docs", "launch", "GATE_P3_safety.md"), "w", encoding="utf-8") as f:
    f.write(doc)
print("\n".join(rows))
