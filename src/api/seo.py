"""SEO 路由：robots.txt / sitemap.xml"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy.orm import Session

from src.core.database import get_db
from src.services import site_seo_service

router = APIRouter(tags=["SEO"])


@router.get("/robots.txt", include_in_schema=False)
def robots_txt():
    return PlainTextResponse(
        site_seo_service.build_robots_txt(),
        media_type="text/plain; charset=utf-8",
    )


@router.get("/sitemap.xml", include_in_schema=False)
def sitemap_xml(db: Session = Depends(get_db)):
    xml = site_seo_service.build_sitemap_xml(db)
    return Response(content=xml, media_type="application/xml; charset=utf-8")
