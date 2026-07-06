"""视频分类与专辑 Schema"""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

VisibilityType = Literal["public", "private"]


class VideoCategoryBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    description: str = Field(default="", max_length=500)
    sort_order: int = 0


class VideoCategoryUpdateBody(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=64)
    description: Optional[str] = Field(default=None, max_length=500)
    sort_order: Optional[int] = None


class VideoAlbumBody(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    visibility: VisibilityType = "public"
    sort_order: int = 0


class VideoAlbumUpdateBody(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=5000)
    visibility: Optional[VisibilityType] = None
    sort_order: Optional[int] = None


class VideoAlbumItemBody(BaseModel):
    video_id: int = Field(..., gt=0)
    sort_order: int = 0


class VideoCategoryEnsureBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)


class VideoAlbumEnsureBody(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    visibility: VisibilityType = "public"
