"""
Triage engine for BC specialist referrals.

Uses a rule-based scoring system informed by BC urology referral guidelines
(GPAC – Guidelines and Protocols Advisory Committee).  This produces an
appropriateness score, completeness score, urgency score, recommended priority,
and a list of missing/flagged items so the specialist and referring physician
receive actionable feedback.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ReferralData:
    """Parsed referral information passed into the triage engine."""

    chief_complaint: str = ""
    clinical_notes: str = ""
    relevant_history: str = ""
    current_medications: str = ""
    allergies: str = ""
    relevant_investigations: str = ""
    patient_age: int | None = None
    specialty_requested: str = "Urology"


@dataclass
class TriageOutput:
    """Output produced by the triage engine for a single referral."""

    appropriateness_score: int = 0   # 0–100
    completeness_score: int = 0      # 0–100
    urgency_score: int = 0           # 0–100
    recommended_priority: str = "routine"
    missing_information: list[str] = field(default_factory=list)
    triage_notes: str = ""
    flags: list[str] = field(default_factory=list)
    model_version: str = "rules-v1.0"


# ---------------------------------------------------------------------------
# Scoring weights and thresholds
# ---------------------------------------------------------------------------

_REQUIRED_FIELD_PENALTY = 20        # completeness deduction per missing required field
_INVESTIGATION_PENALTY = 15         # completeness deduction for missing investigations
_INAPPROPRIATE_PENALTY = 25         # appropriateness deduction per inappropriate keyword
_MISSING_FIELD_APPROPRIATENESS_PENALTY = 5  # appropriateness deduction per missing field
_URGENT_KEYWORD_WEIGHT = 20         # urgency score increment per urgent keyword
_HIGH_KEYWORD_WEIGHT = 10           # urgency score increment per high-priority keyword

# ---------------------------------------------------------------------------
# Keyword dictionaries
# ---------------------------------------------------------------------------

# Red-flag symptoms that trigger urgent or high priority
_URGENT_KEYWORDS = [
    "gross hematuria", "frank hematuria", "clot retention", "urosepsis",
    "acute urinary retention", "obstructive uropathy", "renal colic",
    "testicular torsion", "priapism", "fournier", "ureteral obstruction",
    "hydronephrosis", "bladder cancer", "renal mass", "transitional cell",
    "urothelial carcinoma", "elevated creatinine", "acute kidney injury",
    "aki",
]

_HIGH_PRIORITY_KEYWORDS = [
    "psa >", "rising psa", "prostate cancer", "suspicious nodule",
    "microhematuria", "microscopic hematuria", "recurrent uti",
    "recurrent urinary tract infection", "voiding dysfunction", "overactive bladder",
    "incontinence", "nocturia", "stone", "calculi", "varicocele",
    "erectile dysfunction", "benign prostatic", "bph",
]

_INAPPROPRIATE_KEYWORDS = [
    "physiotherapy", "weight loss", "dietary", "refer to gp",
    "not a urology issue",
]

# Required fields for a complete urology referral (GPAC guideline-based)
_REQUIRED_FIELDS_UROLOGY = [
    ("chief_complaint", "Chief complaint / reason for referral"),
    ("relevant_history", "Relevant past medical and surgical history"),
    ("current_medications", "Current medications list"),
    ("relevant_investigations", "Relevant investigations (urinalysis, PSA, imaging, etc.)"),
]

_STRONGLY_RECOMMENDED_UROLOGY = [
    "urinalysis",
    "psa",
    "ultrasound",
    "ct",
    "urine culture",
    "creatinine",
    "voiding diary",
]


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _lower(*texts: str) -> str:
    """Concatenate and lower-case multiple text fields for keyword scanning."""
    return " ".join(t.lower() for t in texts if t)


def _contains_any(text: str, keywords: list[str]) -> list[str]:
    return [kw for kw in keywords if kw in text]


# ---------------------------------------------------------------------------
# Core triage function
# ---------------------------------------------------------------------------

def triage_referral(referral: ReferralData) -> TriageOutput:
    """
    Evaluate a referral and return a :class:`TriageOutput`.

    Scoring methodology
    -------------------
    * **Appropriateness** – does the complaint match the specialty?
      Deductions for inappropriate keywords; bonuses for condition-specific
      keywords.
    * **Completeness** – are the minimum required fields populated?
      Each missing required field deducts from the score; missing recommended
      investigations also deduct points.
    * **Urgency** – how quickly does the patient need to be seen?
      Based on red-flag/high-priority keyword detection.
    """
    output = TriageOutput()
    all_text = _lower(
        referral.chief_complaint,
        referral.clinical_notes,
        referral.relevant_history,
        referral.current_medications,
        referral.relevant_investigations,
    )

    # ------------------------------------------------------------------
    # 1. Completeness scoring
    # ------------------------------------------------------------------
    completeness = 100
    missing = []

    required_fields = _REQUIRED_FIELDS_UROLOGY if referral.specialty_requested.lower() in (
        "urology", "urologist"
    ) else [
        ("chief_complaint", "Chief complaint / reason for referral"),
        ("relevant_history", "Relevant past medical history"),
        ("current_medications", "Current medications list"),
    ]

    for field_name, label in required_fields:
        value = getattr(referral, field_name, "")
        if not value or not str(value).strip():
            missing.append(label)
            completeness -= _REQUIRED_FIELD_PENALTY

    # Check for at least one investigation result in urology referrals
    if referral.specialty_requested.lower() in ("urology", "urologist"):
        found_investigations = [
            inv for inv in _STRONGLY_RECOMMENDED_UROLOGY if inv in all_text
        ]
        if not found_investigations:
            missing.append(
                "Relevant investigations: urinalysis, PSA, imaging results, urine culture, "
                "or creatinine are strongly recommended before specialist referral"
            )
            completeness -= _INVESTIGATION_PENALTY

    output.completeness_score = max(0, completeness)
    output.missing_information = missing

    # ------------------------------------------------------------------
    # 2. Urgency / Appropriateness scoring
    # ------------------------------------------------------------------
    urgent_matches = _contains_any(all_text, _URGENT_KEYWORDS)
    high_matches = _contains_any(all_text, _HIGH_PRIORITY_KEYWORDS)
    inappropriate_matches = _contains_any(all_text, _INAPPROPRIATE_KEYWORDS)

    urgency = 30  # baseline
    if urgent_matches:
        urgency = min(100, urgency + len(urgent_matches) * _URGENT_KEYWORD_WEIGHT)
        for kw in urgent_matches:
            output.flags.append(f"🚨 Urgent indicator: '{kw}'")
    elif high_matches:
        urgency = min(80, urgency + len(high_matches) * _HIGH_KEYWORD_WEIGHT)
        for kw in high_matches[:3]:  # cap flag noise
            output.flags.append(f"⚠️ High priority indicator: '{kw}'")

    output.urgency_score = urgency

    # Appropriateness
    appropriateness = 60  # start neutral
    if inappropriate_matches:
        appropriateness -= len(inappropriate_matches) * _INAPPROPRIATE_PENALTY
        for kw in inappropriate_matches:
            output.flags.append(f"❌ Possibly inappropriate for specialty: '{kw}'")
    if urgent_matches or high_matches:
        appropriateness = min(100, appropriateness + 20)
    if missing:
        appropriateness -= len(missing) * _MISSING_FIELD_APPROPRIATENESS_PENALTY

    output.appropriateness_score = max(0, min(100, appropriateness))

    # ------------------------------------------------------------------
    # 3. Priority recommendation
    # ------------------------------------------------------------------
    if urgency >= 80 or (urgent_matches and appropriateness >= 50):
        output.recommended_priority = "urgent"
    elif urgency >= 60 or (high_matches and appropriateness >= 50):
        output.recommended_priority = "high"
    elif appropriateness < 25 or inappropriate_matches:
        output.recommended_priority = "inappropriate"
    elif output.completeness_score < 40:
        output.recommended_priority = "needs_info"
    elif urgency >= 40:
        output.recommended_priority = "routine"
    else:
        output.recommended_priority = "low"

    # ------------------------------------------------------------------
    # 4. Narrative triage notes
    # ------------------------------------------------------------------
    notes_parts = []

    if urgent_matches:
        notes_parts.append(
            f"Referral contains urgent red-flag indicator(s): "
            f"{', '.join(urgent_matches[:3])}. Recommend expedited review."
        )
    elif high_matches:
        notes_parts.append(
            f"Referral contains high-priority indicator(s): "
            f"{', '.join(high_matches[:3])}."
        )

    if missing:
        notes_parts.append(
            "The following information is missing and should be requested from the "
            f"referring physician: {'; '.join(missing)}."
        )

    if inappropriate_matches:
        notes_parts.append(
            "This referral may not require specialist intervention. "
            "Consider redirecting to a more appropriate provider."
        )

    if referral.patient_age and referral.patient_age > 70 and "psa" not in all_text:
        notes_parts.append(
            "Patient is over 70 years of age. Consider whether PSA/DRE has been performed."
        )
        output.flags.append("ℹ️ Patient >70 – PSA status unclear from referral")

    if not notes_parts:
        notes_parts.append(
            "Referral appears appropriately worked up. Routine processing recommended."
        )

    output.triage_notes = " ".join(notes_parts)

    return output
