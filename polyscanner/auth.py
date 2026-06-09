from __future__ import annotations

import base64
import os
import time
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from dotenv import load_dotenv


@dataclass(frozen=True)
class KalshiCredentials:
    access_key_id: str
    private_key_path: Path

    @classmethod
    def from_env(cls) -> "KalshiCredentials | None":
        load_dotenv()
        access_key_id = os.getenv("KALSHI_ACCESS_KEY_ID", "").strip()
        private_key_path = os.getenv("KALSHI_PRIVATE_KEY_PATH", "").strip()
        if not access_key_id or not private_key_path:
            return None
        return cls(access_key_id, Path(private_key_path).expanduser())

    def validate(self) -> None:
        if not self.private_key_path.is_file():
            raise FileNotFoundError(
                f"Kalshi private key not found at {self.private_key_path}"
            )


class KalshiRequestSigner:
    def __init__(self, credentials: KalshiCredentials) -> None:
        credentials.validate()
        self.credentials = credentials
        with credentials.private_key_path.open("rb") as key_file:
            private_key = serialization.load_pem_private_key(
                key_file.read(),
                password=None,
            )
        if not isinstance(private_key, rsa.RSAPrivateKey):
            raise ValueError("Kalshi private key must be an RSA private key.")
        self.private_key = private_key

    def headers(
        self,
        method: str,
        path: str,
        timestamp_ms: int | None = None,
    ) -> dict[str, str]:
        timestamp = str(timestamp_ms or int(time.time() * 1000))
        signed_path = path.split("?", 1)[0]
        message = f"{timestamp}{method.upper()}{signed_path}".encode()
        signature = self.private_key.sign(
            message,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.DIGEST_LENGTH,
            ),
            hashes.SHA256(),
        )
        return {
            "KALSHI-ACCESS-KEY": self.credentials.access_key_id,
            "KALSHI-ACCESS-TIMESTAMP": timestamp,
            "KALSHI-ACCESS-SIGNATURE": base64.b64encode(signature).decode(),
        }
