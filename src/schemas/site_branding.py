"""站点品牌 Schema"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class SiteBrandingUpdateBody(BaseModel):
    site_name: Optional[str] = Field(default=None, max_length=32)
    accent_theme: Optional[str] = Field(default=None, max_length=16)
    copyright_text: Optional[str] = Field(default=None, max_length=200)
    seo_title: Optional[str] = Field(default=None, max_length=70)
    seo_description: Optional[str] = Field(default=None, max_length=500)
    seo_keywords: Optional[str] = Field(default=None, max_length=500)
    seo_robots: Optional[str] = Field(default=None, max_length=64)
    seo_indexable: Optional[bool] = None
    site_url: Optional[str] = Field(default=None, max_length=200)
