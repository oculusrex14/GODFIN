from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class PinSet(BaseModel):
    pin: str = Field(..., min_length=4, max_length=6, pattern=r"^\d{4,6}$")


class PinVerify(BaseModel):
    pin: str = Field(..., min_length=4, max_length=6)


class AuthStatusResponse(BaseModel):
    is_first_run: bool


class PinChange(BaseModel):
    current_pin: str = Field(..., min_length=4, max_length=6, pattern=r"^\d{4,6}$")
    new_pin: str = Field(..., min_length=4, max_length=6, pattern=r"^\d{4,6}$")


class AuthResponse(BaseModel):
    authenticated: bool
    token: Optional[str] = None
