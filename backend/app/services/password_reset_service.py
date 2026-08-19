import secrets
import hashlib

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.password_reset import PasswordReset


RESET_TOKEN_EXPIRE_MINUTES = 30


def create_password_reset_token(
    db: Session,
    user_id: int
):
    # Kullanıcının eski ve kullanılmamış tokenlarını geçersiz yap
    db.query(PasswordReset).filter(
        PasswordReset.user_id == user_id,
        PasswordReset.used == False
    ).update(
        {
            PasswordReset.used: True
        }
    )

    # Güçlü rastgele token üret
    token = secrets.token_urlsafe(32)

    # Veritabanına token'ın kendisini değil hash'ini kaydet
    token_hash = hashlib.sha256(
        token.encode("utf-8")
    ).hexdigest()

    expires_at = (
        datetime.now(timezone.utc)
        + timedelta(
            minutes=RESET_TOKEN_EXPIRE_MINUTES
        )
    )

    reset = PasswordReset(
        user_id=user_id,
        token_hash=token_hash,
        expires_at=expires_at,
        used=False
    )

    db.add(reset)
    db.flush()

    return token, reset


def hash_reset_token(token: str) -> str:
    return hashlib.sha256(
        token.encode("utf-8")
    ).hexdigest()