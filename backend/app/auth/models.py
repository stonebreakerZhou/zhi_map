"""ORM models for the auth subsystem.

Defined here for typing/relations; tables are created by alembic migration
0007_email_auth.py so we never have to manage DDL from Python.
"""
from __future__ import annotations
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from ..db import Base


class EmailCredential(Base):
    __tablename__ = "auth_email_credentials"
    user_id = Column(String, ForeignKey("users.id"), primary_key=True)
    email = Column(String, nullable=False, unique=True)
    password_hash = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)


class EmailVerification(Base):
    __tablename__ = "auth_email_verifications"
    id = Column(String, primary_key=True)
    email = Column(String, nullable=False)
    code_hash = Column(String, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    attempts = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False)