"""视频分类与专辑"""
from __future__ import annotations

from typing import Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.core.exceptions import BizError
from src.core.input_security import like_contains_pattern, validate_category_code
from src.models.user import User
from src.models.video import Video, VideoAlbum, VideoAlbumItem, VideoCategory
from src.services import video_service


def _is_admin(user: User) -> bool:
    return (user.role or "").lower() == "admin"


def _serialize_category(c: VideoCategory, *, video_count: int = 0) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "description": c.description,
        "sort_order": c.sort_order,
        "video_count": video_count,
        "created_at": c.created_at.isoformat(sep=" ", timespec="seconds") if c.created_at else None,
    }


def list_categories(db: Session) -> list[dict]:
    rows = (
        db.query(
            VideoCategory,
            func.count(Video.id).label("video_count"),
        )
        .outerjoin(Video, Video.category_id == VideoCategory.id)
        .group_by(VideoCategory.id)
        .order_by(VideoCategory.sort_order.asc(), VideoCategory.id.asc())
        .all()
    )
    return [_serialize_category(c, video_count=int(cnt or 0)) for c, cnt in rows]


def get_category(db: Session, category_id: int) -> VideoCategory:
    c = db.get(VideoCategory, category_id)
    if not c:
        raise BizError("分类不存在", 404)
    return c


