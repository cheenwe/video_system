"""通用 schema"""
from __future__ import annotations

from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel, Field, field_validator

from src.core.input_security import assert_no_sql_probe, strip_control_chars

T = TypeVar("T")


class PageQuery(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=200)
    keyword: Optional[str] = Field(default=None, max_length=100)

    @field_validator("keyword")
    @classmethod
    def _keyword_safe(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        s = strip_control_chars(v.strip())
        if not s:
            return None
        assert_no_sql_probe(s, label="搜索关键词")
        return s


class PageData(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    page_size: int


class IdRequest(BaseModel):
    id: int


class StatusUpdate(BaseModel):
    status: str
