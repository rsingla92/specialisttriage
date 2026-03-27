"""Application entry point."""
import os
from app import create_app, db
from app.models import User, Referral, TriageResult, Feedback

app = create_app(os.environ.get("FLASK_ENV", "default"))


@app.shell_context_processor
def make_shell_context():
    return {"db": db, "User": User, "Referral": Referral,
            "TriageResult": TriageResult, "Feedback": Feedback}


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


if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(debug=debug)
