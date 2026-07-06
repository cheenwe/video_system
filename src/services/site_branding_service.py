"""站点品牌：Logo / Favicon / 投稿图标 / 主页色调"""
from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from typing import Any

from fastapi import UploadFile

from src.core.config import settings
from src.core.exceptions import BizError
from src.core.local_storage import safe_filename

ACCENT_THEMES: dict[str, dict[str, str]] = {
    "pink": {"label": "樱花粉", "primary": "#fb7299", "dark": "#e85d88"},
    "blue": {"label": "海洋蓝", "primary": "#00a1d6", "dark": "#0084b0"},
    "green": {"label": "清新绿", "primary": "#00b578", "dark": "#009962"},
    "purple": {"label": "紫罗兰", "primary": "#7b61ff", "dark": "#6248e6"},
    "orange": {"label": "活力橙", "primary": "#ff7f24", "dark": "#e56a10"},
    "red": {"label": "经典红", "primary": "#ff4757", "dark": "#e84118"},
    "teal": {"label": "青碧", "primary": "#18a999", "dark": "#138f82"},
    "indigo": {"label": "靛蓝", "primary": "#5865f2", "dark": "#4752c4"},
    "gold": {"label": "琥珀金", "primary": "#f5a623", "dark": "#d48806"},
    "rose": {"label": "玫瑰", "primary": "#e84393", "dark": "#c7367d"},
    "cyan": {"label": "天青", "primary": "#13c2c2", "dark": "#08979c"},
    "crimson": {"label": "绯红", "primary": "#c41e3a", "dark": "#a01830"},
    "lime": {"label": "薄荷", "primary": "#52c41a", "dark": "#389e0d"},
    "magenta": {"label": "品红", "primary": "#eb2f96", "dark": "#c41d7f"},
    "slate": {"label": "石墨", "primary": "#607d8b", "dark": "#455a64"},
}

DEFAULT_BRANDING: dict[str, Any] = {
    "site_name": "V视频站",
    "accent_theme": "pink",
    "copyright_text": "© {year} V视频站 版权所有 |微信: amwahaha",
    "github_url": "https://github.com/cheenwe/video_system",
    "logo": None,
    "favicon": None,
    "upload_icon": None,
    # ---------- SEO（搜索引擎）----------
    "seo_title": "V视频站 - 在线视频分享与点播",
    "seo_description": "V视频站提供公开视频推荐、分类浏览、专辑合集与高清在线播放，支持投稿分享优质视频内容。",
    "seo_keywords": "视频,在线视频,视频分享,高清视频,短视频,视频点播,视频站,公开视频,V视频站,视频推荐",
    "seo_robots": "index,follow",
    "seo_indexable": True,
    "site_url": "",
}

ASSET_KEYS = {"logo", "favicon", "upload_icon"}
ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico"}
MAX_ICON_BYTES = 2 * 1024 * 1024


def _config_path() -> Path:
    return settings.site_branding_root_path / "branding.json"


def _load_raw() -> dict[str, Any]:
    path = _config_path()
    if not path.is_file():
        return dict(DEFAULT_BRANDING)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return dict(DEFAULT_BRANDING)
        out = dict(DEFAULT_BRANDING)
        out.update(data)
        return out
    except (OSError, json.JSONDecodeError):
        return dict(DEFAULT_BRANDING)


def _save_raw(data: dict[str, Any]) -> None:
    settings.site_branding_root_path.mkdir(parents=True, exist_ok=True)
    _config_path().write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _asset_file(key: str, filename: str | None) -> Path | None:
    if not filename:
        return None
    safe = safe_filename(filename)
    p = settings.site_branding_root_path / safe
    return p if p.is_file() else None


def asset_url(key: str, filename: str | None) -> str | None:
    path = _asset_file(key, filename)
    if not path:
        return None
    return f"/api/site/branding/asset/{key}?v={path.stat().st_mtime_ns}"


def _theme_options() -> list[dict[str, str]]:
    return [{"id": k, "label": v["label"], "primary": v["primary"]} for k, v in ACCENT_THEMES.items()]


def _resolve_accent(raw: dict[str, Any]) -> str:
    accent = raw.get("accent_theme") or "pink"
    if accent not in ACCENT_THEMES:
        accent = "pink"
    return accent


def _seo_payload(raw: dict[str, Any]) -> dict[str, Any]:
    indexable = raw.get("seo_indexable")
    if indexable is None:
        indexable = DEFAULT_BRANDING["seo_indexable"]
    return {
        "seo_title": (raw.get("seo_title") or DEFAULT_BRANDING["seo_title"] or "").strip(),
        "seo_description": (raw.get("seo_description") or DEFAULT_BRANDING["seo_description"] or "").strip(),
        "seo_keywords": (raw.get("seo_keywords") or DEFAULT_BRANDING["seo_keywords"] or "").strip(),
        "seo_robots": (raw.get("seo_robots") or DEFAULT_BRANDING["seo_robots"] or "index,follow").strip(),
        "seo_indexable": bool(indexable),
        "site_url": (raw.get("site_url") or "").strip().rstrip("/"),
    }


