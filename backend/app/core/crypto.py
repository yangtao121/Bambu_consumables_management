from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken


def _derive_fernet_key(secret: str) -> bytes:
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def encrypt_str(secret: str, plaintext: str) -> str:
    f = Fernet(_derive_fernet_key(secret))
    return f.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_str(secret: str, ciphertext: str) -> str:
    f = Fernet(_derive_fernet_key(secret))
    try:
        return f.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken as e:
        raise ValueError("invalid ciphertext") from e


