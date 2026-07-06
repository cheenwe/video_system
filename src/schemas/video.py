"""视频相关 Schema"""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

VisibilityType = Literal["public", "private"]


class VideoUploadInitBody(BaseModel):
    filename: str = Field(..., min_length=1, max_length=255)
    file_size: int = Field(..., gt=0)
    mime_type: str = Field(default="application/octet-stream", max_length=128)
    chunk_size: Optional[int] = Field(default=None, gt=0)


class VideoUploadInitOut(BaseModel):
    upload_id: str
    chunk_size: int
    total_chunks: int
    received_chunks: List[int] = []


class VideoUploadStatusOut(BaseModel):
    upload_id: str
    filename: str
    file_size: int
    chunk_size: int
    total_chunks: int
    received_chunks: List[int]
    status: str


class VideoCreateBody(BaseModel):
    upload_id: str = Field(..., min_length=8, max_length=64)
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    visibility: VisibilityType = "public"
    category_id: Optional[int] = Field(default=None, gt=0)
    category_name: Optional[str] = Field(default=None, max_length=64)
    album_id: Optional[int] = Field(default=None, gt=0)
    album_title: Optional[str] = Field(default=None, max_length=200)


class VideoUpdateBody(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=5000)
    visibility: Optional[VisibilityType] = None
    category_id: Optional[int] = Field(default=None, gt=0)


class VideoReplaceBody(BaseModel):
    upload_id: str = Field(..., min_length=8, max_length=64)


class VideoShareCreateBody(BaseModel):
    public_access: bool = False
    expires_hours: Optional[int] = Field(default=None, ge=1, le=8760)


class VideoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str
    visibility: str
    status: str
    mime_type: str
    file_size: int
    duration_sec: int
    view_count: int
    like_count: int = 0
    favorite_count: int = 0
    liked: bool = False
    favorited: bool = False
    uploader_id: Optional[int] = None
    uploader_name: Optional[str] = None
    original_filename: str = ""
    created_at: Optional[str] = None
    play_url: Optional[str] = None
    cover_url: Optional[str] = None
    can_play: bool = True
