"""Application entry point."""
import os
from app import create_app, db
from app.models import User, Referral, TriageResult, Feedback, ResponseTemplate, BatchAction

app = create_app(os.environ.get("FLASK_ENV", "default"))


@app.shell_context_processor
def make_shell_context():
    return {"db": db, "User": User, "Referral": Referral,
            "TriageResult": TriageResult, "Feedback": Feedback,
            "ResponseTemplate": ResponseTemplate, "BatchAction": BatchAction}


@app.cli.command("seed-demo")
def seed_demo():
    """Create a demo specialist account for local development only."""
    import secrets as _secrets

    flask_env = os.environ.get("FLASK_ENV", "default")
    if flask_env == "production":
        print("ERROR: seed-demo must not be run in a production environment.")
        return

    existing = User.query.filter_by(email="demo@example.com").first()
    if existing:
        print("Demo user already exists.")
        return

    # Generate a cryptographically random password (~16 printable chars from URL-safe alphabet).
    # This avoids shipping a publicly-known fixed credential even in development/staging.
    password = _secrets.token_urlsafe(12)

    user = User(
        email="demo@example.com",
        full_name="Dr. Alex Nguyen",
        specialty="Urology",
        clinic_name="Lions Gate Hospital – Urology, North Vancouver",
        role="specialist",
    )
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    print(f"Demo user created: {user.email}")
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
    print(f"Created {created} default template(s) ({6 - created} already existed).")


if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(debug=debug)
