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

# Deferred import to avoid circular dependency at module load time.
# The DB models are only needed when load_ruleset() actually queries;
# hardcoded-constant fallback paths never touch the ORM.
_db_models = None


def _get_db_models():
    global _db_models
    if _db_models is None:
        from app import models as m
        _db_models = m
    return _db_models


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
# DB-backed rule loading
# ---------------------------------------------------------------------------

@dataclass
class TriageRuleSet:
    """All clinical rules for one specialty, loaded from DB or hardcoded constants."""

    specialty_id: int | None = None
    # (slug, [(keyword, use_word_boundary), ...]) ordered by priority_order
    categories: list[tuple[str, list[tuple[str, bool]]]] = field(default_factory=list)
    # slug -> [(label, [(keyword, use_word_boundary), ...]), ...]
    workup_rules: dict[str, list[tuple[str, list[tuple[str, bool]]]]] = field(default_factory=dict)
    urgent_keywords: list[str] = field(default_factory=list)
    high_keywords: list[str] = field(default_factory=list)
    inappropriate_keywords: list[str] = field(default_factory=list)
    scoring: dict[str, int] = field(default_factory=dict)


_ruleset_cache: dict[int | None, TriageRuleSet] = {}


def _build_hardcoded_ruleset() -> TriageRuleSet:
    """Build a TriageRuleSet from the hardcoded constants (urology fallback)."""
    cats = []
    for slug, kw_list in _CATEGORY_KEYWORDS:
        cats.append((slug, [(kw, len(kw) <= 3 or kw in _SHORT_TOKENS) for kw in kw_list]))

    workup: dict[str, list[tuple[str, list[tuple[str, bool]]]]] = {}
    for slug, items in _CATEGORY_REQUIRED_WORKUP.items():
        workup[slug] = [
            (label, [(kw, len(kw) <= 3) for kw in kws])
            for label, kws in items
        ]

    return TriageRuleSet(
        specialty_id=None,
        categories=cats,
        workup_rules=workup,
        urgent_keywords=list(_URGENT_KEYWORDS),
        high_keywords=list(_HIGH_PRIORITY_KEYWORDS),
        inappropriate_keywords=list(_INAPPROPRIATE_KEYWORDS),
        scoring={
            "field_penalty": _REQUIRED_FIELD_PENALTY,
            "investigation_penalty": _INVESTIGATION_PENALTY,
            "inappropriate_penalty": _INAPPROPRIATE_PENALTY,
            "missing_field_appropriateness_penalty": _MISSING_FIELD_APPROPRIATENESS_PENALTY,
            "urgent_keyword_weight": _URGENT_KEYWORD_WEIGHT,
            "high_keyword_weight": _HIGH_KEYWORD_WEIGHT,
            "workup_penalty": _WORKUP_PENALTY,
        },
    )


def load_ruleset(specialty_id: int | None = None) -> TriageRuleSet:
    """Load clinical rules for a specialty from DB, with hardcoded fallback.

    Results are cached by specialty_id for the lifetime of the process.
    """
    if specialty_id in _ruleset_cache:
        return _ruleset_cache[specialty_id]

    if specialty_id is None:
        rs = _build_hardcoded_ruleset()
        _ruleset_cache[None] = rs
        return rs

    try:
        m = _get_db_models()
        specialty = m.Specialty.query.get(specialty_id)
        if not specialty:
            rs = _build_hardcoded_ruleset()
            _ruleset_cache[specialty_id] = rs
            return rs

        # Load categories ordered by priority
        db_cats = (
            m.ClinicalCategory.query
            .filter_by(specialty_id=specialty_id, is_active=True)
            .order_by(m.ClinicalCategory.priority_order)
            .all()
        )
        if not db_cats:
            rs = _build_hardcoded_ruleset()
            _ruleset_cache[specialty_id] = rs
            return rs

        cats = []
        workup: dict[str, list[tuple[str, list[tuple[str, bool]]]]] = {}
        for cat in db_cats:
            kws = [(ck.keyword, ck.use_word_boundary) for ck in cat.keywords]
            cats.append((cat.slug, kws))

            items = []
            for wi in cat.workup_items:
                det_kws = [(wk.keyword, wk.use_word_boundary) for wk in wi.detection_keywords]
                items.append((wi.label, det_kws))
            if items:
                workup[cat.slug] = items

        # Priority keywords
        urgent = [pk.keyword for pk in m.PriorityKeyword.query.filter_by(
            specialty_id=specialty_id, priority_level="urgent").all()]
        high = [pk.keyword for pk in m.PriorityKeyword.query.filter_by(
            specialty_id=specialty_id, priority_level="high").all()]
        inappropriate = [pk.keyword for pk in m.PriorityKeyword.query.filter_by(
            specialty_id=specialty_id, priority_level="inappropriate").all()]

        # Scoring config
        configs = {tc.config_key: tc.config_value
                   for tc in m.TriageConfig.query.filter_by(specialty_id=specialty_id).all()}

        rs = TriageRuleSet(
            specialty_id=specialty_id,
            categories=cats,
            workup_rules=workup,
            urgent_keywords=urgent,
            high_keywords=high,
            inappropriate_keywords=inappropriate,
            scoring=configs,
        )
        _ruleset_cache[specialty_id] = rs
        return rs
    except Exception:
        # DB not available (e.g., during tests with no app context) — use hardcoded
        rs = _build_hardcoded_ruleset()
        _ruleset_cache[specialty_id] = rs
        return rs


