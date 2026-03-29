"""Referral management routes."""
from datetime import datetime, date, timezone
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, jsonify
from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError
from app import db
from app.models import Referral, TriageResult, Feedback, ResponseTemplate, BatchAction
from app.services.triage_engine import triage_referral, ReferralData
from app.services.ocean_md import OceanMDService

_ALLOWED_DECISIONS = frozenset({"accepted", "declined", "needs_info", "redirected"})
_MAX_BATCH_SIZE = 100

referrals_bp = Blueprint("referrals", __name__)

# Fallback date of birth used when the OceanMD record contains an unparseable value
_DEFAULT_DOB = date(1970, 1, 1)


def _run_triage(referral: Referral) -> TriageResult:
    """Run the triage engine on a referral and persist the result."""
    rd = ReferralData(
        chief_complaint=referral.chief_complaint or "",
        clinical_notes=referral.clinical_notes or "",
        relevant_history=referral.relevant_history or "",
        current_medications=referral.current_medications or "",
        allergies=referral.allergies or "",
        relevant_investigations=referral.relevant_investigations or "",
        patient_age=referral.patient_age,
        specialty_requested=referral.specialty_requested or "Urology",
    )
    output = triage_referral(rd)

    referral.clinical_category = output.clinical_category
    referral.missing_workup = output.missing_workup

    tr = TriageResult(
        referral_id=referral.id,
        appropriateness_score=output.appropriateness_score,
        completeness_score=output.completeness_score,
        urgency_score=output.urgency_score,
        recommended_priority=output.recommended_priority,
        missing_information=output.missing_information,
        triage_notes=output.triage_notes,
        flags=output.flags,
        model_version=output.model_version,
    )
    referral.priority = output.recommended_priority
    referral.status = (
        "needs_info" if output.recommended_priority == "needs_info" else "triaged"
    )
    referral.triaged_at = datetime.now(timezone.utc)
    return tr


@referrals_bp.route("/import", methods=["POST"])
@login_required
def import_referrals():
    """Bulk-import pending referrals from OceanMD and run auto-triage."""
    ocean = OceanMDService.from_app()
    raw_referrals = ocean.fetch_pending_referrals()

    # Preload all existing ocean_referral_ids in a single query to avoid N+1.
    incoming_ids = [r.get("ocean_referral_id") for r in raw_referrals if r.get("ocean_referral_id")]
    existing_ids: set[str] = set()
    if incoming_ids:
        existing_ids = {
            row.ocean_referral_id
            for row in Referral.query.filter(
                Referral.ocean_referral_id.in_(incoming_ids)
            ).with_entities(Referral.ocean_referral_id).all()
        }

    imported = 0
    skipped = 0
    for raw in raw_referrals:
        ocean_id = raw.get("ocean_referral_id")
        if ocean_id and ocean_id in existing_ids:
            skipped += 1
            continue

        try:
            dob_raw = raw.get("patient_dob", "")
            if isinstance(dob_raw, str) and dob_raw:
                dob = date.fromisoformat(dob_raw[:10])
            elif isinstance(dob_raw, date):
                dob = dob_raw
            else:
                dob = _DEFAULT_DOB
        except ValueError:
            dob = _DEFAULT_DOB

        referral = Referral(
            ocean_referral_id=ocean_id,
            patient_first_name=raw.get("patient_first_name", ""),
            patient_last_name=raw.get("patient_last_name", ""),
            patient_dob=dob,
            patient_phn=raw.get("patient_phn", ""),
            referring_physician_name=raw.get("referring_physician_name", ""),
            referring_clinic=raw.get("referring_clinic", ""),
            referring_physician_phone=raw.get("referring_physician_phone", ""),
            referring_physician_fax=raw.get("referring_physician_fax", ""),
            chief_complaint=raw.get("chief_complaint", ""),
            clinical_notes=raw.get("clinical_notes", ""),
            relevant_history=raw.get("relevant_history", ""),
            current_medications=raw.get("current_medications", ""),
            allergies=raw.get("allergies", ""),
            relevant_investigations=raw.get("relevant_investigations", ""),
            specialty_requested=raw.get("specialty_requested", "Urology"),
            specialist_id=current_user.id,
        )
        db.session.add(referral)
        try:
            db.session.begin_nested()  # savepoint so one failure doesn't kill the batch
            db.session.flush()  # get referral.id for TriageResult FK
            tr = _run_triage(referral)
            db.session.add(tr)
            imported += 1
        except Exception:
            db.session.rollback()  # rolls back to savepoint, not entire transaction
            continue

    db.session.commit()
    flash(
        f"Imported {imported} new referral(s) from OceanMD "
        f"({skipped} already on file, all auto-triaged).",
        "success" if imported else "info",
    )
    return redirect(url_for("dashboard.index"))


@referrals_bp.route("/<int:referral_id>")
@login_required
def detail(referral_id):
    referral = Referral.query.get_or_404(referral_id)
    if referral.specialist_id != current_user.id and current_user.role != "admin":
        abort(403)
    return render_template("referrals/detail.html", referral=referral)


@referrals_bp.route("/<int:referral_id>/retriage", methods=["POST"])
@login_required
def retriage(referral_id):
    referral = Referral.query.get_or_404(referral_id)
    if referral.specialist_id != current_user.id and current_user.role != "admin":
        abort(403)

    if referral.triage_result:
        db.session.delete(referral.triage_result)
        db.session.flush()

    tr = _run_triage(referral)
    db.session.add(tr)
    db.session.commit()
    flash("Referral re-triaged successfully.", "success")
    return redirect(url_for("referrals.detail", referral_id=referral_id))


