"""搜索引擎：robots.txt、sitemap.xml"""
from __future__ import annotations

from datetime import timezone
from xml.sax.saxutils import escape

from sqlalchemy.orm import Session

from src.models.video import Video
from src.services.site_branding_service import get_seo_settings


def _base_url() -> str:
    url = (get_seo_settings().get("site_url") or "").strip().rstrip("/")
    return url


def build_robots_txt() -> str:
    seo = get_seo_settings()
    lines = ["User-agent: *"]
    if not seo.get("seo_indexable", True):
        lines.append("Disallow: /")
    else:
        lines.append("Allow: /")
        for path in (
            "/login",
            "/dashboard",
            "/users",
            "/sys_configs",
            "/sys_logs",
            "/site_branding",
            "/video_system",
            "/video_upload",
            "/video_categories",
            "/video_albums",
            "/profile",
            "/api/",
        ):
            lines.append(f"Disallow: {path}")
    base = _base_url()
    if base and seo.get("seo_indexable", True):
        lines.append(f"Sitemap: {base}/sitemap.xml")
    lines.append("")
    return "\n".join(lines)


def build_sitemap_xml(db: Session) -> str:
    base = _base_url()
    if not base:
        base = ""

    urls: list[tuple[str, str | None]] = [
        ("/", None),
        ("/index", None),
    ]

    if get_seo_settings().get("seo_indexable", True):
        rows = (
            db.query(Video)
            .filter(Video.status == "ready", Video.visibility == "public")
            .order_by(Video.id.desc())
            .limit(5000)
            .all()
        )
        for v in rows:
            last = v.updated_at or v.created_at
            iso = last.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00") if last else None
            urls.append((f"/video?id={v.id}", iso))

    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for path, lastmod in urls:
        if not base:
            loc = path
        else:
            loc = f"{base}{path if path.startswith('/') else '/' + path}"
        parts.append("  <url>")
        parts.append(f"    <loc>{escape(loc)}</loc>")
        if lastmod:
            parts.append(f"    <lastmod>{escape(lastmod)}</lastmod>")
        parts.append("  </url>")
    parts.append("</urlset>")
    return "\n".join(parts) + "\n"
