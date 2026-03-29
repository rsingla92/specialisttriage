"""Public FP pre-referral pathway pages."""
from flask import Blueprint, render_template, abort
from app.models import VALID_CATEGORIES
from app.services.triage_engine import CATEGORY_REQUIRED_WORKUP

pathways_bp = Blueprint("pathways", __name__)

# Category display names
_CATEGORY_LABELS = {
    "hematuria": "Hematuria",
    "psa_prostate": "PSA / Prostate",
    "stones": "Kidney Stones",
    "incontinence": "Incontinence",
    "uti_recurrent": "Recurrent UTI",
    "erectile_dysfunction": "Erectile Dysfunction",
}

# Pre-referral guidance per category
_PRE_REFERRAL_GUIDANCE = {
    "hematuria": {
        "consider_before": [
            "Treat UTI if culture positive, recheck in 6 weeks",
            "Assess medication causes (anticoagulants, NSAIDs)",
            "If microscopic only + normal imaging + age <40: monitor",
        ],
        "refer_if": (
            "Visible hematuria persisting after UTI treatment, abnormal imaging, "
            "age >40 with persistent microscopic hematuria, or any suspicion of malignancy."
        ),
    },
    "psa_prostate": {
        "consider_before": [
            "Repeat PSA in 6-8 weeks if initial value is mildly elevated",
            "Rule out UTI, recent ejaculation, or prostatitis as cause",
            "Assess life expectancy and patient preferences for screening",
        ],
        "refer_if": (
            "PSA consistently elevated (>4.0 or rising trend), abnormal DRE, "
            "or patient/family history concerning for prostate cancer."
        ),
    },
    "stones": {
        "consider_before": [
            "Trial of medical expulsive therapy for stones <10mm",
            "Ensure adequate hydration and pain management",
            "Strain urine for stone analysis if passed",
        ],
        "refer_if": (
            "Stone >10mm, obstructing stone with infection, recurrent stones, "
            "or stones requiring intervention."
        ),
    },
    "incontinence": {
        "consider_before": [
            "Trial of pelvic floor exercises for 3 months",
            "Review medications that may contribute",
            "Trial of bladder training for urge incontinence",
        ],
        "refer_if": (
            "Failed conservative management after 3 months, "
            "associated prolapse, neurological symptoms, or surgical candidate."
        ),
    },
    "uti_recurrent": {
        "consider_before": [
            "Confirm recurrence with urine C&S (not just symptoms)",
            "Trial of prophylactic measures (cranberry, hygiene counselling)",
            "Consider low-dose antibiotic prophylaxis",
        ],
        "refer_if": (
            "3+ culture-confirmed UTIs in 12 months despite prophylaxis, "
            "male patient with recurrent UTI, or suspected anatomical cause."
        ),
    },
    "erectile_dysfunction": {
        "consider_before": [
            "Assess cardiovascular risk factors (ED may be early marker)",
            "Trial of PDE5 inhibitor if no contraindications",
            "Screen for depression, medication side effects, hormonal causes",
        ],
        "refer_if": (
            "Failed PDE5 inhibitor trial, suspected Peyronie's disease, "
            "penile trauma, or secondary cause suspected."
        ),
    },
}


@pathways_bp.route("/pathways")
def index():
    """List all available pre-referral pathways."""
    categories = [
        {"slug": slug, "label": label}
        for slug, label in _CATEGORY_LABELS.items()
    ]
    return render_template("pathways/index.html", categories=categories)


@pathways_bp.route("/pathways/<category>")
def pathway(category):
    """Show the pre-referral pathway for a specific clinical category."""
    if category not in VALID_CATEGORIES or category == "other":
        abort(404)

    workup_items = CATEGORY_REQUIRED_WORKUP.get(category, [])
    guidance = _PRE_REFERRAL_GUIDANCE.get(category, {})

    return render_template(
        "pathways/pathway.html",
        category=category,
        label=_CATEGORY_LABELS.get(category, category),
        workup_items=workup_items,
        consider_before=guidance.get("consider_before", []),
        refer_if=guidance.get("refer_if", ""),
    )
