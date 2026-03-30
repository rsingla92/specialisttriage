"""Seed specialties and their clinical rules into the database.

Migrates hardcoded urology rules from triage_engine.py constants and adds
draft GI and orthopedics rules from Alberta SpecialistLink / common guidelines.
Idempotent: safe to re-run.
"""
from app.models import (
    Specialty, ClinicalCategory, CategoryKeyword, WorkupItem, WorkupKeyword,
    PriorityKeyword, PathwayGuidance, TriageConfig,
)

# ---------------------------------------------------------------------------
# Urology data (migrated from triage_engine.py hardcoded constants)
# ---------------------------------------------------------------------------

_UROLOGY = {
    "name": "Urology",
    "slug": "urology",
    "description": "Urological conditions including hematuria, prostate, stones, incontinence, UTI, ED",
    "categories": [
        {
            "slug": "hematuria", "display_name": "Hematuria", "priority_order": 0,
            "keywords": [
                ("hematuria", False), ("blood in urine", False), ("gross hematuria", False),
                ("microscopic hematuria", False), ("microhematuria", False),
            ],
            "workup": [
                ("Urinalysis", [("urinalysis", False), ("ua", True), ("urine dip", False)]),
                ("Urine cytology", [("urine cytology", False), ("cytology", False)]),
                ("Imaging (CT urogram or US KUB)", [
                    ("ct urogram", False), ("ct kub", False), ("ultrasound", False),
                    ("us kub", False), ("renal ultrasound", False), ("ct scan", False),
                ]),
                ("Serum creatinine", [("creatinine", False), ("egfr", True)]),
            ],
            "guidance": {
                "consider_before": [
                    "Treat UTI if culture positive, recheck in 6 weeks",
                    "Assess medication causes (anticoagulants, NSAIDs)",
                    "If microscopic only + normal imaging + age <40: monitor",
                ],
                "refer_if": "Visible hematuria persisting after UTI treatment, abnormal imaging, "
                            "age >40 with persistent microscopic hematuria, or any suspicion of malignancy.",
                "source": "BC GPAC Guidelines",
            },
        },
        {
            "slug": "psa_prostate", "display_name": "PSA / Prostate", "priority_order": 3,
            "keywords": [
                ("psa", True), ("prostate", False), ("elevated psa", False),
                ("rising psa", False), ("bph", True), ("benign prostatic", False),
            ],
            "workup": [
                ("PSA value", [("psa", True)]),
                ("DRE findings", [("dre", True), ("digital rectal", False), ("rectal exam", False)]),
                ("Prior PSA values", [("prior psa", False), ("previous psa", False), ("psa history", False)]),
                ("Family history of prostate cancer", [("family history", False), ("fhx", True)]),
            ],
            "guidance": {
                "consider_before": [
                    "Repeat PSA in 6-8 weeks if initial value is mildly elevated",
                    "Rule out UTI, recent ejaculation, or prostatitis as cause",
                    "Assess life expectancy and patient preferences for screening",
                ],
                "refer_if": "PSA consistently elevated (>4.0 or rising trend), abnormal DRE, "
                            "or patient/family history concerning for prostate cancer.",
                "source": "BC GPAC Guidelines",
            },
        },
        {
            "slug": "stones", "display_name": "Kidney Stones", "priority_order": 1,
            "keywords": [
                ("kidney stone", False), ("renal calculi", False), ("nephrolithiasis", False),
                ("ureteral stone", False), ("renal colic", False), ("calculi", False),
            ],
            "workup": [
                ("CT KUB imaging", [("ct kub", False), ("ct scan", False), ("ct urogram", False)]),
                ("Serum creatinine", [("creatinine", False), ("egfr", True)]),
                ("Urinalysis", [("urinalysis", False), ("ua", True), ("urine dip", False)]),
            ],
            "guidance": {
                "consider_before": [
                    "Trial of medical expulsive therapy for stones <10mm",
                    "Ensure adequate hydration and pain management",
                    "Strain urine for stone analysis if passed",
                ],
                "refer_if": "Stone >10mm, obstructing stone with infection, recurrent stones, "
                            "or stones requiring intervention.",
                "source": "BC GPAC Guidelines",
            },
        },
        {
            "slug": "uti_recurrent", "display_name": "Recurrent UTI", "priority_order": 2,
            "keywords": [
                ("recurrent uti", False), ("frequent uti", False),
                ("recurrent urinary tract infection", False),
            ],
            "workup": [
                ("Urine C&S", [("urine culture", False), ("urine c&s", False),
                               ("c&s", True), ("culture and sensitivity", False)]),
                ("Imaging (US KUB)", [("ultrasound", False), ("us kub", False), ("renal ultrasound", False)]),
                ("Antibiotic history", [("antibiotic", False), ("antimicrobial", False)]),
            ],
            "guidance": {
                "consider_before": [
                    "Confirm recurrence with urine C&S (not just symptoms)",
                    "Trial of prophylactic measures (cranberry, hygiene counselling)",
                    "Consider low-dose antibiotic prophylaxis",
                ],
                "refer_if": "3+ culture-confirmed UTIs in 12 months despite prophylaxis, "
                            "male patient with recurrent UTI, or suspected anatomical cause.",
                "source": "BC GPAC Guidelines",
            },
        },
        {
            "slug": "incontinence", "display_name": "Incontinence", "priority_order": 4,
            "keywords": [
                ("incontinence", False), ("urinary leakage", False),
                ("stress incontinence", False), ("urge incontinence", False),
            ],
            "workup": [
                ("Voiding diary", [("voiding diary", False)]),
                ("Urinalysis", [("urinalysis", False), ("ua", True)]),
                ("Post-void residual", [("post-void residual", False), ("pvr", True), ("post void", False)]),
            ],
            "guidance": {
                "consider_before": [
                    "Trial of pelvic floor exercises for 3 months",
                    "Review medications that may contribute",
                    "Trial of bladder training for urge incontinence",
                ],
                "refer_if": "Failed conservative management after 3 months, "
                            "associated prolapse, neurological symptoms, or surgical candidate.",
                "source": "BC GPAC Guidelines",
            },
        },
        {
            "slug": "erectile_dysfunction", "display_name": "Erectile Dysfunction", "priority_order": 5,
            "keywords": [
                ("erectile dysfunction", False), ("impotence", False),
            ],
            "workup": [],
            "guidance": {
                "consider_before": [
                    "Assess cardiovascular risk factors (ED may be early marker)",
                    "Trial of PDE5 inhibitor if no contraindications",
                    "Screen for depression, medication side effects, hormonal causes",
                ],
                "refer_if": "Failed PDE5 inhibitor trial, suspected Peyronie's disease, "
                            "penile trauma, or secondary cause suspected.",
                "source": "BC GPAC Guidelines",
            },
        },
    ],
    "priority_keywords": {
        "urgent": [
            "gross hematuria", "frank hematuria", "clot retention", "urosepsis",
            "acute urinary retention", "obstructive uropathy", "renal colic",
            "testicular torsion", "priapism", "fournier", "ureteral obstruction",
            "hydronephrosis", "bladder cancer", "renal mass", "transitional cell",
            "urothelial carcinoma", "elevated creatinine", "acute kidney injury", "aki",
        ],
        "high": [
            "psa >", "rising psa", "prostate cancer", "suspicious nodule",
            "microhematuria", "microscopic hematuria", "recurrent uti",
            "recurrent urinary tract infection", "voiding dysfunction", "overactive bladder",
            "incontinence", "nocturia", "stone", "calculi", "varicocele",
            "erectile dysfunction", "benign prostatic", "bph",
        ],
        "inappropriate": [
            "physiotherapy", "weight loss", "dietary", "refer to gp", "not a urology issue",
        ],
    },
    "scoring": {
        "field_penalty": 20,
        "investigation_penalty": 15,
        "inappropriate_penalty": 25,
        "missing_field_appropriateness_penalty": 5,
        "urgent_keyword_weight": 20,
        "high_keyword_weight": 10,
        "workup_penalty": 10,
    },
}

