from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from app.db.session import Base



class Form(Base):
    __tablename__ = "forms"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    schema_json = Column(JSON, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    is_public = Column(Boolean, default=True, nullable=False)
    source_type = Column(String(50), default="manual", nullable=False)
    original_document_path = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


    # Relationships
    user = relationship("User", back_populates="forms")
    submissions = relationship(
        "Submission",
        back_populates="form",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    drafts = relationship(
        "Draft",
        back_populates="form",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    conversation_sessions = relationship(
        "ConversationSession",
        back_populates="form",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
