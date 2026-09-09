import hmac
import os

from flask_login import UserMixin

from app.config import Config


class AdminUser(UserMixin):
    """Single, fixed user representing web-interface access."""

    id = "admin"

    def get_id(self):
        return self.id


def _resolve_app_password() -> str:
    """Return the configured admin password, generating and persisting a
    random one on first run if neither APP_PASSWORD nor a saved password
    file exists yet."""
    if Config.APP_PASSWORD:
        return Config.APP_PASSWORD

    Config.ensure_dirs()
    pw_file = Config.APP_PASSWORD_FILE
    if pw_file.exists():
        return pw_file.read_text().strip()

    generated = os.urandom(9).hex()
    pw_file.write_text(generated)
    os.chmod(pw_file, 0o600)
    return generated


def verify_app_credentials(username: str, password: str) -> bool:
    expected_user = Config.APP_USERNAME
    expected_pass = _resolve_app_password()
    return hmac.compare_digest(username or "", expected_user) and hmac.compare_digest(
        password or "", expected_pass
    )


def load_user(user_id: str):
    if user_id == AdminUser.id:
        return AdminUser()
    return None
