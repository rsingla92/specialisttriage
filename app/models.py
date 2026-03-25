"""Database models for the specialist triage application."""
from datetime import datetime, timezone
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db


class User(UserMixin, db.Model):
    """Represents a portal user (specialist or admin)."""

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="specialist")  # specialist | admin
    specialty = db.Column(db.String(100))
    clinic_name = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    is_active = db.Column(db.Boolean, default=True)

    referrals = db.relationship("Referral", backref="specialist", lazy="dynamic")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<User {self.email}>"


class Referral(db.Model):
    """Represents a specialist referral from a family physician."""

    __tablename__ = "referrals"

    id = db.Column(db.Integer, primary_key=True)
    ocean_referral_id = db.Column(db.String(100), unique=True, index=True)

    # Patient information
    patient_first_name = db.Column(db.String(100), nullable=False)
    patient_last_name = db.Column(db.String(100), nullable=False)
    patient_dob = db.Column(db.Date, nullable=False)
    patient_phn = db.Column(db.String(20))  # BC Personal Health Number

    # Referring physician
    referring_physician_name = db.Column(db.String(100), nullable=False)
    referring_clinic = db.Column(db.String(200))
    referring_physician_phone = db.Column(db.String(20))
    referring_physician_fax = db.Column(db.String(20))

    # Referral content
    chief_complaint = db.Column(db.Text, nullable=False)
    clinical_notes = db.Column(db.Text)
    relevant_history = db.Column(db.Text)
    current_medications = db.Column(db.Text)
    allergies = db.Column(db.Text)
    relevant_investigations = db.Column(db.Text)

    # Specialist assignment
    specialist_id = db.Column(db.Integer, db.ForeignKey("users.id"), index=True)
    specialty_requested = db.Column(db.String(100), nullable=False, default="Urology")

    # Status and triage
    status = db.Column(
        db.String(30), nullable=False, default="pending"
    )  # pending | triaged | accepted | declined | needs_info
    priority = db.Column(
        db.String(20)
    )  # urgent | high | routine | low | inappropriate

    # Timestamps
    received_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    triaged_at = db.Column(db.DateTime)
    resolved_at = db.Column(db.DateTime)

    triage_result = db.relationship(
        "TriageResult", backref="referral", uselist=False, cascade="all, delete-orphan"
    )
    feedback = db.relationship(
        "Feedback", backref="referral", uselist=False, cascade="all, delete-orphan"
    )

    @property
    def patient_full_name(self):
        return f"{self.patient_first_name} {self.patient_last_name}"

    @property
    def patient_age(self):
        today = datetime.now(timezone.utc).date()
        dob = self.patient_dob
        return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

    def __repr__(self):
        return f"<Referral {self.id} – {self.patient_full_name}>"


class TriageResult(db.Model):
    """Stores the AI triage assessment for a referral."""

    __tablename__ = "triage_results"

    id = db.Column(db.Integer, primary_key=True)
    referral_id = db.Column(
        db.Integer, db.ForeignKey("referrals.id"), nullable=False, unique=True
    )

    # Scoring (0–100)
    appropriateness_score = db.Column(db.Integer, nullable=False)
    completeness_score = db.Column(db.Integer, nullable=False)
    urgency_score = db.Column(db.Integer, nullable=False)

    # Outcomes
    recommended_priority = db.Column(db.String(20), nullable=False)
    missing_information = db.Column(db.JSON, default=list)
    triage_notes = db.Column(db.Text)
    flags = db.Column(db.JSON, default=list)  # List of warning/info flags

    triaged_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    model_version = db.Column(db.String(50), default="rules-v1.0")

    def __repr__(self):
        return f"<TriageResult referral={self.referral_id} score={self.appropriateness_score}>"


class Feedback(db.Model):
    """Feedback sent from specialist back to referring physician."""

    __tablename__ = "feedback"

    id = db.Column(db.Integer, primary_key=True)
    referral_id = db.Column(
        db.Integer, db.ForeignKey("referrals.id"), nullable=False, unique=True
    )
    specialist_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    decision = db.Column(
        db.String(30), nullable=False
    )  # accepted | declined | needs_info | redirected
    message = db.Column(db.Text, nullable=False)
    recommended_workup = db.Column(db.Text)
    redirect_to = db.Column(db.String(200))  # e.g. "Physiotherapy", "Nephrology"

    sent_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    delivery_status = db.Column(db.String(20), default="pending")  # pending | sent | failed

    specialist = db.relationship("User", foreign_keys=[specialist_id])

    def __repr__(self):
        return f"<Feedback referral={self.referral_id} decision={self.decision}>"
