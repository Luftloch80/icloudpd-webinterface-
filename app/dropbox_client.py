"""Dropbox connection: OAuth2 (no-redirect flow) and client construction.

Uses `DropboxOAuth2FlowNoRedirect` rather than the usual redirect-based
OAuth flow: the redirect flow needs Dropbox to call back a publicly
reachable URL, which a self-hosted app behind a home router/NAT typically
doesn't have. The no-redirect flow instead has the user open an
authorize URL, approve access, and paste the resulting code back into
our own page - no inbound connectivity required.
"""
import secrets
import threading

import dropbox
from dropbox.oauth import DropboxOAuth2FlowNoRedirect

from app.config import Config
from app.crypto import decrypt, encrypt
from app.extensions import db
from app.models import DropboxConnection

_lock = threading.Lock()
_pending_flows: dict[str, DropboxOAuth2FlowNoRedirect] = {}


class DropboxConfigError(Exception):
    pass


class DropboxAuthError(Exception):
    pass


def app_configured() -> bool:
    return bool(Config.DROPBOX_APP_KEY and Config.DROPBOX_APP_SECRET)


def start_auth_flow() -> tuple[str, str]:
    """Returns (token, authorize_url). The token is later passed to
    finish_auth_flow() together with the code the user pastes in."""
    if not app_configured():
        raise DropboxConfigError(
            "DROPBOX_APP_KEY/DROPBOX_APP_SECRET sind nicht gesetzt."
        )

    flow = DropboxOAuth2FlowNoRedirect(
        Config.DROPBOX_APP_KEY,
        consumer_secret=Config.DROPBOX_APP_SECRET,
        token_access_type="offline",
    )
    authorize_url = flow.start()

    token = secrets.token_urlsafe(24)
    with _lock:
        _pending_flows[token] = flow
    return token, authorize_url


def finish_auth_flow(token: str, code: str) -> str:
    """Completes the flow, persists the refresh token, and returns the
    connected Dropbox account's email address."""
    with _lock:
        flow = _pending_flows.pop(token, None)
    if flow is None:
        raise DropboxAuthError("Anmeldesitzung abgelaufen. Bitte erneut versuchen.")

    try:
        result = flow.finish(code.strip())
    except Exception as exc:  # noqa: BLE001
        raise DropboxAuthError(f"Code wurde abgelehnt: {exc}") from exc

    dbx = dropbox.Dropbox(oauth2_access_token=result.access_token)
    try:
        account = dbx.users_get_current_account()
        email = account.email
    except Exception:  # noqa: BLE001
        email = None

    connection = DropboxConnection.query.first()
    if connection is None:
        connection = DropboxConnection(encrypted_refresh_token=encrypt(result.refresh_token))
        db.session.add(connection)
    else:
        connection.encrypted_refresh_token = encrypt(result.refresh_token)
    connection.account_email = email
    db.session.commit()

    return email or "verbunden"


def get_client() -> dropbox.Dropbox | None:
    """Returns a Dropbox client that auto-refreshes its access token, or
    None if no Dropbox account is connected."""
    if not app_configured():
        return None
    connection = DropboxConnection.query.first()
    if connection is None:
        return None
    refresh_token = decrypt(connection.encrypted_refresh_token)
    return dropbox.Dropbox(
        oauth2_refresh_token=refresh_token,
        app_key=Config.DROPBOX_APP_KEY,
        app_secret=Config.DROPBOX_APP_SECRET,
    )


def disconnect():
    DropboxConnection.query.delete()
    db.session.commit()
