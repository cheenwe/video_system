#!/usr/bin/env sh
# Docker / 生产容器统一入口：等待数据库 → 迁移（如有）→ 初始化 → 启动 uvicorn
set -eu

cd /app

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8808}"
WEB_CONCURRENCY="${WEB_CONCURRENCY:-1}"

db_url="$(printf '%s' "${DATABASE_URL:-}" | tr 'A-Z' 'a-z')"

if printf '%s' "$db_url" | grep -q '^mysql'; then
  if [ "${WAIT_FOR_DB:-true}" = "true" ]; then
  mysql_host="${MYSQL_HOST:-mysql}"
  mysql_port="${MYSQL_PORT:-3306}"
  sh scripts/wait-for-tcp.sh "$mysql_host" "$mysql_port" "${DB_WAIT_TIMEOUT:-90}"
  fi
fi

if [ -d alembic/versions ] && [ -n "$(ls -A alembic/versions 2>/dev/null)" ]; then
  echo "==> alembic upgrade head"
  alembic upgrade head
else
  echo "==> no alembic revisions, skip migration (tables via init_data)"
fi

echo "==> init database (idempotent)"
python scripts/init_data.py

echo "==> ensure local upload directories"
python -c "from src.core.config import settings; settings.ensure_dirs(); print('upload root:', settings.upload_root_path)"

echo "==> starting uvicorn on ${HOST}:${PORT} (workers=${WEB_CONCURRENCY})"

if [ "$WEB_CONCURRENCY" -gt 1 ] 2>/dev/null; then
  if [ "${BACKUP_EMAIL_ENABLED:-false}" = "true" ]; then
    echo "WARN: WEB_CONCURRENCY>1 时应用内备份调度会多实例重复执行，建议改用 cron: python -m src.jobs.run_backup_email" >&2
  fi
  exec python -m uvicorn src.main:app --host "$HOST" --port "$PORT" --workers "$WEB_CONCURRENCY"
fi

exec python -m uvicorn src.main:app --host "$HOST" --port "$PORT"
