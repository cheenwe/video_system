"""数据库备份（MySQL mysqldump / SQLite 文件）打包 ZIP 后通过 SMTP 发送邮件。"""
from __future__ import annotations

import fcntl
import os
import shutil
import smtplib
import ssl
import subprocess
import tempfile
import textwrap
import zipfile
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from typing import List, Optional, TextIO

from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import Session

from src.core.config import RUNTIME_ROOT, Settings, _sqlite_data_path, get_settings
from src.core.logging import logger


def _acquire_backup_lock() -> tuple[TextIO, Path]:
    """获取进程级互斥锁，避免并发任务同时备份。"""
    lock_path = (RUNTIME_ROOT / ".backup_email.lock").resolve()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_file = open(lock_path, "w", encoding="utf-8")
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as e:
        lock_file.close()
        raise RuntimeError("已有数据库备份任务正在执行，请稍后重试") from e
    return lock_file, lock_path


def _release_backup_lock(lock_file: TextIO) -> None:
    try:
        fileno = lock_file.fileno()
        fcntl.flock(fileno, fcntl.LOCK_UN)
    finally:
        lock_file.close()


def _verify_zip_integrity(zip_path: Path) -> None:
    """校验 ZIP 文件目录与内容完整性。"""
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            if not zf.namelist():
                raise RuntimeError("备份 ZIP 为空")
            bad = zf.testzip()
            if bad:
                raise RuntimeError(f"ZIP 文件内容损坏: {bad}")
    except (zipfile.BadZipFile, OSError) as e:
        raise RuntimeError(f"备份压缩包校验失败: {e}") from e


def _mysql_dump_sql(settings: Settings, out_sql: Path) -> None:
    url = make_url(settings.DATABASE_URL)
    if not str(url.drivername).lower().startswith("mysql"):
        raise RuntimeError("当前 DATABASE_URL 不是 MySQL，无法使用 mysqldump")
    user = url.username or ""
    password = url.password or ""
    host = url.host or "127.0.0.1"
    port = int(url.port or 3306)
    db = (url.database or "").split("?")[0]
    if not db:
        raise RuntimeError("DATABASE_URL 中未指定数据库名")

    fd, cnf_path = tempfile.mkstemp(prefix="lab_mysqldump_", suffix=".cnf", text=True)
    try:
        os.close(fd)
        Path(cnf_path).write_text(
            textwrap.dedent(
                f"""\
                [client]
                host={host}
                port={port}
                user={user}
                password={password}
                """
            ),
            encoding="utf-8",
        )
        os.chmod(cnf_path, 0o600)
        cmd: List[str] = [
            settings.MYSQLDUMP_PATH,
            f"--defaults-file={cnf_path}",
            "--single-transaction",
            "--routines",
            "--events",
            "--databases",
            db,
        ]
        logger.info("开始 mysqldump: host=%s port=%s db=%s", host, port, db)
        with open(out_sql, "wb") as f_sql:
            proc = subprocess.run(
                cmd,
                stdout=f_sql,
                stderr=subprocess.PIPE,
                timeout=3600,
                check=False,
            )
        if proc.returncode != 0:
            err = (proc.stderr or b"").decode("utf-8", errors="replace")[-4000:]
            raise RuntimeError(f"mysqldump 失败 (code={proc.returncode}): {err}")
    finally:
        try:
            os.unlink(cnf_path)
        except OSError:
            pass


def _sqlite_file_copy(settings: Settings, out_file: Path) -> None:
    """复制 SQLite 数据文件用于后续 ZIP 打包。"""
    db_path = _sqlite_data_path(settings.DATABASE_URL)
    if db_path is None or not db_path.is_file():
        raise RuntimeError("未找到 SQLite 数据库文件路径")
    logger.info("备份 SQLite 文件: %s", db_path)
    shutil.copy2(db_path, out_file)


def _make_zip(source_file: Path, out_zip: Path, arcname: str) -> None:
    with zipfile.ZipFile(
        out_zip, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as zf:
        zf.write(source_file, arcname=arcname)


def _send_smtp_with_attachment(
    settings: Settings,
    *,
    attachment_path: Path,
    subject: str,
    body_text: str,
) -> None:
    to_list = settings.backup_email_recipients
    if not settings.SMTP_HOST.strip():
        raise RuntimeError("SMTP_HOST 未配置")
    if not to_list:
        raise RuntimeError("BACKUP_EMAIL_TO 未配置")
    sender = (settings.SMTP_FROM or settings.SMTP_USER or "").strip()
    if not sender:
        raise RuntimeError("SMTP_FROM 或 SMTP_USER 未配置发件人")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(to_list)
    msg.set_content(body_text)
    data = attachment_path.read_bytes()
    subtype = "zip" if attachment_path.suffix.lower() == ".zip" else "octet-stream"
    msg.add_attachment(
        data,
        maintype="application",
        subtype=subtype,
        filename=attachment_path.name,
    )

    logger.info(
        "SMTP 发送备份: host=%s port=%s tls=%s ssl=%s to=%s",
        settings.SMTP_HOST,
        settings.SMTP_PORT,
        settings.SMTP_USE_TLS,
        settings.SMTP_USE_SSL,
        to_list,
    )
    smtp_timeout = 300
    ctx = ssl.create_default_context()
    try:
        if settings.SMTP_USE_SSL:
            with smtplib.SMTP_SSL(
                settings.SMTP_HOST, settings.SMTP_PORT, timeout=smtp_timeout, context=ctx
            ) as smtp:
                try:
                    smtp.ehlo()
                except smtplib.SMTPException:
                    pass
                if settings.SMTP_USER:
                    smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=smtp_timeout) as smtp:
                smtp.ehlo()
                if settings.SMTP_USE_TLS:
                    smtp.starttls(context=ctx)
                    smtp.ehlo()
                if settings.SMTP_USER:
                    smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                smtp.send_message(msg)
    except (smtplib.SMTPException, OSError) as e:
        err_text = str(e)
        hint = (
            " 常见原因：465 端口须设置 SMTP_USE_SSL=true、SMTP_USE_TLS=false；"
            "587 多为 SMTP_USE_SSL=false、SMTP_USE_TLS=true；发件邮箱与认证方式需与服务商说明一致。"
        )
        if "unexpectedly closed" in err_text.lower() or "connection" in err_text.lower():
            hint += " 若为「Connection unexpectedly closed」，多为端口/SSL 与服务器要求不匹配。"
        raise RuntimeError("SMTP 发送失败：" + err_text + hint) from e


