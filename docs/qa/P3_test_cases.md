# Phase 3 test cases

Format: ID | Title | Preconditions | Steps | Expected | Priority | Type.
Runner: `python tests/qa/p3_qa.py <server-log>` against a running server (live forecast). The golden cases run offline in `tests/test_golden.py`.

| ID | Title | Preconditions | Steps | Expected | Priority | Type |
|---|---|---|---|---|---|---|
| P3-01 | Old form still works | — | POST status with `vulnerable: ["elderly","child"]` and no `people` | 200; `per_person` has two entries (older, child) | High | Functional |
| P3-02 | People list accepted | — | POST status with `people: [{age_band: older_65_74, lives_alone: true}, {age_band: infant_0_1}]` | 200; two per-person entries; `fan.group` = older | High | Functional |
| P3-03 | Level unchanged by people | — | Same place, with and without people | Same `risk.level` and reasons | High | Functional |
| P3-04 | No per-person level | P3-02 | Read `per_person[*]` | No `level` field; `higher_risk_today` is true/false | High | Functional |
| P3-05 | Nickname echoed, never logged | Server log file | Send nickname "Dadi"; read the reply and the server log | Label "Dadi" in the reply; "Dadi" nowhere in the log | High | Privacy |
| P3-06 | Unsafe nickname rejected | — | Nickname `<script>` | 422; the string isn't echoed | High | Security |
| P3-07 | Unknown person fields rejected | — | `conditions: ["cancer"]`, `medicine_classes: ["aspirin"]`, `name: "Ravi"`, `work_start: "25:00"` | 422 each | High | Negative |
| P3-08 | Hindi actions | — | `lang: hi` with an infant and an older person | Every `today_actions[*].text` has Hindi; no `{` placeholders left | High | Hindi/English |
| P3-09 | Power cut and AC inputs | — | `devices.ac: true`, `power_cut_hours: [["14:00","16:00"]]`; then a bad time `["14:00","26:00"]` | 200 with no AC action inside 14–16; then 422 | Medium | Functional |
| P3-10 | Golden cases G1–G12 | — | Automated: `tests/test_golden.py` | 12 pass; table in `docs/launch/GATE_P3_safety.md` | High | Safety |
| P3-11 | Per-person rules | — | Automated: `tests/test_people_rules.py` | Pass | High | Safety |
