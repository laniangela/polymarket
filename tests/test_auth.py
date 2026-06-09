import base64
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
)

from polyscanner.auth import KalshiCredentials, KalshiRequestSigner


def test_signer_uses_method_and_path_without_query(tmp_path: Path):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    key_path = tmp_path / "kalshi.pem"
    key_path.write_bytes(
        key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
    )
    signer = KalshiRequestSigner(KalshiCredentials("key-id", key_path))
    headers = signer.headers(
        "get",
        "/trade-api/v2/portfolio/orders?limit=5",
        timestamp_ms=1_700_000_000_000,
    )
    signature = base64.b64decode(headers["KALSHI-ACCESS-SIGNATURE"])
    key.public_key().verify(
        signature,
        b"1700000000000GET/trade-api/v2/portfolio/orders",
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.DIGEST_LENGTH,
        ),
        hashes.SHA256(),
    )
    assert headers["KALSHI-ACCESS-KEY"] == "key-id"
