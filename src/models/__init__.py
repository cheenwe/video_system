"""ORM 模型集合"""
from src.core.database import Base
from src.models.user import User
from src.models.sys_config import SysConfig
from src.models.sys_log import SysLog
from src.models.auth_revoked_token import AuthRevokedToken
from src.models.video import Video, VideoAlbum, VideoAlbumItem, VideoCategory, VideoComment, VideoFavorite, VideoLike, VideoShareLink, VideoUploadSession

__all__ = [
    "Base",
    "User",
    "SysConfig",
    "SysLog",
    "AuthRevokedToken",
    "Video",
    "VideoCategory",
    "VideoAlbum",
    "VideoAlbumItem",
    "VideoComment",
    "VideoLike",
    "VideoFavorite",
    "VideoShareLink",
    "VideoUploadSession",
]
