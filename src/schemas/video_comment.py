"""视频评论 Schema"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class VideoCommentCreateBody(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)
    anonymous: bool = False
    display_name: Optional[str] = Field(default=None, max_length=32)
