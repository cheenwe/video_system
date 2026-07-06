"""一次性执行数据库备份并发邮件。

适合系统 cron（与 uvicorn 多进程解耦），在项目根目录执行：

    .venv/bin/python -m src.jobs.run_backup_email

需 .env 中 BACKUP_EMAIL_ENABLED=true 且配置好 SMTP 与收件人。
"""
from __future__ import annotations

import sys

from src.core.config import get_settings
from src.core.database import SessionLocal
from src.core.logging import logger, setup_logging
from src.services.db_backup_email import run_backup_and_email


def main() -> int:
    setup_logging("INFO")
    s = get_settings()
    with SessionLocal() as db:
        if not s.BACKUP_EMAIL_ENABLED:
            run_backup_and_email(s, db=db)
            logger.info("BACKUP_EMAIL_ENABLED=false，已记录 sys_logs 后退出")
            return 0
        try:
            out = run_backup_and_email(s, db=db)
            logger.info("备份任务结果: %s", out)
            return 0
        except Exception as e:
            logger.exception("备份任务失败: %s", e)
            return 1


if __name__ == "__main__":
    sys.exit(main())
