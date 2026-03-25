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
    """Create a demo specialist account for local development."""
    from werkzeug.security import generate_password_hash

    existing = User.query.filter_by(email="demo@example.com").first()
    if existing:
        print("Demo user already exists.")
        return

    user = User(
        email="demo@example.com",
        full_name="Dr. Alex Nguyen",
        specialty="Urology",
        clinic_name="Lions Gate Hospital – Urology, North Vancouver",
        role="specialist",
    )
    user.set_password("password123")
    db.session.add(user)
    db.session.commit()
    print(f"Demo user created: {user.email} / password123")


if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(debug=debug)
