from fastapi.security import OAuth2PasswordRequestForm
from fastapi import HTTPException, status

from app.core.security import (
    verify_password,
    create_access_token,
    get_current_user
)

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.db.database import get_db
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate

from app.core.security import hash_password

from sqlalchemy import func

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
def create_user(user: UserCreate, db: Session = Depends(get_db)):
    email = str(user.email).strip().lower()
    if db.query(User).filter(func.lower(User.email) == email).first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bu e-posta adresi zaten kullanımda.",
        )
    if db.query(User).filter(User.username == user.username).first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bu kullanıcı adı zaten kullanımda.",
        )

    hashed_password = hash_password(user.password)

    new_user = User(
        username=user.username,
        email=email,
        password=hashed_password,
    )

    db.add(new_user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Kullanıcı adı veya e-posta adresi zaten kullanımda.",
        )
    db.refresh(new_user)

    return {
        "message": "Kullanıcı başarıyla oluşturuldu.",
        "id": new_user.id,
        "username": new_user.username,
        "email": new_user.email,
    }

@router.post("/login")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):

    db_user = db.query(User).filter(
        func.lower(User.email) == form_data.username.strip().lower()
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

    token = create_access_token(
        data={
            "sub": str(db_user.id)
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


@router.put("/me")
def update_me(
    profile: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    email = str(profile.email).strip().lower()

    email_owner = (
        db.query(User)
        .filter(
            func.lower(User.email) == email,
            User.id != current_user.id,
        )
        .first()
    )
    if email_owner is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bu e-posta adresi başka bir kullanıcı tarafından kullanılıyor.",
        )

    username_owner = (
        db.query(User)
        .filter(
            User.username == profile.username,
            User.id != current_user.id,
        )
        .first()
    )
    if username_owner is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bu kullanıcı adı başka bir kullanıcı tarafından kullanılıyor.",
        )

    current_user.username = profile.username
    current_user.email = email
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Kullanıcı adı veya e-posta adresi zaten kullanılıyor.",
        )
    db.refresh(current_user)

    return {
        "message": "Profil başarıyla güncellendi.",
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
    }