# ---------------------------------------------------------------------------
# GI data (draft from Alberta SpecialistLink pathways)
# ---------------------------------------------------------------------------

_GI = {
    "name": "Gastroenterology",
    "slug": "gi",
    "description": "DRAFT — needs specialist review. Based on Alberta SpecialistLink pathways.",
    "categories": [
        {
            "slug": "gerd_dyspepsia", "display_name": "GERD / Dyspepsia", "priority_order": 0,
            "keywords": [
                ("gerd", True), ("reflux", False), ("dyspepsia", False),
                ("heartburn", False), ("acid reflux", False),
            ],
            "workup": [
                ("H. pylori testing", [("h. pylori", False), ("h pylori", False),
                                        ("helicobacter", False), ("urea breath", False)]),
                ("Trial of PPI (4-8 weeks)", [("ppi", True), ("omeprazole", False),
                                               ("pantoprazole", False), ("proton pump", False)]),
            ],
            "guidance": {
                "consider_before": [
                    "Trial of PPI for 4-8 weeks",
                    "Test and treat H. pylori",
                    "Lifestyle modifications (diet, weight, elevation)",
                ],
                "refer_if": "Alarm features (dysphagia, weight loss, GI bleeding, anemia), "
                            "failed PPI trial, or age >50 with new-onset dyspepsia.",
                "source": "Alberta SpecialistLink — DRAFT",
            },
        },
        {
            "slug": "rectal_bleeding", "display_name": "Rectal Bleeding", "priority_order": 1,
            "keywords": [
                ("rectal bleeding", False), ("blood in stool", False), ("hematochezia", False),
                ("melena", False), ("occult blood", False),
            ],
            "workup": [
                ("CBC", [("cbc", True), ("complete blood count", False), ("hemoglobin", False)]),
                ("Iron studies", [("iron", False), ("ferritin", False), ("iron studies", False)]),
                ("FIT test", [("fit", True), ("fecal immunochemical", False), ("fobt", True)]),
            ],
            "guidance": {
                "consider_before": [
                    "Assess for hemorrhoidal source (bright red, painless, on wiping only)",
                    "Check CBC and iron studies for anemia",
                    "FIT testing if no overt bleeding",
                ],
                "refer_if": "Unexplained iron deficiency anemia, positive FIT, change in bowel habits >6 weeks, "
                            "age >40 with new rectal bleeding, or family history of colorectal cancer.",
                "source": "Alberta SpecialistLink — DRAFT",
            },
        },
        {
            "slug": "abnormal_liver", "display_name": "Abnormal Liver Enzymes", "priority_order": 2,
            "keywords": [
                ("liver enzymes", False), ("alt", True), ("ast", True),
                ("elevated alt", False), ("elevated ast", False),
                ("hepatitis", False), ("jaundice", False),
            ],
            "workup": [
                ("Liver panel (ALT, AST, ALP, GGT, bilirubin)", [
                    ("alt", True), ("ast", True), ("alp", True), ("ggt", True), ("bilirubin", False),
                ]),
                ("Hepatitis B & C serology", [("hepatitis b", False), ("hepatitis c", False),
                                                ("hbsag", True), ("anti-hcv", False)]),
                ("Abdominal ultrasound", [("ultrasound", False), ("abdominal us", False)]),
                ("Alcohol history", [("alcohol", False), ("etoh", True)]),
            ],
            "guidance": {
                "consider_before": [
                    "Repeat liver enzymes in 3-6 months if mildly elevated (<2x ULN)",
                    "Screen for hepatitis B and C",
                    "Assess alcohol intake and medications",
                    "Abdominal ultrasound to rule out biliary/fatty liver",
                ],
                "refer_if": "ALT/AST persistently >2x upper limit of normal, positive hepatitis serology, "
                            "signs of liver failure, or unexplained jaundice.",
                "source": "Alberta SpecialistLink — DRAFT",
            },
        },
        {
            "slug": "ibd", "display_name": "Inflammatory Bowel Disease", "priority_order": 3,
            "keywords": [
                ("ibd", True), ("crohn", False), ("ulcerative colitis", False),
                ("inflammatory bowel", False), ("colitis", False),
            ],
            "workup": [
                ("CBC + CRP/ESR", [("cbc", True), ("crp", True), ("esr", True)]),
                ("Fecal calprotectin", [("calprotectin", False), ("fecal calprotectin", False)]),
                ("Stool C&S + C. diff", [("stool culture", False), ("c. diff", False),
                                          ("c diff", False), ("cdiff", False)]),
            ],
            "guidance": {
                "consider_before": [
                    "Rule out infectious cause (stool cultures, C. diff)",
                    "Check inflammatory markers (CRP, ESR)",
                    "Fecal calprotectin to differentiate IBD from IBS",
                ],
                "refer_if": "Elevated fecal calprotectin (>200), bloody diarrhea >2 weeks, "
                            "weight loss with GI symptoms, or suspected IBD flare.",
                "source": "Alberta SpecialistLink — DRAFT",
            },
        },
    ],
    "priority_keywords": {
        "urgent": [
            "gi bleed", "hematemesis", "melena", "acute abdomen",
            "bowel obstruction", "perforation", "severe hepatitis",
            "acute liver failure", "variceal bleed",
        ],
        "high": [
            "dysphagia", "weight loss", "iron deficiency anemia",
            "positive fit", "rectal mass", "jaundice", "ascites",
            "ibd flare", "crohn flare",
        ],
        "inappropriate": [
            "constipation only", "dietary advice", "weight management",
        ],
    },
    "scoring": {
        "field_penalty": 20,
        "investigation_penalty": 15,
        "inappropriate_penalty": 25,
        "missing_field_appropriateness_penalty": 5,
        "urgent_keyword_weight": 20,
        "high_keyword_weight": 10,
        "workup_penalty": 10,
    },
}

