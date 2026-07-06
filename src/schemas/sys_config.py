"""系统配置 schema"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class SysConfigBase(BaseModel):
    category: str = Field(..., min_length=1, max_length=64)
    code: str = Field(..., min_length=1, max_length=128)
    value: Optional[str] = None
    status: str = "active"
    version: Optional[str] = None


class SysConfigCreate(SysConfigBase):
    pass


class SysConfigUpdate(BaseModel):
    value: Optional[str] = None
    status: Optional[str] = None
    version: Optional[str] = None


class SysConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category: str
    code: str
    value: Optional[str] = None
    status: str
    version: Optional[str] = None
    updated_by: Optional[int] = None
    updated_at: Optional[datetime] = None
