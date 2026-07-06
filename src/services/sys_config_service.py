"""系统配置服务"""
from __future__ import annotations

import csv
from io import StringIO
from typing import List, Optional, Tuple

from sqlalchemy import or_
from sqlalchemy.orm import Session

from src.core.exceptions import BizError
from src.core.input_security import like_contains_pattern, validate_category_code
from src.models.sys_config import SysConfig
from src.schemas.sys_config import SysConfigCreate, SysConfigUpdate
from src.services.csv_helpers import norm_row

# 检验记录检测矩阵「快捷填入」：在系统配置中维护，值为英文逗号分隔（可含中文逗号输入，会归一）
MATRIX_QUICK_FILL_CATEGORY = "inspection"
MATRIX_QUICK_FILL_CODE = "matrix_quick_fill"
DEFAULT_MATRIX_QUICK_FILL_RAW = "<0.02,0.04,0.1"

_PUBLIC_CONFIG_KEYS: frozenset[tuple[str, str]] = frozenset(
    {(MATRIX_QUICK_FILL_CATEGORY, MATRIX_QUICK_FILL_CODE)}
)


def parse_quick_fill_csv(raw: str | None) -> list[str]:
    if not raw or not str(raw).strip():
        return []
    s = str(raw).replace("，", ",")
    return [p.strip() for p in s.split(",") if p.strip()]


def get_matrix_quick_fill_items(db: Session) -> list[str]:
    c = (
        db.query(SysConfig)
        .filter(
            SysConfig.category == MATRIX_QUICK_FILL_CATEGORY,
            SysConfig.code == MATRIX_QUICK_FILL_CODE,
            SysConfig.status == "active",
        )
        .first()
    )
    raw = (c.value or "").strip() if c else ""
    items = parse_quick_fill_csv(raw)
    if not items:
        items = parse_quick_fill_csv(DEFAULT_MATRIX_QUICK_FILL_RAW)
    return items


def get_public_config_payload(db: Session, category: str, code: str) -> dict[str, object]:
    cat = (category or "").strip()
    cod = (code or "").strip()
    if (cat, cod) not in _PUBLIC_CONFIG_KEYS:
        raise BizError("不支持的配置项", 404)
    if (cat, cod) == (MATRIX_QUICK_FILL_CATEGORY, MATRIX_QUICK_FILL_CODE):
        return {
            "category": cat,
            "code": cod,
            "items": get_matrix_quick_fill_items(db),
        }
    raise BizError("不支持的配置项", 404)


def list_configs(db: Session, page: int, page_size: int, keyword: Optional[str], category: Optional[str]) -> Tuple[List[SysConfig], int]:
    q = db.query(SysConfig)
    like_info = like_contains_pattern(keyword)
    if like_info:
        like, esc = like_info
        q = q.filter(or_(SysConfig.code.ilike(like, escape=esc), SysConfig.value.ilike(like, escape=esc)))
    cat = validate_category_code(category)
    if cat:
        q = q.filter(SysConfig.category == cat)
    total = q.count()
    items = q.order_by(SysConfig.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return items, total


def create_config(db: Session, data: SysConfigCreate, updated_by: Optional[int]) -> SysConfig:
    if db.query(SysConfig).filter(SysConfig.category == data.category, SysConfig.code == data.code).first():
        raise BizError("配置项已存在")
    c = SysConfig(
        category=data.category,
        code=data.code,
        value=data.value,
        status=data.status or "active",
        version=data.version,
        updated_by=updated_by,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def update_config(db: Session, cid: int, data: SysConfigUpdate, updated_by: Optional[int]) -> SysConfig:
    c = db.get(SysConfig, cid)
    if not c:
        raise BizError("配置不存在", 404)
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(c, k, v)
    c.updated_by = updated_by
    db.commit()
    db.refresh(c)
    return c


def delete_config(db: Session, cid: int) -> None:
    c = db.get(SysConfig, cid)
    if not c:
        raise BizError("配置不存在", 404)
    db.delete(c)
    db.commit()


_SYS_EXPORT_HEADER = ["category", "code", "value", "status", "version"]


def export_sys_configs_csv(db: Session) -> str:
    buf = StringIO()
    w = csv.writer(buf)
    w.writerow(_SYS_EXPORT_HEADER)
    for c in db.query(SysConfig).order_by(SysConfig.category.asc(), SysConfig.code.asc()).all():
        w.writerow([c.category, c.code, c.value or "", c.status, c.version or ""])
    return buf.getvalue()


def import_sys_configs_from_csv(db: Session, text: str, updated_by: Optional[int]) -> dict[str, int]:
    reader = csv.DictReader(StringIO(text))
    if not reader.fieldnames:
        raise BizError("CSV 无表头")
    created = 0
    updated = 0
    line_no = 1
    for raw in reader:
        line_no += 1
        row = norm_row(raw)
        category = (row.get("category") or "").strip()
        code = (row.get("code") or "").strip()
        if not category and not code:
            continue
        if not category or not code:
            raise BizError(f"第 {line_no} 行：category 与 code 均必填")
        value = (row.get("value") or "").strip() or None
        status = (row.get("status") or "active").strip() or "active"
        version = (row.get("version") or "").strip() or None
        existing = (
            db.query(SysConfig).filter(SysConfig.category == category, SysConfig.code == code).first()
        )
        if existing:
            existing.value = value
            existing.status = status
            if version is not None:
                existing.version = version
            existing.updated_by = updated_by
            updated += 1
        else:
            db.add(
                SysConfig(
                    category=category,
                    code=code,
                    value=value,
                    status=status,
                    version=version,
                    updated_by=updated_by,
                )
            )
            created += 1
    db.commit()
    return {"created": created, "updated": updated}
