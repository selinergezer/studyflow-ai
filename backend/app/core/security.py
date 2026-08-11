from fastapi.security import OAuth2PasswordRequestForm

from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import jwt
from passlib.context import CryptContext

from app.core.config import settings

from jose import JWTError
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.user import User

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto"
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/users/login")


def hash_password(password: str):
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str):
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict):
    to_encode = data.copy()

    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )

    to_encode.update({"exp": expire})

    encoded_jwt = jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM
    )

    return encoded_jwt

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    credentials_exception = HTTPException(
        status_code=401,
        detail="Geçersiz kimlik bilgileri",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )

        subject: Optional[str] = payload.get("sub")

        if subject is None:
            raise credentials_exception

    except JWTError:
        raise credentials_exception

    # Yeni tokenlar değişmeyen kullanıcı ID'sini taşır. Daha önce verilmiş
    # e-posta tabanlı tokenlar geçiş sürecinde çalışmaya devam eder.
    try:
        user_id = int(subject)
    except (TypeError, ValueError):
        user = db.query(User).filter(User.email == subject).first()
    else:
        user = db.query(User).filter(User.id == user_id).first()

    if user is None:
        raise credentials_exception

    return user
