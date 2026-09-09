"""Uploads the icloudpd download directory to Dropbox.

Runs as its own background thread (mirroring icloudpd_runner's job
tracking), independent of icloudpd itself - it's triggered either
manually or automatically once a sync run finishes successfully. Already-
uploaded files are tracked in the UploadedFile table (by relative path +
size + mtime) so repeat passes only transfer what's new or changed.
"""
import os
import threading
from datetime import datetime
from pathlib import Path

import dropbox
from dropbox import files as dbx_files

from app import dropbox_client
from app.config import Config
from app.extensions import db
from app.models import UploadedFile

_lock = threading.Lock()
_state = {
    "running": False,
    "log_file": None,
    "started_at": None,
    "finished_at": None,
    "uploaded": 0,
    "skipped": 0,
    "failed": 0,
    "error": None,
}

_CHUNK_SIZE = 8 * 1024 * 1024  # 8 MiB


def is_uploading() -> bool:
    with _lock:
        return _state["running"]


def get_status() -> dict:
    with _lock:
        return dict(_state)


def _log(fh, message: str):
    fh.write(f"{datetime.utcnow():%Y-%m-%d %H:%M:%S} {message}\n".encode())
    fh.flush()


def _dropbox_path(dropbox_folder: str, relative_path: str) -> str:
    folder = "/" + dropbox_folder.strip("/")
    rel = relative_path.replace(os.sep, "/")
    return f"{folder}/{rel}" if folder != "/" else f"/{rel}"


def _upload_one(dbx: dropbox.Dropbox, path: Path, dropbox_path: str):
    file_size = path.stat().st_size
    with open(path, "rb") as f:
        if file_size <= _CHUNK_SIZE:
            dbx.files_upload(f.read(), dropbox_path, mode=dbx_files.WriteMode.overwrite)
            return

        session = dbx.files_upload_session_start(f.read(_CHUNK_SIZE))
        cursor = dbx_files.UploadSessionCursor(session_id=session.session_id, offset=f.tell())
        commit = dbx_files.CommitInfo(path=dropbox_path, mode=dbx_files.WriteMode.overwrite)
        while True:
            chunk = f.read(_CHUNK_SIZE)
            remaining = file_size - f.tell()
            if remaining <= 0:
                dbx.files_upload_session_finish(chunk, cursor, commit)
                break
            dbx.files_upload_session_append_v2(chunk, cursor)
            cursor.offset = f.tell()


def _run_upload(app, local_dir: str, dropbox_folder: str, log_path: Path):
    with app.app_context():
        log_fh = open(log_path, "wb", buffering=0)
        uploaded = skipped = failed = 0
        try:
            dbx = dropbox_client.get_client()
            if dbx is None:
                _log(log_fh, "Kein Dropbox-Konto verbunden.")
                with _lock:
                    _state["error"] = "Kein Dropbox-Konto verbunden."
                return

            root = Path(local_dir)
            if not root.exists():
                _log(log_fh, f"Zielverzeichnis {root} existiert nicht.")
                with _lock:
                    _state["error"] = f"Zielverzeichnis {root} existiert nicht."
                return

            _log(log_fh, f"Starte Dropbox-Upload: {root} -> {dropbox_folder}")
            existing = {u.relative_path: u for u in UploadedFile.query.all()}

            for path in sorted(root.rglob("*")):
                if not path.is_file():
                    continue
                rel = str(path.relative_to(root))
                stat = path.stat()
                prev = existing.get(rel)
                if prev and prev.size == stat.st_size and abs(prev.mtime - stat.st_mtime) < 1:
                    skipped += 1
                    continue

                dest = _dropbox_path(dropbox_folder, rel)
                try:
                    _upload_one(dbx, path, dest)
                except Exception as exc:  # noqa: BLE001
                    failed += 1
                    _log(log_fh, f"FEHLER bei {rel}: {exc}")
                    continue

                if prev:
                    prev.size = stat.st_size
                    prev.mtime = stat.st_mtime
                    prev.uploaded_at = datetime.utcnow()
                else:
                    db.session.add(
                        UploadedFile(relative_path=rel, size=stat.st_size, mtime=stat.st_mtime)
                    )
                db.session.commit()
                uploaded += 1
                _log(log_fh, f"Hochgeladen: {dest}")

                with _lock:
                    _state["uploaded"] = uploaded
                    _state["skipped"] = skipped
                    _state["failed"] = failed

            _log(
                log_fh,
                f"Fertig. {uploaded} hochgeladen, {skipped} unveraendert, {failed} fehlgeschlagen.",
            )
        except Exception as exc:  # noqa: BLE001
            _log(log_fh, f"Unerwarteter Fehler: {exc}")
            with _lock:
                _state["error"] = str(exc)
        finally:
            log_fh.close()
            with _lock:
                _state["running"] = False
                _state["finished_at"] = datetime.utcnow()
                _state["uploaded"] = uploaded
                _state["skipped"] = skipped
                _state["failed"] = failed


def start_upload(app, local_dir: str, dropbox_folder: str) -> bool:
    """Starts an upload pass in the background. Returns False (no-op) if
    one is already running."""
    with _lock:
        if _state["running"]:
            return False
        Config.ensure_dirs()
        log_path = Config.LOG_DIR / f"{datetime.utcnow():%Y%m%d_%H%M%S}_dropbox.log"
        _state.update(
            {
                "running": True,
                "log_file": str(log_path),
                "started_at": datetime.utcnow(),
                "finished_at": None,
                "uploaded": 0,
                "skipped": 0,
                "failed": 0,
                "error": None,
            }
        )

    thread = threading.Thread(
        target=_run_upload, args=(app, local_dir, dropbox_folder, log_path), daemon=True
    )
    thread.start()
    return True