# ---------------------------------------------------------------------------
# Orthopedics data (draft from common Canadian guidelines)
# ---------------------------------------------------------------------------

_ORTHO = {
    "name": "Orthopedics",
    "slug": "orthopedics",
    "description": "DRAFT — needs specialist review. Based on common Canadian orthopedic referral guidelines.",
    "categories": [
        {
            "slug": "knee_pain", "display_name": "Knee Pain", "priority_order": 0,
            "keywords": [
                ("knee pain", False), ("knee injury", False), ("knee swelling", False),
                ("meniscus", False), ("acl", True), ("mcl", True), ("knee arthritis", False),
            ],
            "workup": [
                ("X-ray (weight-bearing AP + lateral)", [("x-ray", False), ("xray", False),
                                                          ("radiograph", False)]),
                ("Trial of conservative management (6 weeks)", [
                    ("physiotherapy", False), ("conservative", False), ("nsaid", True),
                ]),
            ],
            "guidance": {
                "consider_before": [
                    "X-ray (weight-bearing views) before referral",
                    "6-week trial of physiotherapy + NSAIDs",
                    "Consider MRI only if mechanical symptoms (locking, giving way)",
                ],
                "refer_if": "Failed 6 weeks conservative management, locked knee, "
                            "acute ligament injury in active patient, or severe OA candidate for arthroplasty.",
                "source": "Common Canadian orthopedic guidelines — DRAFT",
            },
        },
        {
            "slug": "hip_pain", "display_name": "Hip Pain", "priority_order": 1,
            "keywords": [
                ("hip pain", False), ("hip arthritis", False), ("hip replacement", False),
                ("avascular necrosis", False), ("hip fracture", False),
            ],
            "workup": [
                ("X-ray (AP pelvis + lateral hip)", [("x-ray", False), ("xray", False),
                                                      ("radiograph", False)]),
                ("Trial of conservative management", [("physiotherapy", False), ("conservative", False)]),
            ],
            "guidance": {
                "consider_before": [
                    "X-ray (AP pelvis + lateral hip) before referral",
                    "Trial of physiotherapy, weight management, activity modification",
                    "NSAIDs or acetaminophen trial",
                ],
                "refer_if": "Severe OA with functional limitation despite conservative treatment, "
                            "suspected avascular necrosis, or acute fracture.",
                "source": "Common Canadian orthopedic guidelines — DRAFT",
            },
        },
        {
            "slug": "shoulder_pain", "display_name": "Shoulder Pain", "priority_order": 2,
            "keywords": [
                ("shoulder pain", False), ("rotator cuff", False), ("frozen shoulder", False),
                ("shoulder impingement", False), ("shoulder dislocation", False),
            ],
            "workup": [
                ("X-ray (AP + axillary)", [("x-ray", False), ("xray", False), ("radiograph", False)]),
                ("Trial of physiotherapy (6-12 weeks)", [("physiotherapy", False), ("conservative", False)]),
            ],
            "guidance": {
                "consider_before": [
                    "X-ray before referral",
                    "6-12 week trial of physiotherapy",
                    "Subacromial injection trial if impingement suspected",
                ],
                "refer_if": "Failed conservative management, suspected complete rotator cuff tear, "
                            "recurrent dislocation, or acute traumatic injury in young patient.",
                "source": "Common Canadian orthopedic guidelines — DRAFT",
            },
        },
        {
            "slug": "back_pain", "display_name": "Back Pain", "priority_order": 3,
            "keywords": [
                ("back pain", False), ("lumbar", False), ("sciatica", False),
                ("disc herniation", False), ("spinal stenosis", False),
            ],
            "workup": [
                ("X-ray (if >6 weeks or red flags)", [("x-ray", False), ("xray", False)]),
                ("Trial of conservative management (6-12 weeks)", [
                    ("physiotherapy", False), ("conservative", False),
                ]),
            ],
            "guidance": {
                "consider_before": [
                    "Rule out red flags (cauda equina, cancer, fracture, infection)",
                    "6-12 week trial of physiotherapy + activity",
                    "MRI only if surgical candidate with progressive neurological deficit",
                ],
                "refer_if": "Red flags (cauda equina symptoms, progressive weakness), "
                            "failed 12 weeks conservative management with radiculopathy, "
                            "or suspected spinal stenosis limiting function.",
                "source": "Common Canadian orthopedic guidelines — DRAFT",
            },
        },
    ],
    "priority_keywords": {
        "urgent": [
            "cauda equina", "spinal cord compression", "open fracture",
            "septic arthritis", "compartment syndrome", "dislocation",
        ],
        "high": [
            "progressive weakness", "foot drop", "locked knee",
            "acute ligament injury", "fracture", "avascular necrosis",
        ],
        "inappropriate": [
            "chronic pain management only", "medication refill",
        ],
    },
    "scoring": {
        "field_penalty": 20,
        "investigation_penalty": 15,
        "inappropriate_penalty": 25,
        "missing_field_appropriateness_penalty": 5,
        "urgent_keyword_weight": 20,
        "high_keyword_weight": 10,
        "workup_penalty": 10,
    },
}


