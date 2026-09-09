from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, session, url_for
from flask_login import login_required

from app import dropbox_client, dropbox_uploader, icloudpd_runner
from app.extensions import db
from app.models import Account, DropboxConnection

bp = Blueprint("dropbox", __name__, url_prefix="/dropbox")


@bp.route("/")
@login_required
def index():
    account = Account.query.first()
    connection = DropboxConnection.query.first()
    return render_template(
        "dropbox.html",
        account=account,
        connection=connection,
        app_configured=dropbox_client.app_configured(),
        uploading=dropbox_uploader.is_uploading(),
    )


@bp.route("/connect", methods=["GET", "POST"])
@login_required
def connect():
    if not dropbox_client.app_configured():
        flash(
            "DROPBOX_APP_KEY/DROPBOX_APP_SECRET sind nicht konfiguriert. "
            "Siehe README für die Einrichtung einer Dropbox-App.",
            "danger",
        )
        return redirect(url_for("dropbox.index"))

    if request.method == "POST":
        try:
            token, authorize_url = dropbox_client.start_auth_flow()
        except dropbox_client.DropboxConfigError as exc:
            flash(str(exc), "danger")
            return redirect(url_for("dropbox.index"))
        session["dropbox_auth_token"] = token
        return render_template("dropbox_connect.html", authorize_url=authorize_url)

    # A GET always shows the "start" button. Re-rendering the code-entry
    # form after a failed code would need the authorize_url again, which
    # isn't kept around - simplest is to have the user start the flow over.
    session.pop("dropbox_auth_token", None)
    return render_template("dropbox_connect.html", authorize_url=None)


@bp.route("/connect/finish", methods=["POST"])
@login_required
def connect_finish():
    token = session.pop("dropbox_auth_token", None)
    code = request.form.get("code", "").strip()
    if not token or not code:
        flash("Bitte zuerst die Verbindung starten und den Code eingeben.", "warning")
        return redirect(url_for("dropbox.connect"))

    try:
        email = dropbox_client.finish_auth_flow(token, code)
    except dropbox_client.DropboxAuthError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("dropbox.connect"))

    flash(f"Dropbox verbunden als {email}.", "success")
    return redirect(url_for("dropbox.index"))


@bp.route("/disconnect", methods=["POST"])
@login_required
def disconnect():
    dropbox_client.disconnect()
    flash("Dropbox-Verbindung getrennt.", "info")
    return redirect(url_for("dropbox.index"))


@bp.route("/settings", methods=["POST"])
@login_required
def save_settings():
    account = Account.query.first()
    if not account or not account.settings:
        flash("Bitte zuerst eine Apple-ID verbinden.", "warning")
        return redirect(url_for("dropbox.index"))

    settings = account.settings
    settings.dropbox_enabled = request.form.get("dropbox_enabled") == "on"
    folder = request.form.get("dropbox_folder", "").strip()
    settings.dropbox_folder = folder or "/iCloud-Fotos"
    db.session.commit()
    flash("Dropbox-Einstellungen gespeichert.", "success")
    return redirect(url_for("dropbox.index"))


@bp.route("/upload-now", methods=["POST"])
@login_required
def upload_now():
    account = Account.query.first()
    if not account or not account.settings:
        flash("Bitte zuerst eine Apple-ID verbinden.", "warning")
        return redirect(url_for("dropbox.index"))
    if not DropboxConnection.query.first():
        flash("Bitte zuerst ein Dropbox-Konto verbinden.", "warning")
        return redirect(url_for("dropbox.index"))

    started = dropbox_uploader.start_upload(
        current_app._get_current_object(), account.settings.directory, account.settings.dropbox_folder
    )
    if started:
        flash("Dropbox-Upload gestartet.", "success")
    else:
        flash("Es läuft bereits ein Dropbox-Upload.", "warning")
    return redirect(url_for("dropbox.index"))


@bp.route("/status")
@login_required
def status():
    state = dropbox_uploader.get_status()
    log_text = icloudpd_runner.tail_log(state["log_file"]) if state.get("log_file") else ""
    started_at = state["started_at"].isoformat() if state.get("started_at") else None
    finished_at = state["finished_at"].isoformat() if state.get("finished_at") else None
    return jsonify(
        {
            "running": state["running"],
            "uploaded": state["uploaded"],
            "skipped": state["skipped"],
            "failed": state["failed"],
            "error": state["error"],
            "started_at": started_at,
            "finished_at": finished_at,
            "log": log_text,
        }
    )
