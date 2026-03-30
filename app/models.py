"""Database models for the specialist triage application."""
from datetime import datetime, timezone
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db


# ---------------------------------------------------------------------------
# Multi-specialty configuration models
# ---------------------------------------------------------------------------

class Specialty(db.Model):
    """A medical specialty (e.g. Urology, Gastroenterology)."""

    __tablename__ = "specialties"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    slug = db.Column(db.String(50), nullable=False, unique=True)
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    categories = db.relationship("ClinicalCategory", backref="specialty", lazy="dynamic")
    priority_keywords = db.relationship("PriorityKeyword", backref="specialty", lazy="dynamic")
    triage_configs = db.relationship("TriageConfig", backref="specialty", lazy="dynamic")

    def __repr__(self):
        return f"<Specialty {self.slug}>"


class ClinicalCategory(db.Model):
    """A clinical category within a specialty (e.g. Hematuria under Urology)."""

    __tablename__ = "clinical_categories"
    __table_args__ = (
        db.UniqueConstraint("specialty_id", "slug", name="uq_category_specialty_slug"),
    )

    id = db.Column(db.Integer, primary_key=True)
    specialty_id = db.Column(db.Integer, db.ForeignKey("specialties.id"), nullable=False, index=True)
    slug = db.Column(db.String(50), nullable=False)
    display_name = db.Column(db.String(100), nullable=False)
    priority_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)

    keywords = db.relationship("CategoryKeyword", backref="category", cascade="all, delete-orphan")
    workup_items = db.relationship("WorkupItem", backref="category", cascade="all, delete-orphan",
                                   order_by="WorkupItem.sort_order")
    guidance = db.relationship("PathwayGuidance", backref="category", uselist=False,
                               cascade="all, delete-orphan")

    def __repr__(self):
        return f"<ClinicalCategory {self.slug}>"


class CategoryKeyword(db.Model):
    """A keyword used to classify referrals into a clinical category."""

    __tablename__ = "category_keywords"

    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey("clinical_categories.id"), nullable=False, index=True)
    keyword = db.Column(db.String(100), nullable=False)
    use_word_boundary = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f"<CategoryKeyword '{self.keyword}'>"


class WorkupItem(db.Model):
    """A required workup item for a clinical category."""

    __tablename__ = "workup_items"

    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey("clinical_categories.id"), nullable=False, index=True)
    label = db.Column(db.String(200), nullable=False)
    sort_order = db.Column(db.Integer, default=0)
    is_required = db.Column(db.Boolean, default=True)

    detection_keywords = db.relationship("WorkupKeyword", backref="workup_item",
                                         cascade="all, delete-orphan")

    def __repr__(self):
        return f"<WorkupItem '{self.label}'>"


class WorkupKeyword(db.Model):
    """A keyword used to detect if a workup item is present in referral text."""

    __tablename__ = "workup_keywords"

    id = db.Column(db.Integer, primary_key=True)
    workup_item_id = db.Column(db.Integer, db.ForeignKey("workup_items.id"), nullable=False, index=True)
    keyword = db.Column(db.String(100), nullable=False)
    use_word_boundary = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f"<WorkupKeyword '{self.keyword}'>"


class PriorityKeyword(db.Model):
    """A keyword that triggers urgent/high/inappropriate priority for a specialty."""

    __tablename__ = "priority_keywords"

    id = db.Column(db.Integer, primary_key=True)
    specialty_id = db.Column(db.Integer, db.ForeignKey("specialties.id"), nullable=False, index=True)
    keyword = db.Column(db.String(100), nullable=False)
    priority_level = db.Column(db.String(20), nullable=False)  # urgent | high | inappropriate

    def __repr__(self):
        return f"<PriorityKeyword '{self.keyword}' ({self.priority_level})>"


class PathwayGuidance(db.Model):
    """Pre-referral pathway guidance content for a clinical category."""

    __tablename__ = "pathway_guidance"

    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey("clinical_categories.id"), nullable=False, unique=True)
    consider_before = db.Column(db.JSON, default=list)
    refer_if = db.Column(db.Text)
    additional_notes = db.Column(db.Text)
    source = db.Column(db.String(200))  # e.g. "BC GPAC Guidelines (2024)"
    source_url = db.Column(db.String(500))

    def __repr__(self):
        return f"<PathwayGuidance category={self.category_id}>"


