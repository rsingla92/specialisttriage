"""Authentication routes: login, logout, register, signup, onboarding, join."""
import re
import secrets
from urllib.parse import urlparse, urljoin
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from app import db
from app.models import User, Specialty, Clinic, ClinicMembership


def _validate_password(password: str) -> list[str]:
    """Return a list of unmet password requirements."""
    errors = []
    if len(password) < 8:
        errors.append("at least 8 characters")
    if not re.search(r'[A-Z]', password):
        errors.append("at least 1 uppercase letter")
    if not re.search(r'\d', password):
        errors.append("at least 1 number")
    if not re.search(r'[!@#$%^&*(),.?\":{}|<>]', password):
        errors.append("at least 1 special character")
    return errors


def _is_safe_redirect_url(target: str) -> bool:
    """Return True only when *target* is a relative path on the same host."""
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ("http", "https") and ref_url.netloc == test_url.netloc


auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))
    return render_template("landing.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password) and user.is_active:
            login_user(user, remember=request.form.get("remember_me") == "on")
            next_page = request.args.get("next")
            flash(f"Welcome back, {user.full_name}!", "success")
            if next_page and _is_safe_redirect_url(next_page):
                return redirect(next_page)
            return redirect(url_for("dashboard.index"))
        flash("Invalid email or password.", "danger")

    return render_template("auth/login.html")


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        full_name = request.form.get("full_name", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        specialty = request.form.get("specialty", "Urology")
        clinic_name = request.form.get("clinic_name", "").strip()

        if not email or not full_name or not password:
            flash("All fields are required.", "danger")
        elif password != confirm:
            flash("Passwords do not match.", "danger")
        elif (pw_errors := _validate_password(password)):
            flash("Password must contain: " + ", ".join(pw_errors) + ".", "danger")
        elif User.query.filter_by(email=email).first():
            flash("An account with that email already exists.", "danger")
        else:
            user = User(
                email=email,
                full_name=full_name,
                specialty=specialty,
                clinic_name=clinic_name,
                role="specialist",
            )
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            login_user(user)
            flash(f"Account created. Welcome, {user.full_name}!", "success")
            return redirect(url_for("dashboard.index"))

    specialties = [
        "Urology", "Cardiology", "Dermatology", "Gastroenterology",
        "Neurology", "Ophthalmology", "Orthopedics", "Rheumatology",
        "Other",
    ]
    return render_template("auth/register.html", specialties=specialties)


def _make_slug(name: str) -> str:
    """Generate a URL-safe slug from a clinic name."""
    return re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')


@auth_bp.route("/signup", methods=["GET", "POST"])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    specialties = Specialty.query.order_by(Specialty.name).all()

    if request.method == "POST":
        clinic_name = request.form.get("clinic_name", "").strip()
        specialty_id = request.form.get("specialty_id", "")
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        if not clinic_name or not specialty_id or not full_name or not email or not password:
            flash("All fields are required.", "danger")
        elif password != confirm:
            flash("Passwords do not match.", "danger")
        elif (pw_errors := _validate_password(password)):
            flash("Password must contain: " + ", ".join(pw_errors) + ".", "danger")
        elif User.query.filter_by(email=email).first():
            flash("An account with that email already exists.", "danger")
        else:
            spec = db.session.get(Specialty, int(specialty_id))
            if not spec:
                flash("Invalid specialty selected.", "danger")
                return render_template("auth/signup.html", specialties=specialties)

            slug = _make_slug(clinic_name)
            # Ensure slug uniqueness
            base_slug = slug
            counter = 1
            while Clinic.query.filter_by(slug=slug).first():
                slug = f"{base_slug}-{counter}"
                counter += 1

            clinic = Clinic(name=clinic_name, slug=slug, specialty_id=spec.id)
            db.session.add(clinic)
            db.session.flush()  # get clinic.id

            user = User(
                email=email,
                full_name=full_name,
                specialty=spec.name,
                clinic_name=clinic_name,
                role="specialist",
            )
            user.set_password(password)
            db.session.add(user)
            db.session.flush()  # get user.id

            membership = ClinicMembership(
                user_id=user.id,
                clinic_id=clinic.id,
                role="owner",
            )
            db.session.add(membership)
            db.session.commit()

            login_user(user)
            flash(f"Clinic created. Welcome, {user.full_name}!", "success")
            return redirect(url_for("auth.onboarding"))

    return render_template("auth/signup.html", specialties=specialties)


@auth_bp.route("/onboarding")
@login_required
def onboarding():
    membership = ClinicMembership.query.filter_by(user_id=current_user.id).first()
    if not membership:
        flash("No clinic found. Please create one first.", "warning")
        return redirect(url_for("auth.signup"))
    clinic = membership.clinic
    return render_template("auth/onboarding.html", clinic=clinic)


@auth_bp.route("/join/<token>", methods=["GET", "POST"])
def join(token):
    membership = ClinicMembership.query.filter_by(invite_token=token).first()
    if not membership:
        flash("Invalid or expired invite link.", "danger")
        return redirect(url_for("auth.login"))

    clinic = membership.clinic

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        if not full_name or not email or not password:
            flash("All fields are required.", "danger")
        elif password != confirm:
            flash("Passwords do not match.", "danger")
        elif (pw_errors := _validate_password(password)):
            flash("Password must contain: " + ", ".join(pw_errors) + ".", "danger")
        elif User.query.filter_by(email=email).first():
            flash("An account with that email already exists.", "danger")
        else:
            specialty_name = clinic.specialty.name if clinic.specialty else None
            user = User(
                email=email,
                full_name=full_name,
                specialty=specialty_name,
                clinic_name=clinic.name,
                role="specialist",
            )
            user.set_password(password)
            db.session.add(user)
            db.session.flush()

            membership.user_id = user.id
            membership.invite_token = None
            db.session.commit()

            login_user(user)
            flash(f"Welcome to {clinic.name}, {user.full_name}!", "success")
            return redirect(url_for("dashboard.index"))

    return render_template("auth/join.html", clinic=clinic, membership=membership)
