from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required, login_user, logout_user

from app.auth_user import AdminUser, verify_app_credentials

bp = Blueprint("app_auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if verify_app_credentials(username, password):
            login_user(AdminUser())
            flash("Erfolgreich angemeldet.", "success")
            next_url = request.args.get("next") or url_for("dashboard.index")
            return redirect(next_url)
        flash("Benutzername oder Passwort falsch.", "danger")
    return render_template("login.html")


@bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Abgemeldet.", "info")
    return redirect(url_for("app_auth.login"))
