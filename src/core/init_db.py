"""数据库初始化与种子数据"""
from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from src.core.config import settings
from src.core.database import Base, SessionLocal, engine
from src.core.security import hash_password


def create_all() -> None:
    """创建所有表（开发/首次启动用，生产用 alembic）"""
    import src.models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def seed_data(db: Session) -> None:
    from src.models.user import User
    from src.models.video import VideoCategory

    if db.query(User).count() == 0:
        admin = User(
            username=settings.DEFAULT_ADMIN_USERNAME,
            password_hash=hash_password(settings.DEFAULT_ADMIN_PASSWORD),
            role="admin",
            disabled=0,
            real_name="系统管理员",
        )
        db.add(admin)

    if db.query(VideoCategory).count() == 0:
        defaults = [
            ("科技", "科技数码类视频", 10),
            ("生活", "日常生活分享", 20),
            ("教育", "教程与知识讲解", 30),
            ("娱乐", "影视游戏娱乐", 40),
        ]
        for name, desc, order in defaults:
            db.add(VideoCategory(name=name, description=desc, sort_order=order))

    db.commit()


def ensure_schema_compatibility() -> None:
    """兼容历史库：补齐新增列。"""
    insp = inspect(engine)
    if "sys_logs" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("sys_logs")}
        with engine.begin() as conn:
            if "tag" not in cols:
                conn.execute(text("ALTER TABLE sys_logs ADD COLUMN tag VARCHAR(32) DEFAULT 'operation'"))
            if "result" not in cols:
                conn.execute(text("ALTER TABLE sys_logs ADD COLUMN result VARCHAR(16) DEFAULT 'success'"))
            if "request_id" not in cols:
                conn.execute(text("ALTER TABLE sys_logs ADD COLUMN request_id VARCHAR(64)"))
    if "users" in insp.get_table_names():
        ucols = {c["name"] for c in insp.get_columns("users")}
        with engine.begin() as conn:
            if "timezone" not in ucols:
                conn.execute(text("ALTER TABLE users ADD COLUMN timezone VARCHAR(64) DEFAULT 'UTC' NOT NULL"))
            if "avatar_path" not in ucols:
                conn.execute(text("ALTER TABLE users ADD COLUMN avatar_path VARCHAR(500)"))
    if "videos" in insp.get_table_names():
        vcols = {c["name"] for c in insp.get_columns("videos")}
        with engine.begin() as conn:
            if "category_id" not in vcols:
                conn.execute(text("ALTER TABLE videos ADD COLUMN category_id BIGINT"))
            if "like_count" not in vcols:
                conn.execute(text("ALTER TABLE videos ADD COLUMN like_count INTEGER DEFAULT 0 NOT NULL"))
            if "favorite_count" not in vcols:
                conn.execute(text("ALTER TABLE videos ADD COLUMN favorite_count INTEGER DEFAULT 0 NOT NULL"))
    # 新表由 create_all 创建；此处仅做历史库列补齐


def init_database() -> None:
    settings.ensure_dirs()
    create_all()
    ensure_schema_compatibility()
    db = SessionLocal()
    try:
        seed_data(db)
    finally:
        db.close()
