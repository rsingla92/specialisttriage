"""Application entry point."""
import os
from app import create_app, db
from app.models import (
    User, Referral, TriageResult, Feedback, ResponseTemplate, BatchAction,
    Specialty, ClinicalCategory, Clinic, ClinicMembership,
)

app = create_app(os.environ.get("FLASK_ENV", "default"))


@app.shell_context_processor
def make_shell_context():
    return {"db": db, "User": User, "Referral": Referral,
            "TriageResult": TriageResult, "Feedback": Feedback,
            "ResponseTemplate": ResponseTemplate, "BatchAction": BatchAction,
            "Specialty": Specialty, "ClinicalCategory": ClinicalCategory}


@app.cli.command("seed-demo")
def seed_demo():
    """Create demo specialist accounts for local development only."""
    import secrets as _secrets

    flask_env = os.environ.get("FLASK_ENV", "default")
    if flask_env == "production":
        print("ERROR: seed-demo must not be run in a production environment.")
        return

    # Create or find the demo clinic
    urology = Specialty.query.filter_by(slug="urology").first()
    clinic = Clinic.query.filter_by(slug="lions-gate-urology").first()
    if not clinic:
        clinic = Clinic(
            name="Lions Gate Hospital – Urology",
            slug="lions-gate-urology",
            specialty_id=urology.id if urology else None,
            address="231 15th St E, North Vancouver, BC",
        )
        db.session.add(clinic)
        db.session.flush()
        print(f"Demo clinic created: {clinic.name}")

    doctors = [
        ("demo@example.com", "Dr. Alex Nguyen", "owner"),
        ("sarah@example.com", "Dr. Sarah Chen", "admin"),
        ("michael@example.com", "Dr. Michael Park", "specialist"),
    ]

    for email, full_name, role in doctors:
        existing = User.query.filter_by(email=email).first()
        if existing:
            print(f"User {email} already exists. Skipping.")
            continue

        password = _secrets.token_urlsafe(12)

        user = User(
            email=email,
            full_name=full_name,
            specialty="Urology",
            clinic_name=clinic.name,
            role="specialist",
        )
        user.set_password(password)
        db.session.add(user)
        db.session.flush()

        membership = ClinicMembership(
            user_id=user.id, clinic_id=clinic.id, role=role,
        )
        db.session.add(membership)
        db.session.commit()
        print(f"Demo user created: {user.email}")
        print(f"  Clinic: {clinic.name} (role: {role})")
        print(f"  Temporary password: {password}")
        print("  (This password is shown only once – save it now.)")


@app.cli.command("seed-templates")
def seed_templates():
    """Create default response templates for each clinical category."""
    defaults = [
        ("hematuria", "needs_info",
         "Thank you for the referral for [Patient]. Before we can schedule assessment, "
         "we require: (1) urine cytology results, (2) CT urogram or renal ultrasound imaging. "
         "-- Dr. [Name], Urology"),
        ("psa_prostate", "needs_info",
         "Thank you for the referral for [Patient]. To proceed with assessment, could you "
         "please provide: (1) DRE findings, (2) prior PSA values if available, (3) family "
         "history of prostate cancer. -- Dr. [Name], Urology"),
        ("stones", "needs_info",
         "Thank you for the referral for [Patient]. We require: (1) CT KUB imaging, "
         "(2) serum creatinine results, (3) urinalysis. -- Dr. [Name], Urology"),
        ("incontinence", "needs_info",
         "Thank you for the referral for [Patient]. Please provide: (1) voiding diary, "
         "(2) urinalysis, (3) post-void residual measurement. -- Dr. [Name], Urology"),
        ("uti_recurrent", "needs_info",
         "Thank you for the referral for [Patient]. We require: (1) urine C&S results, "
         "(2) imaging (US KUB), (3) antibiotic treatment history. -- Dr. [Name], Urology"),
        ("erectile_dysfunction", "decline",
         "Thank you for the referral for [Patient]. Erectile dysfunction is typically "
         "managed in primary care. Please see the attached pathway for recommended workup "
         "and management. Refer back if secondary cause suspected or refractory to treatment. "
         "-- Dr. [Name], Urology"),
    ]

    created = 0
    for category, ttype, body in defaults:
        existing = ResponseTemplate.query.filter_by(
            category=category, template_type=ttype, created_by=None
        ).first()
        if not existing:
            tpl = ResponseTemplate(category=category, template_type=ttype,
                                   body_text=body, created_by=None)
            db.session.add(tpl)
            created += 1

    db.session.commit()
    print(f"Created {created} default template(s) ({len(defaults) - created} already existed).")