def _seed_one_specialty(db, data):
    """Seed a single specialty and all its clinical rules. Idempotent."""
    specialty = Specialty.query.filter_by(slug=data["slug"]).first()
    if not specialty:
        specialty = Specialty(
            name=data["name"], slug=data["slug"], description=data["description"],
        )
        db.session.add(specialty)
        db.session.flush()
        print(f"  Created specialty: {data['name']}")
    else:
        print(f"  Specialty exists: {data['name']}")

    # Categories + keywords + workup + guidance
    for cat_data in data["categories"]:
        cat = ClinicalCategory.query.filter_by(
            specialty_id=specialty.id, slug=cat_data["slug"],
        ).first()
        if not cat:
            cat = ClinicalCategory(
                specialty_id=specialty.id,
                slug=cat_data["slug"],
                display_name=cat_data["display_name"],
                priority_order=cat_data["priority_order"],
            )
            db.session.add(cat)
            db.session.flush()

        # Keywords
        existing_kws = {kw.keyword for kw in cat.keywords}
        for keyword, use_wb in cat_data["keywords"]:
            if keyword not in existing_kws:
                db.session.add(CategoryKeyword(
                    category_id=cat.id, keyword=keyword, use_word_boundary=use_wb,
                ))

        # Workup items
        existing_items = {wi.label for wi in cat.workup_items}
        for label, detection_kws in cat_data.get("workup", []):
            if label not in existing_items:
                wi = WorkupItem(category_id=cat.id, label=label, sort_order=0)
                db.session.add(wi)
                db.session.flush()
                for kw, use_wb in detection_kws:
                    db.session.add(WorkupKeyword(
                        workup_item_id=wi.id, keyword=kw, use_word_boundary=use_wb,
                    ))

        # Guidance
        guidance_data = cat_data.get("guidance")
        if guidance_data and not cat.guidance:
            db.session.add(PathwayGuidance(
                category_id=cat.id,
                consider_before=guidance_data.get("consider_before", []),
                refer_if=guidance_data.get("refer_if", ""),
                source=guidance_data.get("source"),
            ))

    # Priority keywords
    existing_pks = {pk.keyword for pk in specialty.priority_keywords}
    for level, keywords in data.get("priority_keywords", {}).items():
        for kw in keywords:
            if kw not in existing_pks:
                db.session.add(PriorityKeyword(
                    specialty_id=specialty.id, keyword=kw, priority_level=level,
                ))

    # Scoring config
    existing_configs = {tc.config_key for tc in specialty.triage_configs}
    for key, value in data.get("scoring", {}).items():
        if key not in existing_configs:
            db.session.add(TriageConfig(
                specialty_id=specialty.id, config_key=key, config_value=value,
            ))

    db.session.commit()


def seed_all_specialties(db):
    """Seed all built-in specialties."""
    print("Seeding specialties...")
    for spec_data in [_UROLOGY, _GI, _ORTHO]:
        _seed_one_specialty(db, spec_data)
    print("Done.")
