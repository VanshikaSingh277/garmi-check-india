"""Copy checks: English and Hindi must say the same things in the same slots, so a reworded string can never drop a
number placeholder or leave a screen half-translated.
Run from the repo root:  python tests/test_i18n.py"""
import csv
import json
import os
import re

ROOT = os.path.join(os.path.dirname(__file__), "..")
I18N = os.path.join(ROOT, "apps", "web", "src", "i18n")
LINE = re.compile(r'^  ([a-z0-9_]+): (".*"),$')


def load(lang):
    out = {}
    with open(os.path.join(I18N, lang + ".js"), encoding="utf-8") as f:
        for line in f:
            m = LINE.match(line.rstrip("\n"))
            if m:
                assert m.group(1) not in out, "duplicate key " + m.group(1)
                out[m.group(1)] = json.loads(m.group(2))
    return out


def placeholders(s):
    return sorted(re.findall(r"\{\w+\}", s))


def test_same_keys():
    en, hi = load("en"), load("hi")
    assert len(en) > 400, len(en)
    assert set(en) == set(hi), (sorted(set(en) - set(hi)), sorted(set(hi) - set(en)))


def test_same_placeholders():
    en, hi = load("en"), load("hi")
    bad = [k for k in en if placeholders(en[k]) != placeholders(hi[k])]
    assert not bad, bad


def test_no_empty_or_untranslated():
    en, hi = load("en"), load("hi")
    assert not [k for k, v in en.items() if not v.strip()]
    assert not [k for k, v in hi.items() if not v.strip()]
    # a Hindi string with no Devanagari at all is usually a copy-paste of the English (short codes like "ID" are fine)
    latin_only = [k for k, v in hi.items() if len(v) > 12 and not re.search(r"[ऀ-ॿ]", v)]
    assert not latin_only, latin_only


def test_emergency_numbers_everywhere():
    en, hi = load("en"), load("hi")
    for k in ("disclaimer", "cool_first", "res_tip_extreme"):
        assert "108" in en[k] and "108" in hi[k], k


def test_solutions_csv_has_both_languages():
    with open(os.path.join(ROOT, "apps", "api", "data", "solutions.csv"), newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows
    for r in rows:
        for col in ("name", "what"):
            assert r[col + "_en"].strip() and r[col + "_hi"].strip(), (r["id"], col)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
