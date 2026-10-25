"""Input models shared by the family, saved-home and worker routes (spec §5.3, §6.1): extra fields, NaN and unknown
values are rejected (422), never guessed."""
from typing import Annotated, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Clock = Annotated[str, StringConstraints(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")]
Nickname = Annotated[str, StringConstraints(pattern=r"^[\w .'-]{1,30}$")]      # letters (any script), digits, spaces, . ' -
AgeBand = Literal["infant_0_1", "child_1_5", "child_6_14", "adult_15_64", "older_65_74", "older_75_plus"]
Condition = Literal["heart", "kidney", "diabetes", "respiratory", "mental_health", "bedridden", "unspecified"]
MedicineClass = Literal["water_pill", "bp_ace_arb", "anticholinergic", "psychiatric", "other"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Problem(Exception):
    """An API error answered as {"error": code, "message": short} (spec §6.1)."""

    def __init__(self, status: int, code: str, message: str, headers: dict | None = None):
        self.status, self.code, self.message, self.headers = status, code, message, headers or {}


class Person(Strict):
    """One person at home. Self-managed homes keep these on the phone and send them with each request; worker-managed
    homes store them encrypted (spec §5.1, §5.3). Classes only: never diagnoses or drug names."""
    age_band: AgeBand
    pregnant: bool = False
    conditions: List[Condition] = Field(default=[], max_length=6)
    medicine_classes: List[MedicineClass] = Field(default=[], max_length=5)
    lives_alone: bool = False
    outdoor_work: bool = False
    work_start: Optional[Clock] = None
    work_end: Optional[Clock] = None
    work_type: Optional[Literal["construction", "vendor", "delivery", "farm", "traffic", "other"]] = None
    nickname: Optional[Nickname] = None      # self-managed: shown back only in the answer, never stored or logged
