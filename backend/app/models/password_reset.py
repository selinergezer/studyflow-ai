from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime, timezone

from app.db.database import Base


class PasswordReset(Base):

    __tablename__ = "password_resets"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False
    )

    token_hash = Column(
        String,
        nullable=False
    )

    expires_at = Column(
        DateTime(timezone=True),
        nullable=False
    )

    used = Column(
        Boolean,
        default=False,
        nullable=False
    )

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    user = relationship(
        "User"
    )