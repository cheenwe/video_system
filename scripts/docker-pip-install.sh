#!/bin/sh
# Docker / 本地安装 Python 依赖；按顺序尝试国内 PyPI 镜像，全部失败再试官方源。
set -eu

PIP_MIRROR="${PIP_MIRROR:-huawei}"
PYTHON="${PYTHON:-python}"

mirror_probe() {
  url="$1"
  if ! command -v curl >/dev/null 2>&1; then
    return 0
  fi
  code=$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 8 --max-time 15 "$url" || echo 000)
  case "$code" in
    200|301|302|304) return 0 ;;
    429)
      echo "pip: skip $url (HTTP 429 限流)"
      return 1
      ;;
    *)
      echo "pip: skip $url (HTTP $code)"
      return 1
      ;;
  esac
}

try_install() {
  index_url="$1"
  trusted_host="$2"
  echo "pip: try $index_url"
  if mirror_probe "$index_url"; then
    if "$PYTHON" -m pip install --no-cache-dir --default-timeout=120 --upgrade pip \
        -i "$index_url" --trusted-host "$trusted_host" \
      && "$PYTHON" -m pip install --no-cache-dir --default-timeout=120 -r requirements.txt \
        -i "$index_url" --trusted-host "$trusted_host"; then
      echo "pip: ok via $trusted_host"
      return 0
    fi
  fi
  echo "pip: failed via $trusted_host"
  return 1
}

if [ "$PIP_MIRROR" = "off" ]; then
  echo "pip: PIP_MIRROR=off, use official PyPI"
  "$PYTHON" -m pip install --no-cache-dir --upgrade pip
  "$PYTHON" -m pip install --no-cache-dir -r requirements.txt
  exit 0
fi

# 清华 → 阿里云 → 腾讯云 → 华为云（部分 IP 对华为云会 429）→ 官方
for pair in \
  "https://pypi.tuna.tsinghua.edu.cn/simple|pypi.tuna.tsinghua.edu.cn" \
  "https://mirrors.aliyun.com/pypi/simple/|mirrors.aliyun.com" \
  "https://mirrors.cloud.tencent.com/pypi/simple|mirrors.cloud.tencent.com" \
  "https://repo.huaweicloud.com/repository/pypi/simple|repo.huaweicloud.com" \
  "https://mirrors.huaweicloud.com/repository/pypi/simple|mirrors.huaweicloud.com"
do
  index_url="${pair%%|*}"
  trusted_host="${pair##*|}"
  if try_install "$index_url" "$trusted_host"; then
    exit 0
  fi
done

echo "pip: all mirrors failed, fallback to official PyPI"
"$PYTHON" -m pip install --no-cache-dir --upgrade pip
"$PYTHON" -m pip install --no-cache-dir -r requirements.txt