class TriageConfig(db.Model):
    """Per-specialty scoring configuration for the triage engine."""

    __tablename__ = "triage_configs"
    __table_args__ = (
        db.UniqueConstraint("specialty_id", "config_key", name="uq_triage_config_specialty_key"),
    )

    id = db.Column(db.Integer, primary_key=True)
    specialty_id = db.Column(db.Integer, db.ForeignKey("specialties.id"), nullable=False, index=True)
    config_key = db.Column(db.String(100), nullable=False)
    config_value = db.Column(db.Integer, nullable=False)

    def __repr__(self):
        return f"<TriageConfig {self.config_key}={self.config_value}>"


# ---------------------------------------------------------------------------
# Clinic / Organization models
# ---------------------------------------------------------------------------

class Clinic(db.Model):
    """A medical clinic or specialist practice (multi-tenant entity)."""

    __tablename__ = "clinics"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False)
    specialty_id = db.Column(db.Integer, db.ForeignKey("specialties.id"), nullable=True, index=True)
    address = db.Column(db.String(500))
    phone = db.Column(db.String(20))
    fax = db.Column(db.String(20))
    ocean_md_api_key = db.Column(db.String(500))
    settings = db.Column(db.JSON, default=lambda: {
        "queue_mode": "hybrid",
        "auto_triage": True,
    })
    subscription_tier = db.Column(db.String(20), default="free")
    subscription_status = db.Column(db.String(20), default="active")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    is_active = db.Column(db.Boolean, default=True)

    specialty = db.relationship("Specialty", foreign_keys=[specialty_id])
    memberships = db.relationship("ClinicMembership", backref="clinic", lazy="dynamic")
    referrals = db.relationship("Referral", backref="clinic", lazy="dynamic")

    @property
    def queue_mode(self):
        return (self.settings or {}).get("queue_mode", "hybrid")

    def __repr__(self):
        return f"<Clinic {self.slug}>"