def clear_ruleset_cache():
    """Clear the cached rulesets (call after editing rules in admin)."""
    _ruleset_cache.clear()


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


def _match_keyword(text: str, keyword: str, use_word_boundary: bool) -> bool:
    """Check if a keyword matches in text, using word boundary if flagged."""
    if use_word_boundary:
        return _word_boundary_match(text, keyword)
    return keyword in text


def classify_category(all_text: str, ruleset: TriageRuleSet | None = None) -> str:
    """Return the primary clinical category for the referral text.

    Categories are checked in priority order (hematuria first, ED last).
    Returns ``"other"`` when nothing matches.
    """
    if ruleset and ruleset.categories:
        for slug, kw_pairs in ruleset.categories:
            for kw, use_wb in kw_pairs:
                if _match_keyword(all_text, kw, use_wb):
                    return slug
        return "other"

    # Fallback to hardcoded constants
    for category, keywords in _CATEGORY_KEYWORDS:
        for kw in keywords:
            if len(kw) <= 3 or kw in _SHORT_TOKENS:
                if _word_boundary_match(all_text, kw):
                    return category
            elif kw in all_text:
                return category
    return "other"


def _all_matched_categories(all_text: str, ruleset: TriageRuleSet | None = None) -> list[str]:
    """Return every category that matches (for flagging secondary categories)."""
    matched = []
    if ruleset and ruleset.categories:
        for slug, kw_pairs in ruleset.categories:
            for kw, use_wb in kw_pairs:
                if _match_keyword(all_text, kw, use_wb):
                    matched.append(slug)
                    break
        return matched

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


def detect_missing_workup(category: str, all_text: str, ruleset: TriageRuleSet | None = None) -> list[str]:
    """Return labels for workup items not found in the referral text."""
    if ruleset and ruleset.workup_rules:
        items = ruleset.workup_rules.get(category, [])
        missing = []
        for label, kw_pairs in items:
            if not any(_match_keyword(all_text, kw, use_wb) for kw, use_wb in kw_pairs):
                missing.append(label)
        return missing

    # Fallback to hardcoded constants
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

def triage_referral(referral: ReferralData, specialty_id: int | None = None) -> TriageOutput:
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
    ruleset = load_ruleset(specialty_id)

    # Extract scoring weights from ruleset (with hardcoded defaults)
    field_pen = ruleset.scoring.get("field_penalty", _REQUIRED_FIELD_PENALTY)
    workup_pen = ruleset.scoring.get("workup_penalty", _WORKUP_PENALTY)

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
    output.clinical_category = classify_category(all_text, ruleset)
    output.missing_workup = detect_missing_workup(output.clinical_category, all_text, ruleset)

    # Flag secondary categories if multiple match
    all_cats = _all_matched_categories(all_text, ruleset)
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
            completeness -= field_pen

    # Per-category workup check replaces generic investigation check
    if output.clinical_category != "other" and output.missing_workup:
        completeness -= len(output.missing_workup) * workup_pen
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
    rs_urgent = ruleset.urgent_keywords if ruleset.urgent_keywords else _URGENT_KEYWORDS
    rs_high = ruleset.high_keywords if ruleset.high_keywords else _HIGH_PRIORITY_KEYWORDS
    rs_inapp = ruleset.inappropriate_keywords if ruleset.inappropriate_keywords else _INAPPROPRIATE_KEYWORDS
    urgent_weight = ruleset.scoring.get("urgent_keyword_weight", _URGENT_KEYWORD_WEIGHT)
    high_weight = ruleset.scoring.get("high_keyword_weight", _HIGH_KEYWORD_WEIGHT)
    inapp_penalty = ruleset.scoring.get("inappropriate_penalty", _INAPPROPRIATE_PENALTY)
    workup_pen = ruleset.scoring.get("workup_penalty", _WORKUP_PENALTY)
    field_pen = ruleset.scoring.get("field_penalty", _REQUIRED_FIELD_PENALTY)

    urgent_matches = _contains_any(all_text, rs_urgent)
    high_matches = _contains_any(all_text, rs_high)
    inappropriate_matches = _contains_any(all_text, rs_inapp)

    urgency = 30  # baseline
    if urgent_matches:
        urgency = min(100, urgency + len(urgent_matches) * urgent_weight)
        for kw in urgent_matches:
            output.flags.append(f"🚨 Urgent indicator: '{kw}'")
    elif high_matches:
        urgency = min(80, urgency + len(high_matches) * high_weight)
        for kw in high_matches[:3]:  # cap flag noise
            output.flags.append(f"⚠️ High priority indicator: '{kw}'")

    output.urgency_score = urgency

    # Appropriateness
    appropriateness = 60  # start neutral
    if inappropriate_matches:
        appropriateness -= len(inappropriate_matches) * inapp_penalty
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
