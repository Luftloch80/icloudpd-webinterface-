import base64
import os

from cryptography.fernet import Fernet

from app.config import Config

_fernet = None


def _load_or_create_key() -> bytes:
    if Config.FERNET_KEY:
        key = Config.FERNET_KEY.encode()
        # Allow either a raw 32-byte secret or an already-encoded Fernet key.
        try:
            Fernet(key)
            return key
        except Exception:
            return base64.urlsafe_b64encode(key.ljust(32, b"0")[:32])

    Config.ensure_dirs()
    key_file = Config.FERNET_KEY_FILE
    if key_file.exists():
        return key_file.read_bytes().strip()

    key = Fernet.generate_key()
    key_file.write_bytes(key)
    os.chmod(key_file, 0o600)
    return key


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        _fernet = Fernet(_load_or_create_key())
    return _fernet


def encrypt(value: str) -> bytes:
    return _get_fernet().encrypt(value.encode())


def decrypt(value: bytes) -> str:
    return _get_fernet().decrypt(value).decode()
