from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required

from app.extensions import db
from app.models import Account, Settings

bp = Blueprint("settings", __name__, url_prefix="/settings")

LIVE_PHOTO_SIZES = ["original", "medium", "thumb"]
FILE_MATCH_POLICIES = ["name-size-dedup-with-suffix", "name-id7"]
LOG_LEVELS = ["debug", "info", "error"]


def _int_or_none(value: str):
    value = (value or "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


@bp.route("/", methods=["GET", "POST"])
@login_required
def edit():
    account = Account.query.first()
    if not account:
        flash("Bitte zuerst eine Apple-ID verbinden.", "warning")
        return redirect(url_for("apple_auth.login"))

    settings = account.settings
    if settings is None:
        settings = Settings(account_id=account.id)
        db.session.add(settings)
        db.session.commit()

    if request.method == "POST":
        settings.directory = request.form.get("directory", settings.directory).strip() or settings.directory
        settings.size_original = request.form.get("size_original") == "on"
        settings.size_medium = request.form.get("size_medium") == "on"
        settings.size_thumb = request.form.get("size_thumb") == "on"
        settings.live_photo_size = request.form.get("live_photo_size", "original")
        settings.force_size = request.form.get("force_size") == "on"

        settings.album = request.form.get("album", "All Photos").strip() or "All Photos"
        settings.file_match_policy = request.form.get(
            "file_match_policy", "name-size-dedup-with-suffix"
        )
        settings.skip_videos = request.form.get("skip_videos") == "on"
        settings.skip_live_photos = request.form.get("skip_live_photos") == "on"
        settings.recent = _int_or_none(request.form.get("recent"))
        settings.until_found = _int_or_none(request.form.get("until_found"))

        settings.auto_delete = request.form.get("auto_delete") == "on"
        settings.dry_run = request.form.get("dry_run") == "on"
        settings.only_print_filenames = request.form.get("only_print_filenames") == "on"

        settings.watch_interval_seconds = _int_or_none(request.form.get("watch_interval_seconds"))
        threads = _int_or_none(request.form.get("threads_num")) or 1
        settings.threads_num = max(1, threads)
        settings.log_level = request.form.get("log_level", "info")

        settings.extra_args = request.form.get("extra_args", "").strip()

        db.session.commit()
        flash("Einstellungen gespeichert.", "success")
        return redirect(url_for("settings.edit"))

    return render_template(
        "settings.html",
        account=account,
        settings=settings,
        live_photo_sizes=LIVE_PHOTO_SIZES,
        file_match_policies=FILE_MATCH_POLICIES,
        log_levels=LOG_LEVELS,
    )
