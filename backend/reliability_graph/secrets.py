import base64
import hashlib
import os
import secrets
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet


class KeyVault:
    def __init__(self, data_dir: Path, master_secret: Optional[str] = None) -> None:
        self.data_dir = data_dir
        self.master_secret = master_secret or self._load_or_create_local_secret()
        key = base64.urlsafe_b64encode(hashlib.sha256(self.master_secret.encode("utf-8")).digest())
        self.fernet = Fernet(key)

    def encrypt(self, value: str) -> str:
        return self.fernet.encrypt(value.encode("utf-8")).decode("utf-8")

    def decrypt(self, token: str) -> str:
        return self.fernet.decrypt(token.encode("utf-8")).decode("utf-8")

    def fingerprint(self, value: str) -> str:
        clean = value.strip()
        if len(clean) <= 8:
            return "..." + clean[-4:]
        prefix = clean[: min(4, len(clean) - 4)]
        return prefix + "..." + clean[-4:]

    def _load_or_create_local_secret(self) -> str:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        path = self.data_dir / "local_secret.key"
        if path.exists():
            return path.read_text(encoding="utf-8").strip()

        value = secrets.token_urlsafe(48)
        path.write_text(value, encoding="utf-8")
        try:
            os.chmod(str(path), 0o600)
        except OSError:
            pass
        return value