@app.cli.command("seed-specialty")
def seed_specialty_cmd():
    """Seed all specialties with their clinical rules from built-in data."""
    from app.services.specialty_seeder import seed_all_specialties
    seed_all_specialties(db)


@app.cli.command("seed-referrals")
def seed_referrals():
    """Create ~80 demo referrals with triage results and feedback for QA testing."""
    import random
    from datetime import date, datetime, timedelta, timezone

    random.seed(42)

    flask_env = os.environ.get("FLASK_ENV", "default")
    if flask_env == "production":
        print("ERROR: seed-referrals must not be run in a production environment.")
        return

    # --- Guard: demo user and clinic must exist ---
    demo_user = User.query.filter_by(email="demo@example.com").first()
    if not demo_user:
        print("ERROR: Demo user not found. Run 'flask seed-demo' first.")
        return

    clinic = Clinic.query.filter_by(slug="lions-gate-urology").first()
    if not clinic:
        print("ERROR: Demo clinic not found. Run 'flask seed-demo' first.")
        return

    urology = Specialty.query.filter_by(slug="urology").first()
    if not urology:
        print("ERROR: Urology specialty not found. Run 'flask seed-specialty' first.")
        return

    existing_count = Referral.query.filter_by(clinic_id=clinic.id).count()
    if existing_count >= 80:
        print(f"Referrals already seeded ({existing_count} found). Delete specialisttriage.db and re-run to refresh.")
        return

    # Look up the 3 doctors for assignment
    doc_nguyen = User.query.filter_by(email="demo@example.com").first()
    doc_chen = User.query.filter_by(email="sarah@example.com").first()
    doc_park = User.query.filter_by(email="michael@example.com").first()
    doctors_pool = [doc_nguyen, doc_chen, doc_park, None]  # None = unassigned

    # --- Name / clinic pools ---
    first_names = [
        "James", "Robert", "Michael", "William", "David", "Richard", "Thomas",
        "Charles", "Daniel", "Matthew", "Andrew", "Joshua", "Kevin", "Brian",
        "Patricia", "Jennifer", "Linda", "Barbara", "Susan", "Margaret", "Sarah",
        "Karen", "Lisa", "Nancy", "Betty", "Helen", "Sandra", "Donna", "Emily",
        "Mei", "Wei", "Priya", "Amit", "Raj", "Harjit", "Gurpreet", "Yuki",
        "Satoshi", "Fatima", "Omar", "Ali", "Hassan", "Elena", "Ivan", "Olga",
    ]
    last_names = [
        "MacDonald", "Nguyen", "Kowalski", "Williams", "Zhang", "Bradley",
        "Foster", "White", "Chen", "Singh", "Patel", "Kim", "Lee", "Anderson",
        "Thompson", "Garcia", "Martinez", "Robinson", "Clark", "Lewis",
        "Walker", "Hall", "Young", "Allen", "Hernandez", "King", "Wright",
        "Lopez", "Hill", "Scott", "Green", "Adams", "Baker", "Gonzalez",
        "Nelson", "Carter", "Mitchell", "Perez", "Roberts", "Turner",
    ]
    referring_physicians = [
        "Dr. Sarah Lee", "Dr. Michael Chen", "Dr. Priya Sharma",
        "Dr. Amanda Foster", "Dr. John Patel", "Dr. Susan Kim",
        "Dr. Emily Chen", "Dr. Mark Lee", "Dr. Rachel Wong",
        "Dr. David Brown", "Dr. Lisa Huang", "Dr. Kevin O'Brien",
        "Dr. Maria Santos", "Dr. James Taylor", "Dr. Anita Gill",
    ]
    referring_clinics = [
        "North Shore Medical Clinic", "Lonsdale Medical Group",
        "Deep Cove Family Practice", "Lynn Valley Medical",
        "Capilano Medical Centre", "North Van Walk-In",
        "Park Royal Medical", "Edgemont Village Clinic",
        "Pemberton Medical Group", "Seymour Health Centre",
        "Marine Drive Medical", "West Van Family Practice",
    ]

    # --- Category definitions with complaints and notes ---
    categories = {
        "hematuria": {
            "count": 15,
            "complaints": [
                "Gross hematuria x 3 weeks, no infection on culture",
                "Painless gross hematuria, 2 episodes this month",
                "Microscopic hematuria found on routine urinalysis",
                "Visible blood in urine for 1 week, no dysuria",
                "Recurrent gross hematuria, ex-smoker",
                "Persistent microscopic hematuria on repeat UA",
                "Frank hematuria with small clots, no trauma",
                "Microscopic hematuria 3+ on dipstick, asymptomatic",
            ],
            "notes": [
                "CT urogram ordered, no stone or mass. Urinalysis: 3+ blood, no nitrites. Creatinine normal.",
                "Painless gross hematuria in 65M ex-smoker. CT urogram pending. Urine cytology sent.",
                "Incidental finding on pre-op urinalysis. No symptoms. Repeat UA confirms persistent microhematuria.",
                "Two episodes of visible hematuria. No anticoagulant use. US kidneys: normal. Urine culture negative.",
                "Ex-smoker 30 pack-years. Gross hematuria x2 weeks. CT urogram shows bladder wall thickening.",
                "Persistent microhematuria on 3 consecutive UAs. No UTI symptoms. BP normal. Creatinine 76.",
                "Frank hematuria with passage of small clots. On ASA 81mg. CT urogram unremarkable.",
                "Asymptomatic microhematuria on annual check. No family history of renal disease.",
            ],
            "history": [
                "Hypertension, ex-smoker 20 pack-year", "Ex-smoker, BPH",
                "No significant PMHx", "Diabetes type 2, on warfarin",
                "HTN, hyperlipidemia, 30 pack-year smoking history",
                "Healthy, no medications", "Atrial fibrillation on apixaban",
                "Kidney stones 10 years ago",
            ],
            "investigations": [
                "CT urogram: no mass/stone. UA: 3+ blood. Cr 88.",
                "Urine cytology: atypical cells. CT urogram pending.",
                "UA: microscopic hematuria. Cr 76. Renal US: normal.",
                "Urine culture: negative. CT urogram: unremarkable.",
                "CT urogram: bladder wall thickening. Urine cytology sent.",
                "UA x3: persistent micro hematuria. Cr normal.",
                "CT urogram: normal. Urine cytology: negative.",
                "",
            ],
        },
        "psa_prostate": {
            "count": 15,
            "complaints": [
                "Rising PSA – 6.8 ng/mL up from 4.1 last year",
                "PSA elevated at 8.2, patient anxious about prostate cancer",
                "PSA 5.5, family history of prostate cancer",
                "Elevated PSA 12.1 ng/mL, abnormal DRE",
                "PSA rising trend: 3.2 → 4.8 → 6.1 over 3 years",
                "PSA 4.5 with LUTS, nocturia x3",
                "New PSA 7.9, no prior screening",
                "PSA 9.3, brother diagnosed with prostate cancer at 55",
            ],
            "notes": [
                "72M with rising PSA over 2 years. DRE: mildly enlarged, no nodule. Patient concerned about prostate cancer.",
                "PSA 8.2, repeat confirms. DRE: smooth, moderately enlarged. IPSS 14. No hematuria.",
                "55M, father had prostate cancer at 60. PSA 5.5, DRE normal. Requesting specialist assessment.",
                "PSA 12.1, DRE reveals firm nodule right lobe. Urgent assessment requested.",
                "Progressive PSA rise over 3 years. DRE: benign enlargement. LUTS worsening.",
                "PSA 4.5 with significant LUTS. Nocturia x3, weak stream. Tried tamsulosin with partial relief.",
                "First PSA screen at age 68: 7.9. No urinary symptoms. DRE: mildly enlarged, no nodule.",
                "PSA 9.3. Strong family history. DRE: normal. Patient requests biopsy discussion.",
            ],
            "history": [
                "Type 2 diabetes, osteoarthritis", "BPH, hypertension",
                "Father – prostate cancer", "HTN, hyperlipidemia",
                "No significant PMHx", "BPH on tamsulosin, GERD",
                "Healthy, no medications", "Brother – prostate CA age 55",
            ],
            "investigations": [
                "PSA 6.8 (prev 4.1). DRE: no nodule. UA: clear.",
                "PSA 8.2 (repeat 8.0). DRE: smooth, 40g. IPSS 14.",
                "PSA 5.5. DRE: normal. Free PSA ratio 12%.",
                "PSA 12.1. DRE: firm R nodule. Cr normal.",
                "PSA trend: 3.2/4.8/6.1. DRE: benign. UA normal.",
                "PSA 4.5. Post-void residual 120mL. Uroflow: Qmax 10mL/s.",
                "PSA 7.9. DRE: mildly enlarged. Cr 95. UA normal.",
                "PSA 9.3. Free/total ratio 10%. DRE normal.",
            ],
        },
        "stones": {
            "count": 12,
            "complaints": [
                "Left flank pain, CT shows 8mm ureteral stone",
                "Recurrent kidney stones, 3rd episode this year",
                "Right renal colic, 5mm stone on CT KUB",
                "Bilateral renal calculi on ultrasound",
                "Passed stone last month, CT shows residual 6mm stone",
                "Acute left flank pain radiating to groin",
            ],
            "notes": [
                "52M with acute left flank pain. CT KUB: 8mm stone at left UVJ. Creatinine 92. UA shows blood.",
                "Third stone episode in 12 months. CT shows 4mm R mid-ureter. Metabolic workup pending.",
                "Acute right renal colic. CT KUB: 5mm R proximal ureter stone. No hydronephrosis. Cr 88.",
                "US kidneys: bilateral non-obstructing calculi, largest 9mm R lower pole. Asymptomatic.",
                "Passed stone spontaneously. CT KUB: residual 6mm L lower pole stone. 24hr urine pending.",
                "Acute onset L flank pain. CT KUB: 7mm L UVJ stone with mild hydronephrosis.",
            ],
            "history": [
                "Previous kidney stone 5 years ago", "Recurrent nephrolithiasis, gout",
                "No significant PMHx", "Hyperparathyroidism",
                "Crohn's disease", "Recurrent UTIs with stones",
            ],
            "investigations": [
                "CT KUB: 8mm L UVJ stone. Cr 92. UA: 3+ blood.",
                "CT KUB: 4mm R mid-ureter. Cr 85. Metabolic panel pending.",
                "CT KUB: 5mm R proximal ureter. No hydro. Cr 88.",
                "US: bilateral calculi, largest 9mm. Cr 78. Ca 2.6.",
                "CT KUB: 6mm L lower pole. 24hr urine: high oxalate.",
                "CT KUB: 7mm L UVJ, mild L hydro. Cr 102.",
            ],
        },
        "uti_recurrent": {
            "count": 10,
            "complaints": [
                "Recurrent UTIs – 4 episodes in 12 months",
                "Recurrent E. coli UTIs, 5 episodes past year",
                "Persistent UTI despite 2 courses of antibiotics",
                "Recurrent UTIs post-menopause, on vaginal estrogen",
                "Male with recurrent UTIs and BPH",
            ],
            "notes": [
                "Male patient with 4 UTIs this year, each culture-positive E. coli. Last episode required IV antibiotics.",
                "Post-menopausal female with 5 UTIs in 12 months. All E. coli. On vaginal estrogen. US KUB pending.",
                "UTI persisting after ciprofloxacin and TMP-SMX. Culture shows resistant E. coli. No structural cause on US.",
                "62F with recurrent UTIs since menopause. Vaginal estrogen started 3 months ago. Still having episodes.",
                "68M with BPH and recurrent UTIs. Post-void residual 180mL. On tamsulosin.",
            ],
            "history": [
                "BPH on tamsulosin", "Post-menopausal, osteoporosis",
                "Diabetes type 2", "Recurrent UTIs since menopause",
                "BPH, diabetes, HTN",
            ],
            "investigations": [
                "Urine cultures: E. coli x4. PSA 3.2. Cr normal.",
                "Urine C&S x5: E. coli. US KUB: normal. Cr 72.",
                "C&S: resistant E. coli. US KUB: no obstruction. Cr 80.",
                "Urine C&S: E. coli. UA: pyuria. Post-void residual 50mL.",
                "C&S: E. coli x3. PVR 180mL. US: enlarged prostate.",
            ],
        },
        "incontinence": {
            "count": 10,
            "complaints": [
                "Stress urinary incontinence affecting quality of life",
                "Mixed incontinence – stress and urge components",
                "Urge incontinence refractory to oxybutynin",
                "Post-prostatectomy incontinence, 6 months out",
                "Stress incontinence, failed pelvic floor physio",
            ],
            "notes": [
                "38F, 2 vaginal deliveries. Leaks with cough/sneeze/exercise. Completed pelvic floor physio with minimal improvement.",
                "55F with mixed incontinence. Leaks with activity and urge. Tried oxybutynin – discontinued due to dry mouth.",
                "67F with urge incontinence. Failed oxybutynin and mirabegron. Frequency 12x/day. Nocturia x4.",
                "72M, 6 months post-RARP for prostate cancer. Using 3-4 pads/day. Doing pelvic floor exercises.",
                "45F with SUI since 2nd delivery. 3 months pelvic floor physio – no improvement. Uses 2 pads/day.",
            ],
            "history": [
                "G2P2, otherwise healthy", "Menopause, HTN",
                "OAB, osteoarthritis", "Prostate cancer – s/p RARP",
                "G3P3, BMI 31",
            ],
            "investigations": [
                "UA: normal. Voiding diary: 8x/day. PVR 30mL.",
                "UA: normal. Voiding diary: 10x/day, 2 urge leaks/day.",
                "UA: normal. Voiding diary: 12x/day, nocturia x4. PVR 20mL.",
                "UA: normal. Pad weight test: 150g/day. PVR 10mL.",
                "UA: normal. Voiding diary completed. PVR 25mL.",
            ],
        },
        "erectile_dysfunction": {
            "count": 9,
            "complaints": [
                "Erectile dysfunction for 2 years",
                "ED refractory to PDE5 inhibitors",
                "New onset ED, age 42, concerned about vascular cause",
                "ED with low libido, testosterone borderline",
                "ED post-TURP, was fine pre-operatively",
            ],
            "notes": [
                "61M with ED for 2 years. Tried sildenafil 50mg with partial response. HTN and diabetes well controlled.",
                "58M, ED x3 years. Failed sildenafil 100mg and tadalafil 20mg. Requesting further options.",
                "42M with new onset ED x6 months. No cardiac history. Morning erections diminished. Concerned about vascular cause.",
                "55M with ED and low libido. Testosterone 8.5 nmol/L (low-normal). BMI 34.",
                "66M, ED since TURP 8 months ago. Was potent pre-op. Sildenafil 50mg ineffective.",
            ],
            "history": [
                "Type 2 DM, HTN, hyperlipidemia", "HTN, depression on SSRI",
                "No significant PMHx", "Obesity, prediabetes",
                "BPH s/p TURP",
            ],
            "investigations": [
                "HbA1c 7.1. Testosterone 12 nmol/L. Lipids: controlled.",
                "Testosterone 14 nmol/L. HbA1c 6.8. TSH normal.",
                "Testosterone 16 nmol/L. Fasting glucose 5.2. Lipids normal.",
                "Testosterone 8.5 nmol/L. Prolactin normal. HbA1c 6.1.",
                "Testosterone 11 nmol/L. PSA 1.8 (post-TURP).",
            ],
        },
        "other": {
            "count": 9,
            "complaints": [
                "Scrotal swelling – possible varicocele",
                "Undescended right testicle in 14-month-old",
                "Testicular mass found on self-exam",
                "Chronic pelvic pain syndrome, urology workup requested",
                "Phimosis in adult male, requesting circumcision consult",
                "Hydrocele, gradually enlarging over 6 months",
                "Lower back pain and fatigue, requesting urology assessment",
                "Penile curvature causing difficulty with intercourse",
                "Chronic scrotal pain, no identifiable cause on US",
            ],
            "notes": [
                "28M with left scrotal swelling. US: grade 2 varicocele. Mild discomfort. Fertility not yet a concern.",
                "14-month-old with right undescended testicle. Not palpable in inguinal canal. US: right testis in inguinal canal.",
                "35M found firm painless lump on R testicle. US: 1.5cm solid hypoechoic mass. Tumour markers pending. URGENT.",
                "42M with chronic pelvic pain x18 months. Urine cultures negative. DRE: normal prostate. Tried NSAIDs, no relief.",
                "32M with tight phimosis causing paraphimosis episodes. Topical steroid x6 weeks – no improvement.",
                "58M with gradually enlarging right hydrocele. US confirms simple hydrocele. No testicular mass.",
                "44F with chronic lower back pain and fatigue. No urinary symptoms. Referral at patient's request.",
                "48M with penile curvature 40 degrees. Peyronie's disease suspected. Painful erections. Duration 8 months.",
                "38M with chronic scrotal pain x2 years. US: normal testes. No varicocele. No hernia on exam.",
            ],
            "history": [
                "No significant PMHx", "Full-term, normal delivery",
                "No significant PMHx", "Depression, anxiety",
                "No significant PMHx", "HTN, ex-smoker",
                "Fibromyalgia, depression", "HTN, diabetes",
                "Anxiety, chronic pain syndrome",
            ],
            "investigations": [
                "US scrotum: grade 2 L varicocele. Semen analysis: normal.",
                "US: R testis in inguinal canal, normal morphology.",
                "US: 1.5cm solid R testicular mass. AFP/bHCG/LDH pending.",
                "UA: normal. C&S: negative. PSA 1.2. DRE: normal.",
                "No investigations.",
                "US scrotum: simple R hydrocele 6cm. Testes normal.",
                "No urological investigations done.",
                "No imaging. Clinical diagnosis Peyronie's.",
                "US scrotum: normal. Urine: normal. MSSU: negative.",
            ],
        },
    }

    medications_pool = [
        "None", "Ramipril 5mg daily", "Metformin 500mg BID",
        "Tamsulosin 0.4mg daily", "ASA 81mg daily",
        "Amlodipine 5mg daily", "Atorvastatin 20mg daily",
        "Lisinopril 10mg daily", "Oxybutynin 5mg BID",
        "Sildenafil 50mg PRN", "Naproxen PRN",
        "Duloxetine 60mg daily", "Acetaminophen PRN",
    ]
    allergies_pool = [
        "NKDA", "NKDA", "NKDA", "NKDA",  # weighted toward NKDA
        "Penicillin", "Sulfa drugs", "Codeine", "ASA", "Iodine contrast",
    ]

    # --- Priority distribution (weights for random.choices) ---
    priority_labels = ["urgent", "high", "routine", "low", "needs_info", "inappropriate"]
    priority_weights = [8, 20, 45, 15, 8, 4]

    # --- Feedback decision distribution ---
    feedback_decisions = ["accepted", "declined", "needs_info", "redirected"]
    feedback_weights = [50, 15, 25, 10]
    feedback_messages = {
        "accepted": [
            "Referral accepted. Patient will be booked for clinic assessment.",
            "Accepted – patient added to surgical waitlist for assessment.",
            "Referral appropriate. Booking within 4-6 weeks.",
        ],
        "declined": [
            "This referral does not meet criteria for specialist assessment. Please see attached pathway guidance.",
            "Declined – condition is best managed in primary care. Pathway attached.",
        ],
        "needs_info": [
            "Thank you for the referral. Please provide the missing investigations before we can proceed.",
            "Additional workup required before assessment. Please see list of required items.",
            "Referral incomplete. Please provide imaging and lab results as outlined.",
        ],
        "redirected": [
            "This referral would be better directed to Nephrology. Redirecting.",
            "Recommend referral to Physiotherapy / Pelvic Floor clinic instead.",
        ],
    }

    now = datetime.now(timezone.utc)
    referral_count = 0
    triage_count = 0
    feedback_count = 0
    referrals_to_add = []
    triage_results_to_add = []
    feedback_to_add = []

    for cat_slug, cat_data in categories.items():
        for i in range(cat_data["count"]):
            # Patient demographics
            fname = random.choice(first_names)
            lname = random.choice(last_names)
            age = random.randint(25, 85)
            dob = date.today() - timedelta(days=int(age * 365.25))
            phn = f"98{random.randint(10000000, 99999999)}"

            # Referring info
            ref_doc = random.choice(referring_physicians)
            ref_clinic = random.choice(referring_clinics)

            # Clinical content
            complaint = cat_data["complaints"][i % len(cat_data["complaints"])]
            notes = cat_data["notes"][i % len(cat_data["notes"])]
            history = cat_data["history"][i % len(cat_data["history"])]
            investigations = cat_data["investigations"][i % len(cat_data["investigations"])]
            meds = random.choice(medications_pool)
            allergy = random.choice(allergies_pool)

            # Timestamp spread over last 90 days
            days_ago = random.randint(0, 90)
            hours_offset = random.randint(0, 23)
            received = now - timedelta(days=days_ago, hours=hours_offset)

            # Priority
            priority = random.choices(priority_labels, weights=priority_weights, k=1)[0]

            ocean_id = f"OCN-SEED-{cat_slug[:4].upper()}-{i+1:03d}"

            # Assign to a doctor (or leave unassigned)
            assigned_doc = random.choices(doctors_pool, weights=[30, 20, 10, 40])[0]

            ref = Referral(
                ocean_referral_id=ocean_id,
                patient_first_name=fname,
                patient_last_name=lname,
                patient_dob=dob,
                patient_phn=phn,
                patient_sex=random.choices(['M', 'F', 'Other'], weights=[70, 25, 5])[0],
                referring_physician_name=ref_doc,
                referring_clinic=ref_clinic,
                referring_physician_phone=f"604-555-{random.randint(1000, 9999)}",
                referring_physician_fax=f"604-555-{random.randint(1000, 9999)}",
                referring_physician_specialty=random.choices(['Family Medicine', 'Internal Medicine', 'Emergency Medicine'], weights=[75, 15, 10])[0],
                chief_complaint=complaint,
                clinical_notes=notes,
                relevant_history=history,
                current_medications=meds,
                allergies=allergy,
                relevant_investigations=investigations,
                clinic_id=clinic.id,
                specialist_id=None,
                specialty_requested="Urology",
                specialty_id=urology.id,
                status="triaged",
                priority=priority,
                clinical_category=cat_slug,
                received_at=received,
                triaged_at=received + timedelta(seconds=random.randint(5, 30)),
            )

            if assigned_doc:
                ref.specialist_id = assigned_doc.id
                ref.assigned_at = ref.received_at + timedelta(hours=random.randint(1, 48))

            # Add mock attachments to ~40% of referrals
            if random.random() < 0.4:
                cat_files = {
                    'hematuria': ['CT_urogram.pdf', 'urinalysis_report.pdf', 'cystoscopy_findings.pdf'],
                    'psa_prostate': ['PSA_lab_results.pdf', 'DRE_notes.pdf'],
                    'stones': ['CT_abdomen.pdf', 'KUB_xray.pdf'],
                }
                pool = cat_files.get(cat_slug, ['lab_results.pdf', 'imaging_report.pdf', 'referral_letter.pdf'])
                n = random.randint(1, min(3, len(pool)))
                ref.attachments = [{"filename": f, "type": "application/pdf", "url": "#"} for f in random.sample(pool, n)]

            referrals_to_add.append(ref)
            referral_count += 1

    # Commit referrals first so they get IDs
    db.session.add_all(referrals_to_add)
    db.session.flush()

    # --- Triage results ---
    for ref in referrals_to_add:
        approp = random.randint(30, 95)
        complete = random.randint(20, 100)
        urgency = random.randint(10, 90)

        missing = []
        if complete < 60:
            possible_missing = [
                "Urine cytology", "CT urogram", "Renal ultrasound",
                "PSA history", "DRE findings", "Urine culture and sensitivity",
                "Voiding diary", "Post-void residual", "Serum creatinine",
                "Metabolic panel", "24-hour urine collection",
            ]
            missing = random.sample(possible_missing, k=random.randint(1, 3))

        triage_notes = ""
        if ref.priority == "urgent":
            triage_notes = "Flagged as urgent based on clinical presentation."
        elif ref.priority == "inappropriate":
            triage_notes = "Referral may not meet specialty criteria. Review recommended."
        elif missing:
            triage_notes = "Incomplete workup. Missing items identified."

        tr = TriageResult(
            referral_id=ref.id,
            appropriateness_score=approp,
            completeness_score=complete,
            urgency_score=urgency,
            recommended_priority=ref.priority,
            missing_information=missing,
            triage_notes=triage_notes,
            model_version="rules-v1.0",
            specialty_id=urology.id,
            triaged_at=ref.triaged_at,
        )
        triage_results_to_add.append(tr)
        triage_count += 1

    db.session.add_all(triage_results_to_add)
    db.session.flush()

    # --- Feedback for ~40% of referrals ---
    feedback_refs = random.sample(referrals_to_add, k=int(len(referrals_to_add) * 0.4))
    for ref in feedback_refs:
        decision = random.choices(feedback_decisions, weights=feedback_weights, k=1)[0]
        message = random.choice(feedback_messages[decision])

        redirect_to = None
        if decision == "redirected":
            redirect_to = random.choice(["Nephrology", "Physiotherapy", "Pelvic Floor Clinic", "Gastroenterology"])

        resolved_time = ref.received_at + timedelta(
            days=random.randint(1, 14),
            hours=random.randint(0, 23),
        )

        fb = Feedback(
            referral_id=ref.id,
            specialist_id=demo_user.id,
            decision=decision,
            message=message,
            redirect_to=redirect_to,
            sent_at=resolved_time,
            delivery_status="sent",
        )
        feedback_to_add.append(fb)

        # Update referral status to match feedback decision
        ref.status = decision
        ref.resolved_at = resolved_time
        ref.specialist_id = demo_user.id
        ref.assigned_at = ref.received_at + timedelta(hours=random.randint(1, 48))
        feedback_count += 1

    db.session.add_all(feedback_to_add)
    db.session.commit()

    print(f"Seeded {referral_count} referrals with {triage_count} triage results and {feedback_count} feedback records.")
    print("Category breakdown:")
    for cat_slug, cat_data in categories.items():
        print(f"  {cat_slug}: {cat_data['count']}")
    print(f"Feedback coverage: {feedback_count}/{referral_count} ({100*feedback_count//referral_count}%)")


if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(debug=debug)
