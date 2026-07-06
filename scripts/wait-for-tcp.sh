#!/usr/bin/env sh
# 等待 TCP 端口可连接（用于 Docker 内等待 MySQL 就绪）
# 用法: wait-for-tcp.sh host port [timeout_seconds]
set -eu

host="${1:?host required}"
port="${2:?port required}"
timeout="${3:-60}"

i=0
while [ "$i" -lt "$timeout" ]; do
  if python - "$host" "$port" <<'PY'
import socket, sys
h, p = sys.argv[1], int(sys.argv[2])
s = socket.socket()
s.settimeout(2)
try:
    s.connect((h, p))
except OSError:
    sys.exit(1)
finally:
    s.close()
PY
  then
    echo "wait-for-tcp: $host:$port is up"
    exit 0
  fi
  i=$((i + 1))
  echo "wait-for-tcp: waiting for $host:$port ($i/$timeout)..."
  sleep 1
done

echo "wait-for-tcp: timeout waiting for $host:$port" >&2
exit 1
