"""Interactive Apple ID login/2FA handled by driving the real `icloudpd`
binary (`--auth-only`, console password/MFA providers) as a subprocess.

Rather than reimplementing iCloud authentication against a separate
pyicloud client library (which risks producing session/cookie files that
the actually-installed icloudpd version can't read back), we let icloudpd
itself perform the login. This guarantees the cookie directory it writes
is exactly what later `icloudpd` sync runs expect.

`--auth-only` only creates/updates the session/cookie files; it prints any
password/MFA prompts to stdout and reads answers from stdin, so we bridge
that over a small buffered, pollable session object that the web routes
drive across multiple HTTP requests.
"""
import os
import secrets
import select
import signal
import subprocess
import threading
import time
from pathlib import Path

from app.config import Config

_lock = threading.Lock()
_sessions: dict[str, "AuthSession"] = {}


class LoginError(Exception):
    pass


class AuthSession:
    def __init__(self, proc: subprocess.Popen, apple_id: str, password: str, domain: str, cookie_dir: str):
        self.proc = proc
        self.apple_id = apple_id
        self.password = password
        self.domain = domain
        self.cookie_dir = cookie_dir
        self.buffer = ""
        self.returncode = None
        self._buf_lock = threading.Lock()
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def _read_loop(self):
        fd = self.proc.stdout.fileno()
        while True:
            ready, _, _ = select.select([fd], [], [], 0.5)
            if ready:
                try:
                    chunk = os.read(fd, 4096)
                except OSError:
                    break
                if not chunk:
                    break
                with self._buf_lock:
                    self.buffer += chunk.decode("utf-8", errors="replace")
            elif self.proc.poll() is not None:
                break
        self.returncode = self.proc.wait()

    def write_line(self, text: str):
        try:
            self.proc.stdin.write((text or "") + "\n")
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise LoginError(f"Konnte Eingabe nicht senden: {exc}") from exc

    def snapshot(self) -> dict:
        with self._buf_lock:
            buf = self.buffer
        done = self.returncode is not None
        # Heuristic: the process is very likely blocked waiting on stdin
        # when it's still running and hasn't produced new output for a
        # short while after already printing something.
        waiting = (not done) and bool(buf.strip())
        success = done and _has_session_files(self.cookie_dir)
        return {
            "buffer": buf,
            "done": done,
            "returncode": self.returncode,
            "waiting": waiting,
            "success": success,
        }

    def terminate(self):
        # icloudpd's own executable is a thin wrapper that runs the actual
        # worker as a further child via subprocess.call; killing only the
        # directly-spawned PID would leave that worker running as an
        # orphan. start_new_session=True at spawn time puts both in one
        # process group so killpg reaches both.
        if self.proc.poll() is None:
            try:
                os.killpg(os.getpgid(self.proc.pid), signal.SIGTERM)
            except ProcessLookupError:
                pass


def _cookie_dir_for(apple_id: str) -> str:
    Config.ensure_dirs()
    safe = "".join(c if c.isalnum() or c in "@._-" else "_" for c in apple_id)
    path = Config.COOKIE_DIR / safe
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def _has_session_files(cookie_dir: str) -> bool:
    """Whether icloudpd actually wrote a session/cookie file, i.e. whether
    authentication truly succeeded. icloudpd's `--auth-only` has been
    observed to exit with code 0 even on outright authentication failure
    (e.g. no network route to Apple), so the exit code alone cannot be
    trusted as a success signal."""
    try:
        return any(Path(cookie_dir).iterdir())
    except OSError:
        return False


def start_login(apple_id: str, password: str, china_mainland: bool = False) -> str:
    """Starts `icloudpd --auth-only` for the given credentials and returns a
    session token used to poll output / submit a 2FA code."""
    cookie_dir = _cookie_dir_for(apple_id)
    args = [
        Config.ICLOUDPD_BIN,
        "--auth-only",
        "--username", apple_id,
        "--password", password,
        "--cookie-directory", cookie_dir,
        "--password-provider", "parameter",
        "--mfa-provider", "console",
        "--no-progress-bar",
    ]
    if china_mainland:
        args += ["--domain", "cn"]

    try:
        proc = subprocess.Popen(
            args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
    except FileNotFoundError as exc:
        raise LoginError(f"icloudpd nicht gefunden: {exc}") from exc

    session = AuthSession(
        proc, apple_id, password, "cn" if china_mainland else "com", cookie_dir
    )
    token = secrets.token_urlsafe(24)
    with _lock:
        _sessions[token] = session
    return token


def wait_briefly(token: str, seconds: float = 4.0) -> dict:
    """Polls a freshly started session for a short window so a fast
    success/failure (e.g. wrong password, or an already-trusted session
    needing no 2FA at all) can be reported immediately instead of always
    bouncing the user to a 2FA screen."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        snap = get_status(token)
        if snap["done"]:
            return snap
        time.sleep(0.25)
    return get_status(token)


def get_status(token: str) -> dict:
    with _lock:
        session = _sessions.get(token)
    if session is None:
        raise LoginError("Anmeldesitzung abgelaufen. Bitte erneut einloggen.")
    return session.snapshot()


def submit_code(token: str, code: str) -> None:
    with _lock:
        session = _sessions.get(token)
    if session is None:
        raise LoginError("Anmeldesitzung abgelaufen. Bitte erneut einloggen.")
    session.write_line(code)


def get_credentials(token: str) -> tuple[str, str, str] | None:
    with _lock:
        session = _sessions.get(token)
    if session is None:
        return None
    return session.apple_id, session.password, session.domain


def cleanup(token: str) -> None:
    with _lock:
        session = _sessions.pop(token, None)
    if session:
        session.terminate()
