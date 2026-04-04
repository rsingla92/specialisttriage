"""Clinic management routes: team, settings, invites."""
import secrets
from flask import Blueprint, render_template, request, jsonify, url_for, flash, redirect, abort
from flask_login import login_required, current_user
from app import db
from app.models import Clinic, ClinicMembership, User, CLINIC_ADMIN_ROLES
from functools import wraps

clinic_bp = Blueprint("clinic", __name__)


def clinic_admin_required(f):
    """Decorator: require the user to be an admin of their primary clinic."""
    @wraps(f)
    def decorated(*args, **kwargs):
        clinic = current_user.primary_clinic
        if not clinic or not current_user.is_clinic_admin(clinic.id):
            abort(403)
        return f(*args, **kwargs)
    return decorated


@clinic_bp.route("/team")
@login_required
def team():
    """View clinic team members."""
    clinic = current_user.primary_clinic
    if not clinic:
        flash("No clinic found. Create one first.", "warning")
        return redirect(url_for("auth.signup"))
    members = ClinicMembership.query.filter_by(clinic_id=clinic.id, is_active=True).all()
    pending = ClinicMembership.query.filter_by(
        clinic_id=clinic.id, invite_token=db.not_(None),
    ).filter(ClinicMembership.invite_token.isnot(None)).all()
    is_admin = current_user.is_clinic_admin(clinic.id)
    return render_template("clinic/team.html", clinic=clinic, members=members,
                           pending=pending, is_admin=is_admin)


@clinic_bp.route("/settings")
@login_required
@clinic_admin_required
def settings():
    """Clinic settings hub."""
    clinic = current_user.primary_clinic
    members = ClinicMembership.query.filter_by(clinic_id=clinic.id, is_active=True).all()
    pending = ClinicMembership.query.filter_by(
        clinic_id=clinic.id,
    ).filter(ClinicMembership.invite_token.isnot(None)).all()
    return render_template("clinic/settings.html", clinic=clinic, members=members,
                           pending=pending)


@clinic_bp.route("/settings", methods=["POST"])
@login_required
@clinic_admin_required
def update_settings():
    """Update clinic settings."""
    clinic = current_user.primary_clinic
    queue_mode = request.form.get("queue_mode", "hybrid")
    if queue_mode in ("shared", "individual", "hybrid"):
        new_settings = dict(clinic.settings or {})
        new_settings["queue_mode"] = queue_mode
        clinic.settings = new_settings  # assign new dict to trigger SQLAlchemy change detection
        db.session.commit()
        flash("Settings updated.", "success")
    return redirect(url_for("clinic.settings"))


@clinic_bp.route("/settings/general", methods=["POST"])
@login_required
@clinic_admin_required
def update_general():
    """Update general clinic information (name, address)."""
    clinic = current_user.primary_clinic
    name = request.form.get("clinic_name", "").strip()
    address = request.form.get("clinic_address", "").strip()
    if name:
        clinic.name = name
    clinic.address = address or None
    db.session.commit()
    flash("General settings updated.", "success")
    return redirect(url_for("clinic.settings") + "#general")


@clinic_bp.route("/invite", methods=["POST"])
@login_required
@clinic_admin_required
def invite():
    """Generate invite links for new team members."""
    clinic = current_user.primary_clinic
    data = request.get_json(silent=True) or {}
    raw_emails = data.get("emails", "")
    emails = [e.strip().lower() for e in raw_emails.split(",") if e.strip()]

    if not emails:
        return jsonify({"error": "No emails provided"}), 400

    invite_urls = []
    for email in emails:
        token = secrets.token_urlsafe(32)
        inv = ClinicMembership(
            clinic_id=clinic.id,
            role="specialist",
            invite_token=token,
        )
        db.session.add(inv)
        invite_urls.append(url_for("auth.join", token=token, _external=True))

    db.session.commit()
    return jsonify({"ok": True, "invite_urls": invite_urls})


@clinic_bp.route("/ocean-key", methods=["POST"])
@login_required
@clinic_admin_required
def save_ocean_key():
    """Save OceanMD API key for the clinic."""
    clinic = current_user.primary_clinic
    data = request.get_json(silent=True) or {}
    api_key = data.get("api_key", "").strip()
    clinic.ocean_md_api_key = api_key
    db.session.commit()
    return jsonify({"ok": True})


@clinic_bp.route("/remove-member", methods=["POST"])
@login_required
@clinic_admin_required
def remove_member():
    """Remove a member from the clinic."""
    clinic = current_user.primary_clinic
    user_id = request.form.get("user_id", type=int)
    if not user_id or user_id == current_user.id:
        flash("Cannot remove yourself.", "warning")
        return redirect(url_for("clinic.team"))

    membership = ClinicMembership.query.filter_by(
        clinic_id=clinic.id, user_id=user_id,
    ).first()
    if membership:
        membership.is_active = False
        db.session.commit()
        flash("Member removed.", "success")
    return redirect(url_for("clinic.team"))
