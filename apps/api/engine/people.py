"""People at home (spec §5.3, §7.2). For self-managed homes these come from the phone with each request and are
never stored. The heat level stays weather-only; per person we only work out the fan group, the hours that matter
and whether the day is riskier for them (no per-person level)."""
OLDER = {"older_65_74", "older_75_plus"}
YOUNG = {"infant_0_1", "child_1_5", "child_6_14"}


def from_vulnerable(vulnerable: list) -> list[dict]:
    """The old form's list -> people (spec §5.3). 'chronic' stays an unspecified condition, never guessed as 'heart'."""
    out: list[dict] = []
    for v in dict.fromkeys(vulnerable or []):
        if v == "elderly":
            out.append({"age_band": "older_65_74"})
        elif v == "child":
            out.append({"age_band": "child_1_5"})
        elif v == "pregnant":
            out.append({"age_band": "adult_15_64", "pregnant": True})
        elif v == "chronic":
            out.append({"age_band": "adult_15_64", "conditions": ["unspecified"]})
        elif v == "outdoor_worker":
            out.append({"age_band": "adult_15_64", "outdoor_work": True})
    return out


def fan_group(p: dict) -> tuple[str, bool]:
    """(group, precautionary). Anticholinergic medicines have their own verified limit; older people theirs;
    infants, children, pregnancy, any condition or other medicines use the older limit as a precaution."""
    meds = set(p.get("medicine_classes") or [])
    if "anticholinergic" in meds:
        return "anticholinergic", False
    if p.get("age_band") in OLDER:
        return "older", False
    if p.get("age_band") in YOUNG or p.get("pregnant") or p.get("conditions") or meds:
        return "older", True
    return "adult", False


def care_reasons(p: dict) -> list[str]:
    """Why heat is riskier for this person (codes; the texts live in data/actions.json)."""
    r = []
    band = p.get("age_band")
    if band in OLDER:
        r.append("older")
    if band == "infant_0_1":
        r.append("infant")
    elif band in YOUNG:
        r.append("child")
    if p.get("pregnant"):
        r.append("pregnant")
    if p.get("conditions"):
        r.append("condition")
    if p.get("medicine_classes"):
        r.append("medicine")
    if p.get("lives_alone"):
        r.append("lives_alone")
    if p.get("outdoor_work"):
        r.append("outdoor_work")
    return r


def role(p: dict) -> str:
    """A default way to name the person when there's no nickname (codes; texts in data/actions.json)."""
    band = p.get("age_band")
    if band == "infant_0_1":
        return "baby"
    if band in YOUNG:
        return "child"
    if band in OLDER:
        return "older"
    if p.get("pregnant"):
        return "pregnant"
    if p.get("outdoor_work"):
        return "worker"
    return "member"
