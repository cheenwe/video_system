"""站点品牌 API"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from src.core.database import get_db
from src.core.deps import get_client_ip, require_admin
from src.core.exceptions import ok
from src.models.user import User
from src.schemas.site_branding import SiteBrandingUpdateBody
from src.services import site_branding_service
from src.services.log_service import log_action

router = APIRouter(tags=["站点品牌"])


@router.get("/api/site/branding")
def api_get_branding():
    return ok(site_branding_service.get_branding_public())


@router.get("/api/site/branding/admin")
def api_get_branding_admin(_me: User = Depends(require_admin)):
    return ok(site_branding_service.get_branding_admin())


@router.put("/api/site/branding")
def api_update_branding(
    body: SiteBrandingUpdateBody,
    request: Request,
    db: Session = Depends(get_db),
    me: User = Depends(require_admin),
):
    data = site_branding_service.update_branding(
        site_name=body.site_name,
        accent_theme=body.accent_theme,
        copyright_text=body.copyright_text,
        seo_title=body.seo_title,
        seo_description=body.seo_description,
        seo_keywords=body.seo_keywords,
        seo_robots=body.seo_robots,
        seo_indexable=body.seo_indexable,
        site_url=body.site_url,
    )
    log_action(
        db,
        tag="operation",
        action="site_branding.update",
        user_id=me.id,
        username=me.username,
        ip=get_client_ip(request),
        remark=body.model_dump_json(),
    )
    return ok(data)


@router.post("/api/site/branding/upload")
async def api_upload_branding(
    request: Request,
    asset: str = Form(..., description="logo | favicon | upload_icon"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    me: User = Depends(require_admin),
):
    data = await site_branding_service.save_asset(asset.strip().lower(), file)
    log_action(
        db,
        tag="operation",
        action="site_branding.upload",
        user_id=me.id,
        username=me.username,
        ip=get_client_ip(request),
        remark=asset,
    )
    return ok(data, msg="上传成功")


@router.delete("/api/site/branding/{asset}")
def api_delete_branding_asset(
    asset: str,
    request: Request,
    db: Session = Depends(get_db),
    me: User = Depends(require_admin),
):
    data = site_branding_service.remove_asset(asset.strip().lower())
    log_action(
        db,
        tag="operation",
        action="site_branding.delete_asset",
        user_id=me.id,
        username=me.username,
        ip=get_client_ip(request),
        remark=asset,
    )
    return ok(data, msg="已恢复默认")


@router.get("/api/site/branding/asset/{asset}")
def api_branding_asset(asset: str):
    path = site_branding_service.get_asset_path(asset.strip().lower())
    return FileResponse(
        str(path),
        media_type=site_branding_service.asset_media_type(path),
        filename=path.name,
    )
