"""密码相关 schema"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(..., min_length=5, max_length=128)
    new_password: str = Field(..., min_length=5, max_length=128)


class ResetPasswordRequest(BaseModel):
    new_password: str = Field(..., min_length=5, max_length=128)