class ClinicMembership(db.Model):
    """Links a user to a clinic with a role."""

    __tablename__ = "clinic_memberships"
    __table_args__ = (
        db.UniqueConstraint("user_id", "clinic_id", name="uq_user_clinic"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    clinic_id = db.Column(db.Integer, db.ForeignKey("clinics.id"), nullable=False, index=True)
    role = db.Column(db.String(20), nullable=False, default="specialist")  # owner | admin | specialist | viewer
    joined_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    is_active = db.Column(db.Boolean, default=True)
    invite_token = db.Column(db.String(100), unique=True, nullable=True)

    user = db.relationship("User", backref=db.backref("memberships", lazy="dynamic"))

    def __repr__(self):
        return f"<ClinicMembership user={self.user_id} clinic={self.clinic_id} role={self.role}>"


CLINIC_ROLES = frozenset({"owner", "admin", "specialist", "viewer"})
CLINIC_ADMIN_ROLES = frozenset({"owner", "admin"})


# ---------------------------------------------------------------------------
# Core application models
# ---------------------------------------------------------------------------

class User(UserMixin, db.Model):
    """Represents a portal user (specialist or admin)."""

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="specialist")  # specialist | admin
    specialty = db.Column(db.String(100))
    specialty_id = db.Column(db.Integer, db.ForeignKey("specialties.id"), nullable=True, index=True)
    clinic_name = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    is_active = db.Column(db.Boolean, default=True)

    referrals = db.relationship("Referral", backref="specialist", lazy="dynamic")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def active_clinic_ids(self):
        return [m.clinic_id for m in self.memberships.filter_by(is_active=True)]

    @property
    def active_clinics(self):
        return [m.clinic for m in self.memberships.filter_by(is_active=True)]

    @property
    def primary_clinic(self):
        m = self.memberships.filter_by(is_active=True).first()
        return m.clinic if m else None

    def clinic_role(self, clinic_id):
        m = self.memberships.filter_by(clinic_id=clinic_id, is_active=True).first()
        return m.role if m else None

    def is_clinic_admin(self, clinic_id):
        return self.clinic_role(clinic_id) in CLINIC_ADMIN_ROLES

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

    # Clinic and specialist assignment
    clinic_id = db.Column(db.Integer, db.ForeignKey("clinics.id"), nullable=True, index=True)
    specialist_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    assigned_at = db.Column(db.DateTime)  # when specialist claimed from pool
    specialty_requested = db.Column(db.String(100), nullable=False, default="Urology")
    specialty_id = db.Column(db.Integer, db.ForeignKey("specialties.id"), nullable=True, index=True)

    # Status and triage
    status = db.Column(
        db.String(30), nullable=False, default="pending"
    )  # pending | triaged | accepted | declined | needs_info | redirected
    priority = db.Column(
        db.String(20)
    )  # urgent | high | routine | low | needs_info | inappropriate

    # Clinical classification (Phase 1 pivot)
    clinical_category = db.Column(db.String(30), index=True)
    missing_workup = db.Column(db.JSON, default=list)

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
    specialty_id = db.Column(db.Integer, db.ForeignKey("specialties.id"), nullable=True)
    triage_config_version = db.Column(db.String(50))

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
    batch_action_id = db.Column(
        db.Integer, db.ForeignKey("batch_actions.id"), nullable=True
    )

    decision = db.Column(
        db.String(30), nullable=False
    )  # accepted | declined | needs_info | redirected
    message = db.Column(db.Text, nullable=False)
    recommended_workup = db.Column(db.Text)
    redirect_to = db.Column(db.String(200))  # e.g. "Physiotherapy", "Nephrology"

    sent_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    delivery_status = db.Column(db.String(20), default="pending")  # pending | sent | failed | saved

    specialist = db.relationship("User", foreign_keys=[specialist_id])

    def __repr__(self):
        return f"<Feedback referral={self.referral_id} decision={self.decision}>"


VALID_CATEGORIES = frozenset({
    "hematuria", "psa_prostate", "stones", "incontinence",
    "uti_recurrent", "erectile_dysfunction", "other",
})

VALID_TEMPLATE_TYPES = frozenset({"needs_info", "accepted", "declined"})


class ResponseTemplate(db.Model):
    """Reusable response templates for specialist feedback by clinical category."""

    __tablename__ = "response_templates"
    __table_args__ = (
        db.UniqueConstraint("category", "template_type", "created_by",
                            name="uq_template_category_type_user"),
    )

    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(30), nullable=False, index=True)
    template_type = db.Column(db.String(20), nullable=False)  # needs_info | accepted | declined
    body_text = db.Column(db.Text, nullable=False)
    specialty_id = db.Column(db.Integer, db.ForeignKey("specialties.id"), nullable=True, index=True)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    creator = db.relationship("User", foreign_keys=[created_by])

    def render(self, patient_name="", specialist_name=""):
        text = self.body_text
        text = text.replace("[Patient]", patient_name)
        text = text.replace("[Name]", specialist_name)
        return text

    def __repr__(self):
        return f"<ResponseTemplate {self.category}/{self.template_type}>"


class BatchAction(db.Model):
    """Audit trail for batch referral actions."""

    __tablename__ = "batch_actions"

    id = db.Column(db.Integer, primary_key=True)
    referral_ids = db.Column(db.JSON, nullable=False)
    action_type = db.Column(db.String(20), nullable=False)  # accepted | needs_info | declined
    template_id = db.Column(
        db.Integer, db.ForeignKey("response_templates.id"), nullable=True
    )
    executed_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    executed_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    template = db.relationship("ResponseTemplate", foreign_keys=[template_id])
    executor = db.relationship("User", foreign_keys=[executed_by])
    feedback_records = db.relationship("Feedback", backref="batch_action", lazy="dynamic")

    def __repr__(self):
        return f"<BatchAction {self.action_type} x{len(self.referral_ids or [])}>"
