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


class VideoQoEBody(BaseModel):
    """播放质量上报体；字段与前端 getQoe() 对应。

    JS 侧习惯 camelCase，Python 侧习惯 snake_case，两者都接受：只认一种写法时
    一旦拼错字段名会被静默忽略，落库成一条全 0 的记录，报表就失真了。
    """

    model_config = ConfigDict(populate_by_name=True)

    ttff_ms: int = Field(default=0, alias="ttffMs", ge=0, le=600_000)
    waiting_count: int = Field(default=0, alias="waitingCount", ge=0, le=100_000)
    waiting_ms: int = Field(default=0, alias="waitingMs", ge=0, le=3_600_000)
    level: int = Field(default=-1, ge=-1, le=32)
    auto_level: int = Field(default=-1, alias="autoLevel", ge=-1, le=32)
    manual: bool = False
    fallback_reason: str = Field(default="", alias="fallbackReason", max_length=120)
    downgrades: int = Field(default=0, ge=0, le=100)
    sw_cached: bool = Field(default=False, alias="swCached")
    elapsed_ms: int = Field(default=0, alias="elapsedMs", ge=0, le=86_400_000)
