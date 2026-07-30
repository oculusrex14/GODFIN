from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class PinSet(BaseModel):
    pin: str = Field(..., min_length=4, max_length=6, pattern=r"^\d{4,6}$")


class PinVerify(BaseModel):
    # Verification remains compatible with PINs created before new PINs were
    # restricted to six digits.
    pin: str = Field(..., min_length=4, max_length=8, pattern=r"^\d{4,8}$")


class AuthStatusResponse(BaseModel):
    is_first_run: bool
    pin_length: Optional[int] = None


class PinChange(BaseModel):
    current_pin: str = Field(..., min_length=4, max_length=8, pattern=r"^\d{4,8}$")
    new_pin: str = Field(..., min_length=4, max_length=6, pattern=r"^\d{4,6}$")


class AuthResponse(BaseModel):
    authenticated: bool
    token: Optional[str] = None
