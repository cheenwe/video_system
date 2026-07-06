"""用户 schema"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator


def validate_iana_timezone(v: Optional[str]) -> str:
    """校验 IANA 时区名（如 Asia/Shanghai、UTC）。"""
    s = (v or "UTC").strip() or "UTC"
    try:
        ZoneInfo(s)
    except Exception as e:
        raise ValueError("无效的时区，请使用 IANA 名称（如 Asia/Shanghai、UTC）") from e
    return s


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=5, max_length=128)
    role: str = Field("user", pattern="^(admin|user)$")
    real_name: Optional[str] = None
    timezone: str = Field("UTC", max_length=64)

    @field_validator("timezone", mode="before")
    @classmethod
    def _tz_create(cls, v):
        return validate_iana_timezone(v if v is not None else "UTC")


class UserUpdate(BaseModel):
    username: Optional[str] = Field(None, min_length=3, max_length=64)
    role: Optional[str] = Field(None, pattern="^(admin|user)$")
    real_name: Optional[str] = None
    new_password: Optional[str] = Field(None, min_length=5, max_length=128)
    timezone: Optional[str] = Field(None, max_length=64)

    @field_validator("timezone")
    @classmethod
    def _tz_update(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        s = v.strip()
        if not s:
            return None
        return validate_iana_timezone(s)


class UserSelfProfileUpdate(BaseModel):
    """当前登录用户可改的个人信息（不含角色、用户名）。"""

    real_name: Optional[str] = Field(None, max_length=64)
    timezone: Optional[str] = Field(None, max_length=64)

    @field_validator("timezone")
    @classmethod
    def _tz_self(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        s = v.strip()
        if not s:
            return None
        return validate_iana_timezone(s)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    role: str
    disabled: int
    real_name: Optional[str] = None
    timezone: str = "UTC"
    created_at: Optional[datetime] = None

    @field_validator("timezone", mode="before")
    @classmethod
    def _tz_out(cls, v):
        if v is None or (isinstance(v, str) and not v.strip()):
            return "UTC"
        return str(v).strip()
