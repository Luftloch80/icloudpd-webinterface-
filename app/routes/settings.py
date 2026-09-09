from pathlib import Path

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import login_required

from app.config import Config
from app.extensions import db
from app.models import Account, Settings

bp = Blueprint("settings", __name__, url_prefix="/settings")

# Only the persistent /data mount can be safely offered to the browser-based
# folder picker: it's the only location guaranteed to survive container
# restarts and (via docker-compose volumes) map to something on the host.
BROWSE_ROOT = Config.DATA_DIR

LIVE_PHOTO_SIZES = ["original", "medium", "thumb"]
FILE_MATCH_POLICIES = ["name-size-dedup-with-suffix", "name-id7"]
LOG_LEVELS = ["debug", "info", "error"]

# Presets for icloudpd's --folder-structure option (a Python format string
# wrapping strftime directives). "custom" is a UI-only sentinel handled
# below, not a real icloudpd value.
FOLDER_STRUCTURE_PRESETS = [
    ("{:%Y/%m/%d}", "Jahr/Monat/Tag (Standard)"),
    ("{:%Y/%m}", "Jahr/Monat"),
    ("{:%m/%Y}", "Monat/Jahr"),
    ("{:%d/%m/%Y}", "Tag/Monat/Jahr"),
    ("{:%Y}", "Nur Jahr"),
    ("none", "Kein Unterordner (alle Fotos in einem Ordner)"),
]
_FOLDER_STRUCTURE_VALUES = {value for value, _ in FOLDER_STRUCTURE_PRESETS}


def _int_or_none(value: str):
    value = (value or "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _safe_resolve(relative_path: str) -> Path:
    """Resolves a client-supplied path as relative to BROWSE_ROOT and
    guarantees the result cannot escape it (no `..`, no symlink escape)."""
    Config.ensure_dirs()
    root = BROWSE_ROOT.resolve()
    relative_path = (relative_path or "").strip().lstrip("/\\")
    candidate = (root / relative_path).resolve() if relative_path else root
    if candidate != root and root not in candidate.parents:
        raise ValueError("Pfad außerhalb des erlaubten Bereichs.")
    return candidate


@bp.route("/browse")
@login_required
def browse():
    try:
        current = _safe_resolve(request.args.get("path", ""))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    if not current.exists():
        current = BROWSE_ROOT.resolve()

    try:
        entries = sorted(
            (p.name for p in current.iterdir() if p.is_dir() and not p.name.startswith(".")),
            key=str.lower,
        )
    except OSError as exc:
        return jsonify({"error": f"Verzeichnis konnte nicht gelesen werden: {exc}"}), 400

    root = BROWSE_ROOT.resolve()
    rel = current.relative_to(root)
    parent_rel = None if current == root else str(rel.parent).replace("\\", "/")
    if parent_rel == ".":
        parent_rel = ""

    return jsonify(
        {
            "path": str(rel).replace("\\", "/") if str(rel) != "." else "",
            "absolute_path": str(current),
            "parent": parent_rel,
            "folders": entries,
        }
    )


@bp.route("/browse/mkdir", methods=["POST"])
@login_required
def browse_mkdir():
    data = request.get_json(silent=True) or {}
    try:
        parent = _safe_resolve(data.get("path", ""))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    name = (data.get("name") or "").strip()
    if not name or "/" in name or "\\" in name or name in (".", ".."):
        return jsonify({"error": "Ungültiger Ordnername."}), 400

    new_dir = parent / name
    try:
        new_dir.mkdir(exist_ok=True)
    except OSError as exc:
        return jsonify({"error": f"Ordner konnte nicht angelegt werden: {exc}"}), 400

    return jsonify({"ok": True})


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

        preset = request.form.get("folder_structure_preset", "{:%Y/%m/%d}")
        if preset == "custom":
            custom = request.form.get("folder_structure_custom", "").strip()
            settings.folder_structure = custom or "{:%Y/%m/%d}"
        elif preset in _FOLDER_STRUCTURE_VALUES:
            settings.folder_structure = preset
        else:
            settings.folder_structure = "{:%Y/%m/%d}"

        # Empty = whole library (icloudpd's own default when --album is
        # omitted). Do NOT fall back to a guessed name like "All Photos"
        # here: icloudpd looks that up as an exact album name and crashes
        # with a KeyError if no such album exists.
        settings.album = request.form.get("album", "").strip()
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

    is_custom_folder_structure = settings.folder_structure not in _FOLDER_STRUCTURE_VALUES

    return render_template(
        "settings.html",
        account=account,
        settings=settings,
        live_photo_sizes=LIVE_PHOTO_SIZES,
        file_match_policies=FILE_MATCH_POLICIES,
        log_levels=LOG_LEVELS,
        folder_structure_presets=FOLDER_STRUCTURE_PRESETS,
        is_custom_folder_structure=is_custom_folder_structure,
    )
