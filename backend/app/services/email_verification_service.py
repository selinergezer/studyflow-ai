import secrets
from datetime import datetime, timedelta, timezone

from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.models.email_verification import EmailVerification


pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto"
)


def generate_verification_code():
    return f"{secrets.randbelow(1000000):06d}"


def create_verification_code(
    db: Session,
    user_id: int
):
    # Kullanýcýnýn eski doðrulama kodlarýný geçersiz yap
    db.query(EmailVerification).filter(
        EmailVerification.user_id == user_id,
        EmailVerification.verified == False
    ).update(
        {
            EmailVerification.verified: True
        }
    )

    # Yeni 6 haneli kod oluþtur
    code = generate_verification_code()

    # Kodu hashle
    code_hash = pwd_context.hash(code)

    # 10 dakika geçerli
    expires_at = (
        datetime.now(timezone.utc)
        + timedelta(minutes=10)
    )

    verification = EmailVerification(
        user_id=user_id,
        code_hash=code_hash,
        expires_at=expires_at,
        verified=False
    )

    db.add(verification)
    db.flush()

    return code, verification