def create_category(db: Session, data: dict) -> VideoCategory:
    name = str(data["name"]).strip()
    if db.query(VideoCategory).filter(VideoCategory.name == name).first():
        raise BizError("分类名称已存在")
    c = VideoCategory(
        name=name,
        description=str(data.get("description") or "").strip(),
        sort_order=int(data.get("sort_order") or 0),
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def update_category(db: Session, category_id: int, data: dict) -> VideoCategory:
    c = get_category(db, category_id)
    if data.get("name") is not None:
        name = str(data["name"]).strip()
        exists = db.query(VideoCategory).filter(VideoCategory.name == name, VideoCategory.id != c.id).first()
        if exists:
            raise BizError("分类名称已存在")
        c.name = name
    if data.get("description") is not None:
        c.description = str(data["description"] or "").strip()
    if data.get("sort_order") is not None:
        c.sort_order = int(data["sort_order"])
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def delete_category(db: Session, category_id: int) -> None:
    c = get_category(db, category_id)
    db.query(Video).filter(Video.category_id == c.id).update({Video.category_id: None})
    db.delete(c)
    db.commit()


def find_category_by_name(db: Session, name: str) -> VideoCategory | None:
    name = (name or "").strip()
    if not name:
        return None
    return db.query(VideoCategory).filter(VideoCategory.name == name).first()


def find_or_create_category(db: Session, name: str, user: User) -> VideoCategory:
    name = (name or "").strip()
    if not name:
        raise BizError("分类名称不能为空")
    if len(name) > 64:
        raise BizError("分类名称最多 64 个字符")
    existing = find_category_by_name(db, name)
    if existing:
        return existing
    return create_category(db, {"name": name, "description": "", "sort_order": 0})


def find_album_by_title(db: Session, title: str, user: User) -> VideoAlbum | None:
    title = (title or "").strip()
    if not title:
        return None
    return (
        db.query(VideoAlbum)
        .filter(VideoAlbum.title == title, VideoAlbum.uploader_id == user.id)
        .first()
    )


def find_or_create_album(
    db: Session,
    title: str,
    user: User,
    *,
    visibility: str = "public",
) -> VideoAlbum:
    title = (title or "").strip()
    if not title:
        raise BizError("专辑标题不能为空")
    existing = find_album_by_title(db, title, user)
    if existing:
        return existing
    vis = visibility if visibility in {"public", "private"} else "public"
    return create_album(db, {"title": title, "description": "", "visibility": vis}, user)


def resolve_category_for_upload(
    db: Session,
    user: User,
    *,
    category_id: int | None = None,
    category_name: str | None = None,
) -> int | None:
    if category_id:
        validate_category_id(db, category_id)
        return int(category_id)
    if category_name and category_name.strip():
        return find_or_create_category(db, category_name.strip(), user).id
    return None


def resolve_album_for_upload(
    db: Session,
    user: User,
    *,
    album_id: int | None = None,
    album_title: str | None = None,
    visibility: str = "public",
) -> int | None:
    if album_id:
        album = get_album(db, int(album_id))
        if not _can_manage_album(album, user):
            raise BizError("无权使用该专辑", 403)
        return album.id
    if album_title and album_title.strip():
        return find_or_create_album(db, album_title.strip(), user, visibility=visibility).id
    return None


def validate_category_id(db: Session, category_id: int | None) -> None:
    if category_id is None:
        return
    get_category(db, int(category_id))


def _can_manage_album(album: VideoAlbum, user: User) -> bool:
    return _is_admin(user) or album.uploader_id == user.id


def _serialize_album(db: Session, album: VideoAlbum, user: Optional[User], *, with_videos: bool = False) -> dict:
    uploader_name = None
    if album.uploader_id:
        u = db.get(User, album.uploader_id)
        uploader_name = (u.real_name or u.username) if u else None
    video_count = db.query(VideoAlbumItem).filter(VideoAlbumItem.album_id == album.id).count()
    out = {
        "id": album.id,
        "title": album.title,
        "description": album.description,
        "visibility": album.visibility,
        "sort_order": album.sort_order,
        "uploader_id": album.uploader_id,
        "uploader_name": uploader_name,
        "video_count": video_count,
        "created_at": album.created_at.isoformat(sep=" ", timespec="seconds") if album.created_at else None,
    }
    if with_videos:
        items = (
            db.query(VideoAlbumItem, Video)
            .join(Video, Video.id == VideoAlbumItem.video_id)
            .filter(VideoAlbumItem.album_id == album.id, Video.status == "ready")
            .order_by(VideoAlbumItem.sort_order.asc(), VideoAlbumItem.id.asc())
            .all()
        )
        videos = []
        for item, video in items:
            if not video_service.can_view_detail(video, user):
                continue
            v = video_service._serialize_video(db, video, user)  # noqa: SLF001
            v["album_sort_order"] = item.sort_order
            videos.append(v)
        out["videos"] = videos
    return out


def list_albums(
    db: Session,
    *,
    page: int,
    page_size: int,
    keyword: str | None,
    visibility: str | None,
    user: Optional[User],
) -> Tuple[list[dict], int]:
    q = db.query(VideoAlbum)
    vis = (visibility or "public").strip().lower()
    if vis == "public":
        q = q.filter(VideoAlbum.visibility == "public")
    elif vis == "private":
        if user is None:
            raise BizError("查看隐私专辑请先登录", 401)
        q = q.filter(VideoAlbum.visibility == "private")
    elif vis == "mine":
        if user is None:
            raise BizError("请先登录", 401)
        q = q.filter(VideoAlbum.uploader_id == user.id)
    else:
        if user is None:
            q = q.filter(VideoAlbum.visibility == "public")
        elif not _is_admin(user):
            q = q.filter(
                (VideoAlbum.visibility == "public")
                | ((VideoAlbum.visibility == "private") & (VideoAlbum.uploader_id == user.id))
            )

    like_info = like_contains_pattern(keyword)
    if like_info:
        like, esc = like_info
        q = q.filter(VideoAlbum.title.like(like, escape=esc) | VideoAlbum.description.like(like, escape=esc))

    total = q.count()
    albums = (
        q.order_by(VideoAlbum.sort_order.asc(), VideoAlbum.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return [_serialize_album(db, a, user) for a in albums], total


def get_album(db: Session, album_id: int) -> VideoAlbum:
    a = db.get(VideoAlbum, album_id)
    if not a:
        raise BizError("专辑不存在", 404)
    return a


def assert_can_view_album(album: VideoAlbum, user: Optional[User]) -> None:
    if album.visibility == "private" and user is None:
        raise BizError("该专辑为隐私内容，请登录后查看", 401)


def album_detail(db: Session, album_id: int, user: Optional[User]) -> dict:
    album = get_album(db, album_id)
    assert_can_view_album(album, user)
    return _serialize_album(db, album, user, with_videos=True)


def create_album(db: Session, data: dict, user: User) -> VideoAlbum:
    vis = data.get("visibility") if data.get("visibility") in {"public", "private"} else "public"
    album = VideoAlbum(
        title=str(data["title"]).strip(),
        description=str(data.get("description") or "").strip(),
        visibility=vis,
        sort_order=int(data.get("sort_order") or 0),
        uploader_id=user.id,
    )
    db.add(album)
    db.commit()
    db.refresh(album)
    return album


def update_album(db: Session, album_id: int, data: dict, user: User) -> VideoAlbum:
    album = get_album(db, album_id)
    if not _can_manage_album(album, user):
        raise BizError("无权修改该专辑", 403)
    if data.get("title") is not None:
        album.title = str(data["title"]).strip()
    if data.get("description") is not None:
        album.description = str(data["description"] or "").strip()
    if data.get("visibility") is not None and str(data["visibility"]) in {"public", "private"}:
        album.visibility = str(data["visibility"])
    if data.get("sort_order") is not None:
        album.sort_order = int(data["sort_order"])
    db.add(album)
    db.commit()
    db.refresh(album)
    return album


def delete_album(db: Session, album_id: int, user: User) -> None:
    album = get_album(db, album_id)
    if not _can_manage_album(album, user):
        raise BizError("无权删除该专辑", 403)
    db.query(VideoAlbumItem).filter(VideoAlbumItem.album_id == album.id).delete()
    db.delete(album)
    db.commit()


def add_video_to_album(db: Session, album_id: int, video_id: int, sort_order: int, user: User) -> None:
    album = get_album(db, album_id)
    if not _can_manage_album(album, user):
        raise BizError("无权管理该专辑", 403)
    video = video_service.get_video(db, video_id)
    if not _is_admin(user) and video.uploader_id != user.id:
        raise BizError("只能添加自己上传的视频", 403)
    exists = (
        db.query(VideoAlbumItem)
        .filter(VideoAlbumItem.album_id == album.id, VideoAlbumItem.video_id == video.id)
        .first()
    )
    if exists:
        raise BizError("该视频已在专辑中")
    item = VideoAlbumItem(album_id=album.id, video_id=video.id, sort_order=sort_order)
    db.add(item)
    db.commit()


def remove_video_from_album(db: Session, album_id: int, video_id: int, user: User) -> None:
    album = get_album(db, album_id)
    if not _can_manage_album(album, user):
        raise BizError("无权管理该专辑", 403)
    item = (
        db.query(VideoAlbumItem)
        .filter(VideoAlbumItem.album_id == album.id, VideoAlbumItem.video_id == video_id)
        .first()
    )
    if not item:
        raise BizError("视频不在该专辑中", 404)
    db.delete(item)
    db.commit()


def attach_video_to_album_on_create(db: Session, video: Video, album_id: int | None, user: User) -> None:
    if not album_id:
        return
    add_video_to_album(db, album_id, video.id, sort_order=0, user=user)


def albums_for_video(db: Session, video_id: int, user: Optional[User]) -> list[dict]:
    rows = (
        db.query(VideoAlbum, VideoAlbumItem)
        .join(VideoAlbumItem, VideoAlbumItem.album_id == VideoAlbum.id)
        .filter(VideoAlbumItem.video_id == video_id)
        .order_by(VideoAlbumItem.sort_order.asc())
        .all()
    )
    out = []
    for album, item in rows:
        try:
            assert_can_view_album(album, user)
        except BizError:
            continue
        out.append(
            {
                "id": album.id,
                "title": album.title,
                "visibility": album.visibility,
                "sort_order": item.sort_order,
            }
        )
    return out
