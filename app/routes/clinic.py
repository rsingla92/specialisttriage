"""Clinic management routes: invite, settings."""
from flask import Blueprint, request, jsonify, url_for
from flask_login import login_required, current_user
from app import db
from app.models import Clinic, ClinicMembership

clinic_bp = Blueprint("clinic", __name__, url_prefix="/clinic")


@clinic_bp.route("/invite", methods=["POST"])
@login_required
def invite():
    """Generate invite tokens for comma-separated emails."""
    membership = ClinicMembership.query.filter_by(
        user_id=current_user.id
    ).first()
    if not membership:
        return jsonify({"error": "No clinic found"}), 400

    data = request.get_json(silent=True) or {}
    raw_emails = data.get("emails", "")
    emails = [e.strip().lower() for e in raw_emails.split(",") if e.strip()]

    if not emails:
        return jsonify({"error": "No emails provided"}), 400

    invite_urls = []
    for email in emails:
        token = ClinicMembership.generate_invite_token()
        inv = ClinicMembership(
            clinic_id=membership.clinic_id,
            role="member",
            invite_token=token,
            invite_email=email,
        )
        db.session.add(inv)
        invite_urls.append(url_for("auth.join", token=token, _external=True))

    db.session.commit()
    return jsonify({"ok": True, "invite_urls": invite_urls})


@clinic_bp.route("/ocean-key", methods=["POST"])
@login_required
def save_ocean_key():
    """Save OceanMD API key for the current user's clinic."""
    membership = ClinicMembership.query.filter_by(
        user_id=current_user.id
    ).first()
    if not membership:
        return jsonify({"error": "No clinic found"}), 400

    data = request.get_json(silent=True) or {}
    api_key = data.get("api_key", "").strip()

    clinic = membership.clinic
    clinic.ocean_md_api_key = api_key
    db.session.commit()

    return jsonify({"ok": True})
