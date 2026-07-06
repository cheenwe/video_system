"""认证相关 schema"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, field_validator

from src.core.input_security import assert_no_sql_probe, strip_control_chars


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=5, max_length=128)

    @field_validator("username")
    @classmethod
    def _username_safe(cls, v: str) -> str:
        s = strip_control_chars(v.strip())
        assert_no_sql_probe(s, label="用户名")
        return s


class LoginResponse(BaseModel):
    token: str
    username: str
    is_admin: bool
    user_id: int


class MeResponse(BaseModel):
    user_id: int
    username: str
    is_admin: bool
    real_name: Optional[str] = None
    timezone: str = "UTC"
