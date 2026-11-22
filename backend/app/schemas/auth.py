"""Pydantic schemas for authentication and profile endpoints."""

from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


def _normalise_email(value: str) -> str:
    email = (value or "").strip().lower()
    if not EMAIL_RE.match(email) or len(email) > 255:
        raise ValueError("Enter a valid email address.")
    return email


def _validate_password(value: str) -> str:
    if len(value) < 8:
        raise ValueError("Password must be at least 8 characters long.")
    if len(value) > 72:
        raise ValueError("Password must be 72 characters or fewer.")
    if not re.search(r"[A-Za-z]", value) or not re.search(r"\d", value):
        raise ValueError("Password must contain at least one letter and one number.")
    return value


class UserRegister(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        return _normalise_email(value)

    @field_validator("password")
    @classmethod
    def _password(cls, value: str) -> str:
        return _validate_password(value)

    @field_validator("name")
    @classmethod
    def _clean_name(cls, value: str) -> str:
        name = " ".join((value or "").split())
        if len(name) < 2:
            raise ValueError("Enter your name (at least 2 characters).")
        return name


class UserLogin(BaseModel):
    email: str
    password: str = Field(min_length=1, max_length=200)

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        return _normalise_email(value)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    preferences: dict | None = None
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    preferences: dict | None = None

    @field_validator("name")
    @classmethod
    def _clean_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        name = " ".join(value.split())
        if len(name) < 2:
            raise ValueError("Enter your name (at least 2 characters).")
        return name


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _new_password(cls, value: str) -> str:
        return _validate_password(value)


class MessageResponse(BaseModel):
    message: str
