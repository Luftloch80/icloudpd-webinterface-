import os
import re
import shlex
import signal
import subprocess
import threading
from datetime import datetime
from pathlib import Path

from app.config import Config
from app.crypto import decrypt
from app.extensions import db
from app.models import RunLog

_lock = threading.Lock()
# account_id -> {"proc": Popen, "run_log_id": int}
_running: dict[int, dict] = {}

_help_cache: str | None = None


def get_help_text() -> str:
    global _help_cache
    if _help_cache is not None:
        return _help_cache
    try:
        result = subprocess.run(
            [Config.ICLOUDPD_BIN, "--help"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        _help_cache = result.stdout or result.stderr
    except Exception as exc:  # noqa: BLE001
        _help_cache = f"icloudpd --help konnte nicht ausgeführt werden: {exc}"
    return _help_cache


def _cookie_dir_for(apple_id: str) -> str:
    safe = "".join(c if c.isalnum() or c in "@._-" else "_" for c in apple_id)
    path = Config.COOKIE_DIR / safe
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def build_args(account, settings, mode: str) -> list[str]:
    args = [Config.ICLOUDPD_BIN]
    args += ["--directory", settings.directory]
    args += ["--username", account.apple_id]
    args += ["--cookie-directory", _cookie_dir_for(account.apple_id)]
    if account.domain and account.domain != "com":
        args += ["--domain", account.domain]

    for size in settings.size_list():
        args += ["--size", size]
    args += ["--live-photo-size", settings.live_photo_size]
    if settings.force_size:
        args.append("--force-size")
    if settings.folder_structure:
        args += ["--folder-structure", settings.folder_structure]

    if settings.album:
        args += ["--album", settings.album]
    if settings.file_match_policy:
        args += ["--file-match-policy", settings.file_match_policy]
    if settings.skip_videos:
        args.append("--skip-videos")
    if settings.skip_live_photos:
        args.append("--skip-live-photos")
    if settings.recent is not None:
        args += ["--recent", str(settings.recent)]
    if settings.until_found is not None:
        args += ["--until-found", str(settings.until_found)]

    if settings.auto_delete:
        args.append("--auto-delete")
    if settings.dry_run:
        args.append("--dry-run")
    if settings.only_print_filenames:
        args.append("--only-print-filenames")

    if settings.threads_num and settings.threads_num > 1:
        args += ["--threads-num", str(settings.threads_num)]
    # Always capture at debug level internally, regardless of the user's
    # display preference (settings.log_level): the "remaining photos"
    # progress calculation needs the debug-only "already exists" skip
    # lines, not just the info-level "Downloaded ..." lines. What the user
    # actually sees is filtered down from this by filter_log_by_level().
    args += ["--log-level", "debug"]

    if mode == "continuous" and settings.watch_interval_seconds:
        args += ["--watch-with-interval", str(settings.watch_interval_seconds)]

    args.append("--no-progress-bar")

    if settings.extra_args and settings.extra_args.strip():
        args += shlex.split(settings.extra_args)

    password = None
    if account.encrypted_password:
        try:
            password = decrypt(account.encrypted_password)
        except Exception:  # noqa: BLE001
            password = None
    if password:
        args += ["--password", password]

    return args


def is_running(account_id: int) -> dict | None:
    with _lock:
        return _running.get(account_id)


def stop_job(account_id: int) -> bool:
    with _lock:
        entry = _running.get(account_id)
    if not entry:
        return False

    run_log = db.session.get(RunLog, entry["run_log_id"])
    if run_log and run_log.status == "running":
        run_log.status = "stopped"
        db.session.commit()

    proc: subprocess.Popen = entry["proc"]
    _terminate_process_group(proc)
    return True


def _terminate_process_group(proc: subprocess.Popen, timeout: int = 15):
    """Signals the whole process group, not just the directly spawned PID.

    The installed `icloudpd` command is a thin wrapper that runs the actual
    (compiled) worker as its own child via `subprocess.call`. Killing only
    the wrapper leaves that worker running as an orphan, still writing to
    the same log file - which is exactly why "Stoppen" previously appeared
    to do nothing. `start_new_session=True` at spawn time (see start_job)
    puts both processes in one group, so `killpg` reaches both.
    """
    try:
        pgid = os.getpgid(proc.pid)
    except ProcessLookupError:
        return

    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        return

    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass


_TOTAL_RE = re.compile(r"Downloading (the first|\d+) \S+.*? to .*? \.\.\.")
_DOWNLOADED_RE = re.compile(r"^\S+ \S+ INFO\s+Downloaded ", re.MULTILINE)
_SKIPPED_RE = re.compile(r"already exists$", re.MULTILINE)

_LEVEL_RANK = {"DEBUG": 0, "INFO": 1, "ERROR": 2}
_LEVEL_LINE_RE = re.compile(r"^\S+ \S+ (DEBUG|INFO|ERROR)\s")


def filter_log_by_level(text: str, min_level: str) -> str:
    """Restricts a debug-captured log to what the user actually asked to
    see (settings.log_level is a display preference now, not passed to
    icloudpd - see build_args). Lines without a recognizable level prefix
    (our own header, tracebacks) inherit the previous line's visibility."""
    min_rank = _LEVEL_RANK.get((min_level or "").upper(), 1)
    out_lines = []
    keep_current = True
    for line in text.splitlines():
        match = _LEVEL_LINE_RE.match(line)
        if match:
            keep_current = _LEVEL_RANK[match.group(1)] >= min_rank
        if keep_current:
            out_lines.append(line)
    return "\n".join(out_lines)


def parse_progress(text: str, started_at: datetime) -> dict:
    """Extracts a best-effort "N of M processed / remaining / ETA" from
    icloudpd's own log output. `total` comes from its startup line
    ("Downloading <N> photos and videos to ... ..."); `processed` counts
    both actually-downloaded and already-existing (skipped) items, since
    both count against that total. Returns total=None when the startup
    line hasn't appeared yet (e.g. still authenticating)."""
    total_match = _TOTAL_RE.search(text)
    total = None
    if total_match:
        raw = total_match.group(1)
        total = 1 if raw == "the first" else int(raw)

    processed = len(_DOWNLOADED_RE.findall(text)) + len(_SKIPPED_RE.findall(text))
    remaining = max(total - processed, 0) if total is not None else None

    eta_seconds = None
    if remaining and processed > 0:
        elapsed = (datetime.utcnow() - started_at).total_seconds()
        if elapsed > 0:
            eta_seconds = int((elapsed / processed) * remaining)

    return {
        "total": total,
        "processed": processed,
        "remaining": remaining,
        "eta_seconds": eta_seconds,
    }


def read_full_log(log_file: str) -> str:
    """Reads the whole log, untruncated - needed for parse_progress()
    since the startup line with the total count is near the beginning,
    which tail_log()'s truncation would otherwise lose on long runs."""
    path = Path(log_file)
    if not path.exists():
        return ""
    return path.read_bytes().decode("utf-8", errors="replace")


def tail_log(log_file: str, max_bytes: int = 40000) -> str:
    path = Path(log_file)
    if not path.exists():
        return ""
    data = path.read_bytes()
    if len(data) > max_bytes:
        data = data[-max_bytes:]
    return data.decode("utf-8", errors="replace")


def _watch_process(app, account_id: int, run_log_id: int, proc: subprocess.Popen):
    exit_code = proc.wait()
    with app.app_context():
        run_log = db.session.get(RunLog, run_log_id)
        if run_log:
            run_log.finished_at = datetime.utcnow()
            run_log.exit_code = exit_code
            if run_log.status == "running":
                run_log.status = "success" if exit_code == 0 else "failed"
            db.session.commit()
    with _lock:
        _running.pop(account_id, None)


def start_job(app, account, settings, mode: str = "once") -> RunLog:
    if is_running(account.id):
        raise RuntimeError("Es läuft bereits ein Job für dieses Konto.")

    Config.ensure_dirs()
    args = build_args(account, settings, mode)
    log_name = f"{datetime.utcnow():%Y%m%d_%H%M%S}_{mode}.log"
    log_path = Config.LOG_DIR / log_name

    run_log = RunLog(
        account_id=account.id,
        mode=mode,
        status="running",
        log_file=str(log_path),
        started_at=datetime.utcnow(),
    )
    db.session.add(run_log)
    db.session.commit()

    log_file_handle = open(log_path, "wb", buffering=0)
    safe_args = []
    skip_next = False
    for a in args:
        if skip_next:
            safe_args.append("********")
            skip_next = False
            continue
        safe_args.append(a)
        if a == "--password":
            skip_next = True
    log_file_handle.write((" ".join(safe_args) + "\n\n").encode())

    try:
        proc = subprocess.Popen(
            args,
            stdout=log_file_handle,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            # New session/process group so stop_job() can kill the whole
            # tree (icloudpd's wrapper + its actual worker child), not just
            # the directly spawned wrapper process.
            start_new_session=True,
        )
    except FileNotFoundError as exc:
        run_log.status = "failed"
        run_log.finished_at = datetime.utcnow()
        db.session.commit()
        log_file_handle.close()
        raise RuntimeError(f"icloudpd nicht gefunden: {exc}") from exc

    run_log.pid = proc.pid
    db.session.commit()

    with _lock:
        _running[account.id] = {"proc": proc, "run_log_id": run_log.id}

    watcher = threading.Thread(
        target=_watch_process, args=(app, account.id, run_log.id, proc), daemon=True
    )
    watcher.start()

    return run_log
