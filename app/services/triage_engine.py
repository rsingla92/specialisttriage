"""
Triage engine for BC specialist referrals.

Uses a rule-based scoring system informed by BC urology referral guidelines
(GPAC – Guidelines and Protocols Advisory Committee).  This produces an
appropriateness score, completeness score, urgency score, recommended priority,
and a list of missing/flagged items so the specialist and referring physician
receive actionable feedback.
"""
from __future__ import annotations

import re
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
    clinical_category: str = "other"
    missing_workup: list[str] = field(default_factory=list)


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
    "ct scan",
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


def _word_boundary_match(text: str, phrase: str) -> bool:
    """Return True if *phrase* appears in *text* at word boundaries.

    Preferred over plain substring search for short abbreviations (e.g. "psa")
    that could inadvertently match inside longer words (e.g. "capsaicin").
    """
    pattern = r"\b" + re.escape(phrase) + r"\b"
    return bool(re.search(pattern, text))


# ---------------------------------------------------------------------------
# Clinical category classification (priority order)
# ---------------------------------------------------------------------------

_CATEGORY_KEYWORDS: list[tuple[str, list[str]]] = [
    ("hematuria", [
        "hematuria", "blood in urine", "gross hematuria",
        "microscopic hematuria", "microhematuria",
    ]),
    ("stones", [
        "kidney stone", "renal calculi", "nephrolithiasis",
        "ureteral stone", "renal colic", "calculi",
    ]),
    ("uti_recurrent", [
        "recurrent uti", "frequent uti",
        "recurrent urinary tract infection",
    ]),
    ("psa_prostate", [
        "psa", "prostate", "elevated psa", "rising psa",
        "bph", "benign prostatic",
    ]),
    ("incontinence", [
        "incontinence", "urinary leakage",
        "stress incontinence", "urge incontinence",
    ]),
    ("erectile_dysfunction", [
        "erectile dysfunction", "impotence",
    ]),
]

# Short tokens that need word-boundary matching to avoid false positives
_SHORT_TOKENS = frozenset({"psa", "bph", "uti", "ed"})


def classify_category(all_text: str) -> str:
    """Return the primary clinical category for the referral text.

    Categories are checked in priority order (hematuria first, ED last).
    Returns ``"other"`` when nothing matches.
    """
    for category, keywords in _CATEGORY_KEYWORDS:
        for kw in keywords:
            if len(kw) <= 3 or kw in _SHORT_TOKENS:
                if _word_boundary_match(all_text, kw):
                    return category
            elif kw in all_text:
                return category
    return "other"


def _all_matched_categories(all_text: str) -> list[str]:
    """Return every category that matches (for flagging secondary categories)."""
    matched = []
    for category, keywords in _CATEGORY_KEYWORDS:
        for kw in keywords:
            if len(kw) <= 3 or kw in _SHORT_TOKENS:
                if _word_boundary_match(all_text, kw):
                    matched.append(category)
                    break
            elif kw in all_text:
                matched.append(category)
                break
    return matched


# ---------------------------------------------------------------------------
# Per-category missing workup detection
# ---------------------------------------------------------------------------

_CATEGORY_REQUIRED_WORKUP: dict[str, list[tuple[str, list[str]]]] = {
    "hematuria": [
        ("Urinalysis", ["urinalysis", "ua", "urine dip"]),
        ("Urine cytology", ["urine cytology", "cytology"]),
        ("Imaging (CT urogram or US KUB)",
         ["ct urogram", "ct kub", "ultrasound", "us kub", "renal ultrasound", "ct scan"]),
        ("Serum creatinine", ["creatinine", "egfr"]),
    ],
    "psa_prostate": [
        ("PSA value", ["psa"]),
        ("DRE findings", ["dre", "digital rectal", "rectal exam"]),
        ("Prior PSA values", ["prior psa", "previous psa", "psa history"]),
        ("Family history of prostate cancer", ["family history", "fhx"]),
    ],
    "stones": [
        ("CT KUB imaging", ["ct kub", "ct scan", "ct urogram"]),
        ("Serum creatinine", ["creatinine", "egfr"]),
        ("Urinalysis", ["urinalysis", "ua", "urine dip"]),
    ],
    "incontinence": [
        ("Voiding diary", ["voiding diary"]),
        ("Urinalysis", ["urinalysis", "ua"]),
        ("Post-void residual", ["post-void residual", "pvr", "post void"]),
    ],
    "uti_recurrent": [
        ("Urine C&S", ["urine culture", "urine c&s", "c&s", "culture and sensitivity"]),
        ("Imaging (US KUB)", ["ultrasound", "us kub", "renal ultrasound"]),
        ("Antibiotic history", ["antibiotic", "antimicrobial"]),
    ],
}

_WORKUP_PENALTY = 10  # completeness deduction per missing workup item

# Public alias for use outside the triage engine (e.g. pathway pages)
CATEGORY_REQUIRED_WORKUP: dict[str, list[tuple[str, list[str]]]] = _CATEGORY_REQUIRED_WORKUP


def detect_missing_workup(category: str, all_text: str) -> list[str]:
    """Return labels for workup items not found in the referral text."""
    required = _CATEGORY_REQUIRED_WORKUP.get(category, [])
    missing = []
    for label, keywords in required:
        found = False
        for kw in keywords:
            if len(kw) <= 3:
                if _word_boundary_match(all_text, kw):
                    found = True
                    break
            elif kw in all_text:
                found = True
                break
        if not found:
            missing.append(label)
    return missing


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
    # 0. Clinical classification
    # ------------------------------------------------------------------
    output.clinical_category = classify_category(all_text)
    output.missing_workup = detect_missing_workup(output.clinical_category, all_text)

    # Flag secondary categories if multiple match
    all_cats = _all_matched_categories(all_text)
    if len(all_cats) > 1:
        secondary = [c for c in all_cats if c != output.clinical_category]
        output.flags.append(
            f"ℹ️ Also matches: {', '.join(secondary)}"
        )

    # Flag erectile dysfunction as potentially inappropriate per committee
    if output.clinical_category == "erectile_dysfunction":
        output.flags.append(
            "⚠️ ED referral – typically managed in primary care. Review before accepting."
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

    # Per-category workup check replaces generic investigation check
    if output.clinical_category != "other" and output.missing_workup:
        completeness -= len(output.missing_workup) * _WORKUP_PENALTY
    elif referral.specialty_requested.lower() in ("urology", "urologist"):
        # Fallback: generic investigation check for "other" category
        found_investigations = [
            inv for inv in _STRONGLY_RECOMMENDED_UROLOGY
            if _word_boundary_match(all_text, inv)
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
