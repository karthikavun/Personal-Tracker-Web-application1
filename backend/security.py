import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from jose import jwt

from app.config import get_settings


class PasswordHasher:
    _algorithm = "pbkdf2_sha256"
    _iterations = 260_000
    _salt_bytes = 16

    def hash(self, password: str) -> str:
        salt = secrets.token_hex(self._salt_bytes)
        digest = self._digest(password, salt)
        return f"{self._algorithm}${self._iterations}${salt}${digest}"

    def verify(self, password: str, hashed_password: str) -> bool:
        algorithm, iterations, salt, digest = hashed_password.split("$", 3)
        expected = hashlib.pbkdf2_hmac(algorithm.removeprefix("pbkdf2_"), password.encode(), salt.encode(), int(iterations))
        return secrets.compare_digest(expected.hex(), digest)

    def _digest(self, password: str, salt: str) -> str:
        return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), self._iterations).hex()


class TokenManager:
    def __init__(self) -> None:
        self._settings = get_settings()

    def create_access_token(self, subject: str) -> str:
        expires_delta = timedelta(minutes=self._settings.access_token_expire_minutes)
        payload = {"sub": subject, "exp": datetime.now(UTC) + expires_delta}
        return jwt.encode(payload, self._settings.secret_key, algorithm=self._settings.algorithm)

    def decode_subject(self, token: str) -> str:
        payload = jwt.decode(token, self._settings.secret_key, algorithms=[self._settings.algorithm])
        return str(payload["sub"])
