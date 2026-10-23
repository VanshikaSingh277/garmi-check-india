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


DEVANAGARI = re.compile(r"[\u0900-\u097F]")


def _fixes():
    with open(os.path.join(ROOT, "apps", "api", "data", "fixes.json"), encoding="utf-8") as f:
        return json.load(f)


def test_fix_catalogue_has_both_languages():
    """Every English field of every fix has a Hindi one, written in Devanagari, with the same placeholders."""
    cat = _fixes()
    assert cat["fixes"]
    for f in cat["fixes"]:
        pairs = [(k, f[k], f.get(k[:-3] + "_hi")) for k in f if k.endswith("_en") and f[k]]
        e = f.get("effect") or {}
        if e.get("note_en"):
            pairs.append(("effect.note_en", e["note_en"], e.get("note_hi")))
        for k, en, hi in pairs:
            assert hi, (f["id"], k)
            if isinstance(en, list):
                assert isinstance(hi, list) and len(hi) == len(en), (f["id"], k)
                assert all(DEVANAGARI.search(x) for x in hi), (f["id"], k)
            else:
                assert DEVANAGARI.search(hi), (f["id"], k, hi)


def test_fix_catalogue_labels_have_both_languages():
    cat = _fixes()
    def walk(node, path):
        if isinstance(node, dict) and "en" in node:
            assert node.get("hi"), path
            assert placeholders(node["en"]) == placeholders(node["hi"]), path
        elif isinstance(node, dict):
            for k, v in node.items():
                walk(v, path + "." + k)
    walk(cat["labels"], "labels")
    for c in cat["causes"]:
        assert c.get("label_hi") and DEVANAGARI.search(c["label_hi"]), c["id"]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
