from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from .database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), nullable=False, unique=True, index=True)
    email = Column(String(255), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login_at = Column(DateTime)
    is_active = Column(Boolean, default=True)

    quotes = relationship("Quote", back_populates="owner", cascade="all, delete-orphan")
    reactions = relationship("UserQuoteReaction", back_populates="user", cascade="all, delete-orphan")


class Quote(Base):
    __tablename__ = "quotes"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    content = Column(Text, nullable=False)
    source = Column(String(255))
    author = Column(String(255))
    explanation = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner = relationship("User", back_populates="quotes")
    reactions = relationship("UserQuoteReaction", back_populates="quote", cascade="all, delete-orphan")


class UserQuoteReaction(Base):
    __tablename__ = "user_quote_reactions"
    __table_args__ = (
        UniqueConstraint("user_id", "quote_id", "reaction_type", name="uq_reaction"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    quote_id = Column(Integer, ForeignKey("quotes.id"), nullable=False)
    reaction_type = Column(String(20), nullable=False)  # like or collect
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="reactions")
    quote = relationship("Quote", back_populates="reactions")
