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
from app.schemas.user import UserCreate

from app.core.security import hash_password

from sqlalchemy import select

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
    hashed_password = hash_password(user.password)

    new_user = User(
    username=user.username,
    email=user.email,
    password=hashed_password
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {
        "message": "User created successfully",
        "id": new_user.id,
        "username": new_user.username,
        "email": new_user.email
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