@referrals_bp.route("/<int:referral_id>/feedback", methods=["GET", "POST"])
@login_required
def send_feedback(referral_id):
    referral = Referral.query.get_or_404(referral_id)
    if referral.specialist_id != current_user.id and current_user.role != "admin":
        abort(403)

    if request.method == "POST":
        decision = request.form.get("decision", "")
        message = request.form.get("message", "").strip()
        recommended_workup = request.form.get("recommended_workup", "").strip()
        redirect_to = request.form.get("redirect_to", "").strip()

        if not decision or not message:
            flash("Decision and message are required.", "danger")
            return render_template("referrals/feedback.html", referral=referral)

        if decision not in _ALLOWED_DECISIONS:
            abort(400)

        # Remove old feedback if re-sending
        if referral.feedback:
            db.session.delete(referral.feedback)
            db.session.flush()

        fb = Feedback(
            referral_id=referral.id,
            specialist_id=current_user.id,
            decision=decision,
            message=message,
            recommended_workup=recommended_workup or None,
            redirect_to=redirect_to or None,
        )
        db.session.add(fb)

        # Update referral status; only mark resolved_at for terminal decisions.
        referral.status = decision
        if decision in {"accepted", "declined", "redirected"}:
            referral.resolved_at = datetime.now(timezone.utc)
        else:
            # Clear any stale resolution timestamp when moving back to a non-terminal state.
            referral.resolved_at = None

        # Send via OceanMD
        if referral.ocean_referral_id:
            ocean = OceanMDService.from_app()
            sent = ocean.send_feedback(
                referral.ocean_referral_id,
                message,
                decision,
                recommended_workup=recommended_workup or None,
                redirect_to=redirect_to or None,
            )
            fb.delivery_status = "sent" if sent else "failed"
        else:
            # No OceanMD referral available; feedback is saved locally only.
            fb.delivery_status = "saved"

        db.session.commit()

        # Tailor final message based on delivery status to avoid misleading UX.
        if fb.delivery_status == "sent":
            flash("Feedback sent to referring physician.", "success")
        elif fb.delivery_status == "failed":
            flash(
                "Feedback saved but could not be delivered via OceanMD – "
                "please fax the referring physician directly.",
                "warning",
            )
        else:
            flash("Feedback saved for referring physician.", "success")
        return redirect(url_for("referrals.detail", referral_id=referral_id))

    return render_template("referrals/feedback.html", referral=referral)


@referrals_bp.route("/batch", methods=["POST"])
@login_required
def batch_action():
    """Process a batch action on multiple referrals."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400

    referral_ids = data.get("referral_ids", [])
    action_type = data.get("action_type", "")
    template_id = data.get("template_id")

    if not referral_ids:
        return jsonify({"error": "No referral IDs provided"}), 400
    if len(referral_ids) > _MAX_BATCH_SIZE:
        return jsonify({"error": f"Maximum {_MAX_BATCH_SIZE} referrals per batch"}), 400
    if action_type not in _ALLOWED_DECISIONS:
        return jsonify({"error": "Invalid action type"}), 400

    # Ownership check: only process referrals belonging to current user
    owned = Referral.query.filter(
        Referral.id.in_(referral_ids),
        Referral.specialist_id == current_user.id,
    ).all()
    owned_map = {r.id: r for r in owned}
    rejected_ids = [rid for rid in referral_ids if rid not in owned_map]

    # Load template if provided
    template = None
    if template_id:
        template = ResponseTemplate.query.get(template_id)

    ocean = OceanMDService.from_app()
    results = []

    batch = BatchAction(
        referral_ids=referral_ids,
        action_type=action_type,
        template_id=template_id,
        executed_by=current_user.id,
    )
    db.session.add(batch)
    db.session.flush()

    for rid in referral_ids:
        if rid in rejected_ids:
            results.append({"id": rid, "status": "rejected", "reason": "not_owned"})
            continue

        referral = owned_map[rid]

        # Skip referrals that already have feedback
        if referral.feedback:
            results.append({"id": rid, "status": "skipped", "reason": "already_actioned"})
            continue

        # Skip ED referrals for batch actions
        if referral.clinical_category == "erectile_dysfunction":
            results.append({"id": rid, "status": "skipped", "reason": "ed_referral"})
            continue

        # Build message from template or default
        if template:
            message = template.render(
                patient_name=referral.patient_full_name,
                specialist_name=current_user.full_name,
            )
        else:
            message = f"Referral for {referral.patient_full_name} has been {action_type}."

        fb = Feedback(
            referral_id=referral.id,
            specialist_id=current_user.id,
            decision=action_type,
            message=message,
            batch_action_id=batch.id,
        )

        # Use savepoint to handle concurrent feedback creation gracefully.
        # The unique constraint on Feedback.referral_id catches the race.
        try:
            db.session.begin_nested()
            db.session.add(fb)

            referral.status = action_type
            if action_type in {"accepted", "declined", "redirected"}:
                referral.resolved_at = datetime.now(timezone.utc)
            else:
                referral.resolved_at = None

            db.session.flush()
        except IntegrityError:
            db.session.rollback()
            results.append({"id": rid, "status": "skipped", "reason": "already_actioned"})
            continue

        # Send via OceanMD
        if referral.ocean_referral_id:
            sent = ocean.send_feedback(
                referral.ocean_referral_id, message, action_type,
            )
            fb.delivery_status = "sent" if sent else "failed"
            results.append({
                "id": rid,
                "status": "sent" if sent else "failed",
                "patient": referral.patient_full_name,
            })
        else:
            fb.delivery_status = "saved"
            results.append({"id": rid, "status": "saved", "patient": referral.patient_full_name})

    db.session.commit()
    return jsonify({"results": results, "batch_id": batch.id})
