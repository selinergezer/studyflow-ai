from pydantic import BaseModel, EmailStr, field_validator


class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str

    @field_validator("username")
    @classmethod
    def validate_create_username(cls, value: str) -> str:
        username = value.strip()
        if not username:
            raise ValueError("Kullanıcı adı boş olamaz.")
        return username

class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserUpdate(BaseModel):
    username: str
    email: EmailStr

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        username = value.strip()
        if not username:
            raise ValueError("Kullanıcı adı boş olamaz.")
        return username
