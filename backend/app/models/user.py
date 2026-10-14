from datetime import datetime
from enum import Enum
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.orm import relationship, validates
from app.db.session import Base


class UserRole(str, Enum):
    USER = "USER"
    ADMIN = "ADMIN"
    SUPER_ADMIN = "SUPER_ADMIN"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    role = Column(String(50), default="USER", nullable=False)
    title = Column(String(100), nullable=True)
    avatar = Column(String(10), default="U", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    token_version = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    forms = relationship("Form", back_populates="user", cascade="all, delete-orphan")
    drafts = relationship("Draft", back_populates="user", cascade="all, delete-orphan")
    submissions = relationship("Submission", back_populates="user")

    def __init__(self, **kwargs):
        role_val = kwargs.get("role", "USER")
        if role_val:
            normalized = str(role_val).strip().upper()
            if normalized in ("ADMIN", "SUPER_ADMIN"):
                kwargs["role"] = normalized
            elif normalized == "USER":
                kwargs["role"] = "USER"
            else:
                # Custom job title like "Product Lead", "Manager", "Engineer"
                if not kwargs.get("title"):
                    kwargs["title"] = str(role_val).strip()
                kwargs["role"] = "USER"
        else:
            kwargs["role"] = "USER"
        super().__init__(**kwargs)

    @validates("role")
    def validate_role(self, key, value):
        if not value:
            return "USER"
        normalized = str(value).strip().upper()
        if normalized in ("ADMIN", "SUPER_ADMIN"):
            return normalized
        if normalized == "USER":
            return "USER"
        # If legacy job title, preserve in title if not set
        if not self.title:
            self.title = str(value).strip()
        return "USER"
