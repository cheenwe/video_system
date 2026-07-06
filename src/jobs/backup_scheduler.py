"""应用内每日数据库备份 + 邮件（APScheduler）。多 worker 部署时建议改用系统 cron 调用 run_backup_email。"""
from __future__ import annotations

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from src.core.database import SessionLocal
from src.core.config import get_settings
from src.core.logging import logger
from src.services.db_backup_email import run_backup_and_email

_scheduler: BackgroundScheduler | None = None


def _job() -> None:
    try:
        s = get_settings()
        if not s.BACKUP_EMAIL_ENABLED:
            return
        with SessionLocal() as db:
            run_backup_and_email(s, db=db)
    except Exception:
        logger.exception("定时数据库备份邮件任务失败")


def start_backup_scheduler() -> BackgroundScheduler | None:
    global _scheduler
    s = get_settings()
    if not s.BACKUP_EMAIL_ENABLED:
        logger.info("BACKUP_EMAIL_ENABLED=false，不启动数据库备份邮件调度")
        return None
    if _scheduler and _scheduler.running:
        return _scheduler

    tz_name = (s.BACKUP_TIMEZONE or "").strip() or "UTC"
    try:
        tz = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        logger.warning("无效的 BACKUP_TIMEZONE=%s，改用 UTC", tz_name)
        tz = ZoneInfo("UTC")

    sched = BackgroundScheduler(timezone=tz)
    sched.add_job(
        _job,
        CronTrigger(hour=s.BACKUP_HOUR, minute=s.BACKUP_MINUTE, timezone=tz),
        id="lab_db_backup_email",
        replace_existing=True,
    )
    sched.start()
    logger.info(
        "已启动数据库备份邮件调度：每天 %02d:%02d（%s）",
        s.BACKUP_HOUR,
        s.BACKUP_MINUTE,
        tz_name,
    )
    _scheduler = sched
    return sched


def shutdown_backup_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
    _scheduler = None
