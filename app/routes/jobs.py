from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, url_for
from flask_login import login_required

from app import icloudpd_runner
from app.extensions import db
from app.models import Account, RunLog

bp = Blueprint("jobs", __name__, url_prefix="/jobs")


def _require_account():
    account = Account.query.first()
    if not account or not account.authenticated:
        flash("Bitte zuerst eine Apple-ID verbinden und anmelden.", "warning")
        return None
    return account


@bp.route("/start/<mode>", methods=["POST"])
@login_required
def start(mode):
    if mode not in ("once", "continuous"):
        flash("Ungültiger Modus.", "danger")
        return redirect(url_for("dashboard.index"))

    account = _require_account()
    if not account:
        return redirect(url_for("dashboard.index"))

    try:
        icloudpd_runner.start_job(current_app._get_current_object(), account, account.settings, mode=mode)
        flash("Job gestartet.", "success")
    except RuntimeError as exc:
        flash(str(exc), "danger")

    return redirect(url_for("dashboard.index"))


@bp.route("/stop", methods=["POST"])
@login_required
def stop():
    account = Account.query.first()
    if account and icloudpd_runner.stop_job(account.id):
        flash("Job gestoppt.", "info")
    else:
        flash("Es läuft kein Job.", "warning")
    return redirect(url_for("dashboard.index"))


@bp.route("/status")
@login_required
def status():
    account = Account.query.first()
    if not account:
        return jsonify({"running": False, "log": ""})

    running = icloudpd_runner.is_running(account.id)
    log_text = ""
    progress = {"total": None, "processed": 0, "remaining": None, "eta_seconds": None}
    run_log = None
    if running:
        run_log = db.session.get(RunLog, running["run_log_id"])
    else:
        run_log = (
            RunLog.query.filter_by(account_id=account.id)
            .order_by(RunLog.started_at.desc())
            .first()
        )

    if run_log:
        full_text = icloudpd_runner.read_full_log(run_log.log_file)
        progress = icloudpd_runner.parse_progress(full_text, run_log.started_at)

        display_level = account.settings.log_level if account.settings else "info"
        tail_text = full_text[-40000:] if len(full_text) > 40000 else full_text
        log_text = icloudpd_runner.filter_log_by_level(tail_text, display_level)

    return jsonify(
        {
            "running": bool(running),
            "status": run_log.status if run_log else None,
            "log": log_text,
            **progress,
        }
    )


@bp.route("/history")
@login_required
def history():
    account = Account.query.first()
    runs = []
    if account:
        runs = (
            RunLog.query.filter_by(account_id=account.id)
            .order_by(RunLog.started_at.desc())
            .limit(50)
            .all()
        )
    return render_template("history.html", runs=runs)


@bp.route("/log/<int:run_id>")
@login_required
def view_log(run_id):
    run_log = db.session.get(RunLog, run_id)
    if not run_log:
        flash("Log nicht gefunden.", "danger")
        return redirect(url_for("jobs.history"))
    log_text = icloudpd_runner.tail_log(run_log.log_file, max_bytes=200000)
    return render_template("job_log.html", run_log=run_log, log_text=log_text)


@bp.route("/help")
@login_required
def help_text():
    return render_template("help.html", help_text=icloudpd_runner.get_help_text())
