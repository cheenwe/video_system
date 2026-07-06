"""系统概览 API"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.core.database import get_db
from src.core.deps import require_admin
from src.core.exceptions import ok
from src.models.user import User
from src.services import dashboard_service

router = APIRouter(tags=["系统概览"])


@router.get("/api/dashboard/stats")
def api_dashboard_stats(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return ok(dashboard_service.get_dashboard_stats(db))