def _write_backup_sys_log(
    db: Optional[Session],
    *,
    result: str,
    remark: str,
    user_id: Optional[int] = None,
    username: Optional[str] = None,
    ip: Optional[str] = None,
    request_id: Optional[str] = None,
) -> None:
    """将备份邮件执行结果写入 sys_logs（失败不影响备份流程）。"""
    if db is None:
        return
    try:
        from src.services.log_service import log_action

        log_action(
            db,
            tag="operation",
            action="db_backup.email",
            result=result,
            user_id=user_id,
            username=username,
            ip=ip,
            request_id=request_id,
            remark=(remark[:8000] if remark else None),
        )
    except Exception:
        logger.exception("写入 sys_logs（数据库备份邮件）失败")


def run_backup_and_email(
    settings: Settings | None = None,
    *,
    db: Optional[Session] = None,
    force: bool = False,
    log_user_id: Optional[int] = None,
    log_username: Optional[str] = None,
    log_ip: Optional[str] = None,
    log_request_id: Optional[str] = None,
) -> dict[str, str]:
    """
    执行一次备份并发送邮件。供定时任务、`python -m src.jobs.run_backup_email` 或管理接口调用。
    传入 db 时会在 sys_logs 表记录执行结果（成功 / 失败 / 跳过）。

    :param force: 为 True 时忽略 BACKUP_EMAIL_ENABLED=false（仅管理员调试用）。
    """
    s = settings or get_settings()
    log_kw = dict(
        user_id=log_user_id,
        username=log_username,
        ip=log_ip,
        request_id=log_request_id,
    )

    if not force and not s.BACKUP_EMAIL_ENABLED:
        _write_backup_sys_log(db, result="success", remark="跳过：BACKUP_EMAIL_ENABLED=false", **log_kw)
        return {"skipped": "BACKUP_EMAIL_ENABLED=false"}

    if not s.is_mysql_database and not s.is_sqlite_database:
        _write_backup_sys_log(db, result="failed", remark="仅支持 MySQL 或 SQLite 的 DATABASE_URL", **log_kw)
        raise RuntimeError("仅支持 MySQL 或 SQLite 的 DATABASE_URL")

    # 使用微秒级时间戳，避免并发任务在同一秒生成同名文件导致覆盖/损坏。
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    fname = f"lab_db_backup_{ts}.zip"
    tmp_dir = tempfile.mkdtemp(prefix="lab_db_bak_")
    zip_path = Path(tmp_dir) / fname
    raw_name = f"lab_db_backup_{ts}.sql" if s.is_mysql_database else f"lab_db_backup_{ts}.db"
    raw_path = Path(tmp_dir) / raw_name
    lock_file = None
    try:
        lock_file, lock_path = _acquire_backup_lock()
        logger.info("已获取备份互斥锁: %s", lock_path)
        if s.is_mysql_database:
            _mysql_dump_sql(s, raw_path)
        else:
            _sqlite_file_copy(s, raw_path)

        _make_zip(raw_path, zip_path, raw_name)
        _verify_zip_integrity(zip_path)
        size_mb = zip_path.stat().st_size / (1024 * 1024)
        kind = "MySQL(mysqldump)" if s.is_mysql_database else "SQLite(数据文件)"
        body = (
            f"系统数据库定时备份。\n"
            f"类型: {kind}\n"
            f"压缩格式: ZIP\n"
            f"文件: {fname}\n"
            f"大小: {size_mb:.2f} MB\n"
            f"生成时间(服务器本地): {datetime.now().isoformat(timespec='seconds')}\n"
        )

        if s.BACKUP_KEEP_LOCAL_COPY:
            dest_dir = Path(s.BACKUP_LOCAL_DIR)
            if not dest_dir.is_absolute():
                dest_dir = RUNTIME_ROOT / dest_dir
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / fname
            shutil.copy2(zip_path, dest)
            logger.info("已保留本地副本: %s", dest)

        _send_smtp_with_attachment(
            s,
            attachment_path=zip_path,
            subject=f"[lab_system] 数据库备份 {fname}",
            body_text=body,
        )
        logger.info("数据库备份邮件已发送: %s (%.2f MB)", fname, size_mb)
        _write_backup_sys_log(
            db,
            result="success",
            remark=f"已发送邮件 附件={fname} 约{size_mb:.2f}MB 类型={kind} 格式=ZIP",
            **log_kw,
        )
        return {"ok": "1", "file": fname, "size_mb": f"{size_mb:.2f}", "format": "zip"}
    except Exception as e:
        _write_backup_sys_log(db, result="failed", remark=str(e), **log_kw)
        raise
    finally:
        if lock_file is not None:
            _release_backup_lock(lock_file)
        shutil.rmtree(tmp_dir, ignore_errors=True)
