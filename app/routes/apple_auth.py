from datetime import datetime

from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for
from flask_login import login_required

from app import icloud_auth
from app.crypto import encrypt
from app.extensions import db
from app.models import Account, Settings

bp = Blueprint("apple_auth", __name__, url_prefix="/apple")


def _get_or_create_account(apple_id: str, domain: str) -> Account:
    account = Account.query.first()
    if account is None:
        account = Account(apple_id=apple_id, domain=domain)
        db.session.add(account)
        db.session.flush()
        db.session.add(Settings(account_id=account.id))
    else:
        account.apple_id = apple_id
        account.domain = domain
        account.authenticated = False
        account.session_trusted = False
    db.session.commit()
    return account


def _finalize_success(apple_id: str, password: str, domain: str):
    account = _get_or_create_account(apple_id, domain)
    account.encrypted_password = encrypt(password)
    account.authenticated = True
    account.session_trusted = True
    account.last_login_at = datetime.utcnow()
    db.session.commit()


@bp.route("/login", methods=["GET", "POST"])
@login_required
def login():
    existing = Account.query.first()
    if request.method == "POST":
        apple_id = request.form.get("apple_id", "").strip()
        password = request.form.get("password", "")
        china = request.form.get("china_mainland") == "on"
        domain = "cn" if china else "com"

        if not apple_id or not password:
            flash("Apple-ID und Passwort werden benötigt.", "danger")
            return render_template("apple_login.html", account=existing)

        try:
            token = icloud_auth.start_login(apple_id, password, china_mainland=china)
            snap = icloud_auth.wait_briefly(token)
        except icloud_auth.LoginError as exc:
            flash(f"Anmeldung fehlgeschlagen: {exc}", "danger")
            return render_template("apple_login.html", account=existing)

        if snap["done"] and snap["success"]:
            icloud_auth.cleanup(token)
            _finalize_success(apple_id, password, domain)
            flash("Erfolgreich mit Apple-ID angemeldet.", "success")
            return redirect(url_for("dashboard.index"))

        if snap["done"] and not snap["success"]:
            icloud_auth.cleanup(token)
            tail = snap["buffer"].strip().splitlines()[-6:]
            message = " | ".join(tail) if tail else f"Exit-Code {snap['returncode']}"
            flash("Anmeldung fehlgeschlagen: " + message, "danger")
            return render_template("apple_login.html", account=existing)

        # Still running: most likely waiting for a 2FA/2SA code.
        session["apple_login_token"] = token
        return redirect(url_for("apple_auth.verify"))

    return render_template("apple_login.html", account=existing)


@bp.route("/verify", methods=["GET", "POST"])
@login_required
def verify():
    token = session.get("apple_login_token")
    if not token:
        flash("Keine offene Anmeldesitzung.", "warning")
        return redirect(url_for("apple_auth.login"))

    if request.method == "POST":
        code = request.form.get("code", "").strip()
        try:
            icloud_auth.submit_code(token, code)
        except icloud_auth.LoginError as exc:
            flash(str(exc), "danger")
            return redirect(url_for("apple_auth.login"))

    return render_template("apple_verify.html")


@bp.route("/verify/status")
@login_required
def verify_status():
    token = session.get("apple_login_token")
    if not token:
        return jsonify({"error": "no_session"}), 400

    try:
        snap = icloud_auth.get_status(token)
    except icloud_auth.LoginError as exc:
        return jsonify({"error": str(exc)}), 400

    if snap["done"]:
        creds = icloud_auth.get_credentials(token)
        icloud_auth.cleanup(token)
        session.pop("apple_login_token", None)

        if snap["success"] and creds:
            apple_id, password, domain = creds
            _finalize_success(apple_id, password, domain)

    return jsonify(snap)


@bp.route("/disconnect", methods=["POST"])
@login_required
def disconnect():
    account = Account.query.first()
    if account:
        account.authenticated = False
        account.session_trusted = False
        account.encrypted_password = None
        db.session.commit()
        flash("Apple-ID wurde getrennt.", "info")
    return redirect(url_for("dashboard.index"))