def get_seo_settings() -> dict[str, Any]:
    return _seo_payload(_load_raw())


def get_branding_public() -> dict[str, Any]:
    raw = _load_raw()
    accent = _resolve_accent(raw)
    return {
        "site_name": raw.get("site_name") or DEFAULT_BRANDING["site_name"],
        "accent_theme": accent,
        "copyright_text": raw.get("copyright_text", DEFAULT_BRANDING["copyright_text"]),
        "github_url": raw.get("github_url") or DEFAULT_BRANDING["github_url"],
        "logo_url": asset_url("logo", raw.get("logo")),
        "favicon_url": asset_url("favicon", raw.get("favicon")),
        "upload_icon_url": asset_url("upload_icon", raw.get("upload_icon")),
        **_seo_payload(raw),
    }


def get_branding_admin() -> dict[str, Any]:
    data = get_branding_public()
    data["themes"] = _theme_options()
    return data


def update_branding(
    *,
    site_name: str | None = None,
    accent_theme: str | None = None,
    copyright_text: str | None = None,
    seo_title: str | None = None,
    seo_description: str | None = None,
    seo_keywords: str | None = None,
    seo_robots: str | None = None,
    seo_indexable: bool | None = None,
    site_url: str | None = None,
) -> dict[str, Any]:
    raw = _load_raw()
    if site_name is not None:
        name = site_name.strip()
        if not name:
            raise BizError("站点名称不能为空")
        if len(name) > 32:
            raise BizError("站点名称最多 32 个字符")
        raw["site_name"] = name
    if accent_theme is not None:
        theme = accent_theme.strip().lower()
        if theme not in ACCENT_THEMES:
            raise BizError("无效的色调主题")
        raw["accent_theme"] = theme
    if copyright_text is not None:
        text = copyright_text.strip()
        if len(text) > 200:
            raise BizError("版权信息最多 200 个字符")
        raw["copyright_text"] = text
    if seo_title is not None:
        title = seo_title.strip()
        if len(title) > 70:
            raise BizError("SEO 标题最多 70 个字符")
        raw["seo_title"] = title
    if seo_description is not None:
        desc = seo_description.strip()
        if len(desc) > 500:
            raise BizError("SEO 描述最多 500 个字符")
        raw["seo_description"] = desc
    if seo_keywords is not None:
        kw = seo_keywords.strip()
        if len(kw) > 500:
            raise BizError("SEO 关键词最多 500 个字符")
        raw["seo_keywords"] = kw
    if seo_robots is not None:
        robots = seo_robots.strip()
        if len(robots) > 64:
            raise BizError("robots 指令最多 64 个字符")
        raw["seo_robots"] = robots
    if seo_indexable is not None:
        raw["seo_indexable"] = bool(seo_indexable)
    if site_url is not None:
        url = site_url.strip().rstrip("/")
        if url and not (url.startswith("http://") or url.startswith("https://")):
            raise BizError("站点 URL 须以 http:// 或 https:// 开头")
        if len(url) > 200:
            raise BizError("站点 URL 最多 200 个字符")
        raw["site_url"] = url
    _save_raw(raw)
    return get_branding_admin()


def get_asset_path(key: str) -> Path:
    if key not in ASSET_KEYS:
        raise BizError("无效的资源类型", 404)
    raw = _load_raw()
    filename = raw.get(key)
    path = _asset_file(key, filename)
    if not path:
        raise BizError("资源不存在", 404)
    return path


async def save_asset(key: str, file: UploadFile) -> dict[str, Any]:
    if key not in ASSET_KEYS:
        raise BizError("无效的资源类型")
    original = (file.filename or "").strip()
    ext = Path(original).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise BizError("仅支持 PNG / JPG / GIF / WEBP / SVG / ICO 图标")
    data = await file.read()
    if not data:
        raise BizError("文件为空")
    if len(data) > MAX_ICON_BYTES:
        raise BizError("图标文件过大，最大 2MB")

    save_name = f"{key}{ext}"
    dest = settings.site_branding_root_path / save_name
    dest.write_bytes(data)

    raw = _load_raw()
    for other in ASSET_KEYS:
        if other == key:
            continue
        old = raw.get(other)
        if old and old != save_name:
            old_path = settings.site_branding_root_path / old
            if old_path.is_file() and old_path.name.startswith(f"{other}.") and old_path.name != save_name:
                pass
    # 清理同 key 旧扩展名文件
    for old_file in settings.site_branding_root_path.glob(f"{key}.*"):
        if old_file.name != save_name:
            try:
                old_file.unlink()
            except OSError:
                pass

    raw[key] = save_name
    _save_raw(raw)
    return get_branding_admin()


def remove_asset(key: str) -> dict[str, Any]:
    if key not in ASSET_KEYS:
        raise BizError("无效的资源类型")
    raw = _load_raw()
    filename = raw.get(key)
    if filename:
        path = settings.site_branding_root_path / filename
        if path.is_file():
            try:
                path.unlink()
            except OSError:
                pass
    raw[key] = None
    _save_raw(raw)
    return get_branding_admin()


def asset_media_type(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"
