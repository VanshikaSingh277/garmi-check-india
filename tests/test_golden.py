"""Golden safety cases G1-G12 (BACKEND_SPEC §10.1) through the full status endpoint. Phase 3 gate: GATE_P3_safety.md."""
import pytest

from golden_cases import CASES


@pytest.mark.parametrize("cid,title,fn", CASES, ids=[c[0] for c in CASES])
def test_golden(cid, title, fn):
    r, ok, expected = fn()
    assert ok, f"{cid} {title}: expected {expected}; got level={r['risk']['level']} reasons={[x['code'] for x in r['risk']['reasons']]} " \
               f"actions={[a['code'] for a in r['today_actions']]} fan={r['fan']['group']}"
