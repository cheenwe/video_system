"""系统日志 schema"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class SysLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    ip: Optional[str] = None
    user_id: Optional[int] = None
    username: Optional[str] = None
    tag: str
    result: str
    action: str
    request_id: Optional[str] = None
    remark: Optional[str] = None
