"""Structured claim schema. The model never writes free prose: it writes claims, each with the typed
fields the verifier needs. Rendering turns verified claims into text."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, PrivateAttr

ClaimKind = Literal["demographic", "condition", "medication", "allergy", "lab_value", "lab_trend",
                    "encounter", "absence", "note", "medication_issue"]


class Claim(BaseModel):
    id: str = ""
    section: str = ""
    kind: ClaimKind
    text: str = Field(description="One sentence shown to the reader")
    refs: list[str] = Field(default_factory=list, description="Handles cited, e.g. ['LAB-3','LAB-7']")
    value: float | str | None = None
    unit: str | None = None
    date: str | None = None            # YYYY-MM-DD of the cited fact
    status: str | None = None          # active | resolved | stopped ...
    trend: Literal["increasing", "decreasing", "stable"] | None = None
    absent_type: str | None = None     # for 'absence': FHIR resource type that is absent
    quote: str | None = None           # for 'note': verbatim span from the cited note
    _extra: dict = PrivateAttr(default_factory=dict)   # test-double bookkeeping only


class ClaimSet(BaseModel):
    claims: list[Claim]


class Verdict(BaseModel):
    claim: Claim
    ok: bool
    reasons: list[str] = Field(default_factory=list)   # empty when ok
    warnings: list[str] = Field(default_factory=list)  # kept, but counted (e.g. a direction label on noise)
    resolved_refs: list[str] = Field(default_factory=list)
