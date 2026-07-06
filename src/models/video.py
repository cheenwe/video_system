"""视频与分片上传会话"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base
from src.models._mixins import FK_TYPE, PK_TYPE, TimestampMixin


class VideoCategory(Base, TimestampMixin):
    __tablename__ = "video_categories"

    id: Mapped[int] = mapped_column(PK_TYPE, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)


class VideoAlbum(Base, TimestampMixin):
    __tablename__ = "video_albums"

    id: Mapped[int] = mapped_column(PK_TYPE, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    visibility: Mapped[str] = mapped_column(String(16), nullable=False, default="public", index=True)
    uploader_id: Mapped[int | None] = mapped_column(FK_TYPE, ForeignKey("users.id"), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class VideoAlbumItem(Base):
    __tablename__ = "video_album_items"
    __table_args__ = (UniqueConstraint("album_id", "video_id", name="uq_video_album_items_album_video"),)

    id: Mapped[int] = mapped_column(PK_TYPE, primary_key=True, autoincrement=True)
    album_id: Mapped[int] = mapped_column(FK_TYPE, ForeignKey("video_albums.id", ondelete="CASCADE"), nullable=False, index=True)
    video_id: Mapped[int] = mapped_column(FK_TYPE, ForeignKey("videos.id", ondelete="CASCADE"), nullable=False, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class Video(Base, TimestampMixin):
    __tablename__ = "videos"

    id: Mapped[int] = mapped_column(PK_TYPE, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    visibility: Mapped[str] = mapped_column(String(16), nullable=False, default="public", index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ready")
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False, default="video/mp4")
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    duration_sec: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cover_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    category_id: Mapped[int | None] = mapped_column(FK_TYPE, ForeignKey("video_categories.id"), nullable=True, index=True)
    uploader_id: Mapped[int | None] = mapped_column(FK_TYPE, ForeignKey("users.id"), nullable=True)
    view_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    like_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    favorite_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class VideoLike(Base):
    __tablename__ = "video_likes"
    __table_args__ = (UniqueConstraint("video_id", "user_id", name="uq_video_likes_video_user"),)

    id: Mapped[int] = mapped_column(PK_TYPE, primary_key=True, autoincrement=True)
    video_id: Mapped[int] = mapped_column(FK_TYPE, ForeignKey("videos.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(FK_TYPE, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class VideoFavorite(Base):
    __tablename__ = "video_favorites"
    __table_args__ = (UniqueConstraint("video_id", "user_id", name="uq_video_favorites_video_user"),)

    id: Mapped[int] = mapped_column(PK_TYPE, primary_key=True, autoincrement=True)
    video_id: Mapped[int] = mapped_column(FK_TYPE, ForeignKey("videos.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(FK_TYPE, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class VideoComment(Base):
    __tablename__ = "video_comments"

    id: Mapped[int] = mapped_column(PK_TYPE, primary_key=True, autoincrement=True)
    video_id: Mapped[int] = mapped_column(FK_TYPE, ForeignKey("videos.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int | None] = mapped_column(FK_TYPE, ForeignKey("users.id"), nullable=True)
    display_name: Mapped[str] = mapped_column(String(64), nullable=False, default="匿名用户")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_anonymous: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False, index=True)


class VideoShareLink(Base):
    __tablename__ = "video_share_links"

    id: Mapped[int] = mapped_column(PK_TYPE, primary_key=True, autoincrement=True)
    video_id: Mapped[int] = mapped_column(FK_TYPE, ForeignKey("videos.id", ondelete="CASCADE"), nullable=False, index=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    public_access: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_by: Mapped[int | None] = mapped_column(FK_TYPE, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class VideoUploadSession(Base):
    __tablename__ = "video_upload_sessions"

    id: Mapped[int] = mapped_column(PK_TYPE, primary_key=True, autoincrement=True)
    upload_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False, default="application/octet-stream")
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    chunk_size: Mapped[int] = mapped_column(Integer, nullable=False)
    total_chunks: Mapped[int] = mapped_column(Integer, nullable=False)
    # 逗号分隔已收到的分片序号，便于断点续传查询
    received_chunks: Mapped[str] = mapped_column(Text, nullable=False, default="")
    user_id: Mapped[int | None] = mapped_column(FK_TYPE, ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="uploading")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
