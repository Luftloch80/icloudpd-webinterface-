import os
from pathlib import Path


class Config:
    DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
    CONFIG_DIR = Path(os.environ.get("CONFIG_DIR", str(DATA_DIR / "config")))
    DOWNLOAD_DIR = Path(os.environ.get("DOWNLOAD_DIR", str(DATA_DIR / "photos")))
    COOKIE_DIR = Path(os.environ.get("COOKIE_DIR", str(CONFIG_DIR / "cookies")))
    LOG_DIR = Path(os.environ.get("LOG_DIR", str(CONFIG_DIR / "logs")))
    DB_PATH = CONFIG_DIR / "app.db"

    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{DB_PATH}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    SECRET_KEY = os.environ.get("SECRET_KEY")

    # Encryption key for storing the Apple ID password at rest. If not
    # provided via env, a key file is generated in CONFIG_DIR on first run.
    FERNET_KEY = os.environ.get("FERNET_KEY")
    FERNET_KEY_FILE = CONFIG_DIR / "secret.key"

    # Credentials for the web interface itself (separate from the Apple ID).
    # Falls back to an auto-generated admin password on first run if unset.
    APP_USERNAME = os.environ.get("APP_USERNAME", "admin")
    APP_PASSWORD = os.environ.get("APP_PASSWORD")
    APP_PASSWORD_FILE = CONFIG_DIR / "admin_password.txt"

    ICLOUDPD_BIN = os.environ.get("ICLOUDPD_BIN", "icloudpd")

    # Dropbox App credentials (identify this app to Dropbox, shared across
    # whoever uses this deployment - not a per-user secret). Create a
    # Scoped App at https://www.dropbox.com/developers/apps to get these.
    DROPBOX_APP_KEY = os.environ.get("DROPBOX_APP_KEY")
    DROPBOX_APP_SECRET = os.environ.get("DROPBOX_APP_SECRET")

    @classmethod
    def ensure_dirs(cls):
        for d in (cls.DATA_DIR, cls.CONFIG_DIR, cls.DOWNLOAD_DIR, cls.COOKIE_DIR, cls.LOG_DIR):
            d.mkdir(parents=True, exist_ok=True)
