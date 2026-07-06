"""各环境变量在配置页的说明与示例值（键统一大写）。"""
from __future__ import annotations

from pathlib import Path

from src.core.config import BUNDLE_ROOT, RUNTIME_ROOT

# (说明, 示例值) — 示例为简短单行，便于表格展示
RUNTIME_ENV_KEY_DOC: dict[str, tuple[str, str]] = {
    "HOST": ("HTTP 服务绑定地址；修改后需重启进程。", "0.0.0.0"),
    "PORT": ("HTTP 监听端口；与当前进程绑定相关，页面仅展示不可改。", "8808"),
    "DEBUG": ("调试模式；true 时开放 /docs、/redoc 等接口文档。", "true"),
    "DATABASE_URL": (
        "数据库连接串。SQLite 相对路径相对运行目录；MySQL 示例见下行。",
        "sqlite:///./data/lab_system.db",
    ),
    "UPLOAD_ROOT": ("上传根目录（本地文件夹；相对则相对运行目录，禁止 http(s)://）。", "uploads"),
    "VIDEO_MAX_UPLOAD_MB": ("单个视频最大体积（MB）。", "5120"),
    "VIDEO_CHUNK_SIZE_MB": ("断点续传分片大小（MB）。", "5"),
    "VIDEO_ALLOW_ANONYMOUS_PLAY": ("是否允许未登录用户播放公开视频；false 时所有播放均需登录。", "true"),
    "VIDEO_COMMENT_GUEST_PREVIEW": ("未登录用户可见的评论条数；其余需登录查看。", "2"),
    "SECRET_KEY": ("JWT 等签名密钥；生产务必更换为随机长串。", "请改为随机字符串"),
    "JWT_ALGORITHM": ("JWT 签名算法。", "HS256"),
    "JWT_EXPIRE_DAYS": ("登录 Token 有效天数。", "7"),
    "DEFAULT_ADMIN_USERNAME": ("首次无用户时自动创建的管理员用户名。", "admin"),
    "DEFAULT_ADMIN_PASSWORD": ("首次无用户时自动创建的管理员密码；已有用户后仅作占位。", "admin2026"),
    "CORS_ORIGINS": ("跨域来源，逗号分隔；* 表示不限制。", "*"),
    "LOGIN_MAX_ATTEMPTS": ("同一账号在窗口内允许的最大登录失败次数。", "8"),
    "LOGIN_WINDOW_SECONDS": ("登录失败计数统计窗口（秒）。", "300"),
    "LOGIN_LOCK_SECONDS": ("超过失败次数后的锁定时长（秒）。", "600"),
    "BACKUP_EMAIL_ENABLED": ("是否启用每日数据库备份并邮件发送。", "false"),
    "BACKUP_HOUR": ("备份触发小时（0–23），按 BACKUP_TIMEZONE 本地时间。", "3"),
    "BACKUP_MINUTE": ("备份触发分钟（0–59）。", "0"),
    "BACKUP_TIMEZONE": ("备份定时所用 IANA 时区。", "Asia/Shanghai"),
    "MYSQLDUMP_PATH": ("mysqldump 可执行文件路径或命令名。", "mysqldump"),
    "SMTP_HOST": ("发信 SMTP 服务器主机。", "smtp.example.com"),
    "SMTP_PORT": ("SMTP 端口；587 多为 STARTTLS，465 多为 SSL。", "587"),
    "SMTP_USER": ("SMTP 认证用户名（无则留空）。", "noreply@example.com"),
    "SMTP_PASSWORD": ("SMTP 认证密码。", "your_smtp_password"),
    "SMTP_FROM": ("发件人地址；留空则常用 SMTP_USER。", "noreply@example.com"),
    "SMTP_USE_TLS": ("是否使用 STARTTLS（与 SMTP_USE_SSL 二选一常见）。", "true"),
    "SMTP_USE_SSL": ("是否使用隐式 SSL（如 465）；为 true 时用 SMTP_SSL 连接。", "false"),
    "BACKUP_EMAIL_TO": ("备份邮件收件人，多个用英文逗号或分号分隔。", "ops@example.com,backup@example.com"),
    "BACKUP_KEEP_LOCAL_COPY": ("是否在发信后保留一份 ZIP 压缩备份到本地目录。", "false"),
    "BACKUP_LOCAL_DIR": ("本地 ZIP 备份目录（相对则相对运行目录）。", "uploads/db_backups"),
    # Docker Compose 等常用扩展（不在 Settings 内也会被展示）
    "MYSQL_PORT": ("Docker Compose 映射的 MySQL 端口，仅 compose 使用。", "3306"),
    "MYSQL_ROOT_PASSWORD": ("Compose 内 MySQL root 密码。", "root"),
    "MYSQL_DATABASE": ("Compose 内要创建的数据库名。", "lab_system"),
    "MYSQL_USER": ("Compose 内业务数据库用户。", "lab_user"),
    "MYSQL_PASSWORD": ("Compose 内业务数据库密码。", "lab_pass"),
    "REDIS_URL": ("Redis 连接串；留空则不启用。Docker 内常用 redis://redis:6379/0。", "redis://redis:6379/0"),
    "REDIS_PUBLISH_PORT": ("Compose 映射的 Redis 端口。", "6379"),
    "WAIT_FOR_REDIS": ("启动时是否等待 Redis 就绪（Docker 建议 true）。", "true"),
    "REDIS_WAIT_TIMEOUT": ("等待 Redis 的最长秒数。", "30"),
}


def doc_for_key(key_upper: str) -> tuple[str, str]:
    return RUNTIME_ENV_KEY_DOC.get(
        key_upper,
        (
            "扩展变量：未在应用 Settings 中声明，可能由 Docker 或其它工具使用；请自行确认含义。",
            "—",
        ),
    )


def load_full_example_env_text() -> str:
    """优先运行目录旁 .env.example，其次项目只读资源根。"""
    for base in (RUNTIME_ROOT, BUNDLE_ROOT):
        p = base / ".env.example"
        if p.is_file():
            try:
                return p.read_text(encoding="utf-8")
            except OSError:
                continue
    return (
        "# 最小示例（未找到 .env.example 文件时显示）\n"
        "HOST=0.0.0.0\n"
        "PORT=8808\n"
        "DEBUG=true\n"
        "DATABASE_URL=sqlite:///./data/lab_system.db\n"
    )
