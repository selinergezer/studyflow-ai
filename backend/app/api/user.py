from fastapi.security import OAuth2PasswordRequestForm
from fastapi import HTTPException

from app.core.security import (
    verify_password,
    create_access_token,
    get_current_user
)

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.user import User
from app.schemas.user import UserCreate, ChangePassword
from app.core.security import hash_password

from sqlalchemy import select
from app.services.notification_service import create_notification
from app.services.email_verification_service import create_verification_code
from app.services.email_service import send_verification_email

from datetime import datetime, timezone

from app.models.email_verification import EmailVerification
from app.schemas.email_verification import EmailVerificationRequest
from app.services.email_verification_service import create_verification_code, pwd_context

from app.schemas.email_verification import ResendVerificationRequest
from app.services.email_verification_service import create_verification_code
from app.services.email_service import send_verification_email


router = APIRouter(
    prefix="/users",
    tags=["Users"]
)


@router.get("/")
def get_users():
    return {
        "message": "Users endpoint is working!"
    }


@router.post("/")
def create_user(
    user: UserCreate,
    db: Session = Depends(get_db)
):
    # Aynı email daha önce kayıtlı mı?
    existing_user = (
        db.query(User)
        .filter(User.email == user.email)
        .first()
    )

    if existing_user is not None:
        raise HTTPException(
            status_code=400,
            detail="Bu email adresi zaten kayıtlı."
        )

    # Kullanıcı oluştur
    hashed_password = hash_password(user.password)

    new_user = User(
        username=user.username,
        email=user.email,
        password=hashed_password,
        email_verified=False
    )

    db.add(new_user)
    db.flush()

    # Doğrulama kodu oluştur
    verification_code, verification = create_verification_code(
        db,
        new_user.id
    )

    db.commit()
    db.refresh(new_user)

    # Doğrulama mailini gönder
    send_verification_email(
        new_user.email,
        verification_code
    )

    return {
        "message": "Kullanıcı oluşturuldu. E-posta doğrulama kodu gönderildi.",
        "id": new_user.id,
        "username": new_user.username,
        "email": new_user.email,
        "email_verified": new_user.email_verified
    }

@router.post("/verify-email")
def verify_email(
    data: EmailVerificationRequest,
    db: Session = Depends(get_db)
):
    user = (
        db.query(User)
        .filter(User.email == data.email)
        .first()
    )

    if user is None:
        raise HTTPException(
            status_code=404,
            detail="Kullanıcı bulunamadı."
        )

    if user.email_verified:
        return {
            "message": "E-posta zaten doğrulanmış."
        }

    verification = (
        db.query(EmailVerification)
        .filter(
            EmailVerification.user_id == user.id,
            EmailVerification.verified == False
        )
        .order_by(
            EmailVerification.created_at.desc()
        )
        .first()
    )

    if verification is None:
        raise HTTPException(
            status_code=400,
            detail="Geçerli bir doğrulama kodu bulunamadı."
        )

    now = datetime.now(timezone.utc)

    if verification.expires_at < now:
        raise HTTPException(
            status_code=400,
            detail="Doğrulama kodunun süresi dolmuş."
        )

    if not pwd_context.verify(
        data.code,
        verification.code_hash
    ):
        raise HTTPException(
            status_code=400,
            detail="Doğrulama kodu hatalı."
        )

    verification.verified = True
    user.email_verified = True

    db.commit()

    return {
        "message": "E-posta başarıyla doğrulandı.",
        "email": user.email,
        "email_verified": True
    }

@router.post("/resend-verification")
def resend_verification(
    data: ResendVerificationRequest,
    db: Session = Depends(get_db)
):
    user = (
        db.query(User)
        .filter(User.email == data.email)
        .first()
    )

    if user is None:
        raise HTTPException(
            status_code=404,
            detail="Kullanıcı bulunamadı."
        )

    if user.email_verified:
        return {
            "message": "E-posta adresi zaten doğrulanmış."
        }

    verification_code, verification = create_verification_code(
        db,
        user.id
    )

    db.commit()

    send_verification_email(
        user.email,
        verification_code
    )

    return {
        "message": "Yeni doğrulama kodu gönderildi.",
        "email": user.email
    }

@router.post("/login")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):

    db_user = db.query(User).filter(
        User.email == form_data.username
    ).first()

    if db_user is None:
        raise HTTPException(
            status_code=401,
            detail="Email veya şifre hatalı."
        )

    if not verify_password(form_data.password, db_user.password):
        raise HTTPException(
            status_code=401,
            detail="Email veya şifre hatalı."
        )

    if not db_user.email_verified:
        raise HTTPException(
        status_code=403,
        detail="Giriş yapmadan önce e-posta adresinizi doğrulamanız gerekiyor."
    )

    token = create_access_token(
        data={
            "sub": db_user.email
        }
    )

    return {
        "access_token": token,
        "token_type": "bearer"
    }

@router.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email
    }

@router.post("/change-password")
def change_password(
    data: ChangePassword,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not verify_password(
        data.current_password,
        current_user.password
    ):
        raise HTTPException(
            status_code=400,
            detail="Mevcut şifreniz hatalı."
        )

    if data.current_password == data.new_password:
        raise HTTPException(
            status_code=400,
            detail="Yeni şifre mevcut şifrenizden farklı olmalıdır."
        )

    current_user.password = hash_password(data.new_password)

    db.commit()

    return {
        "message": "Şifreniz başarıyla değiştirildi."
    }
