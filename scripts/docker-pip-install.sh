#!/bin/sh
# Docker / 本地构建时安装 Python 依赖；国内默认使用华为云 PyPI 镜像。
set -eu

PIP_MIRROR="${PIP_MIRROR:-huawei}"
PYTHON="${PYTHON:-python}"

pip_install() {
  "$PYTHON" -m pip install --no-cache-dir --upgrade pip "$@"
  "$PYTHON" -m pip install --no-cache-dir -r requirements.txt "$@"
}

if [ "$PIP_MIRROR" = "huawei" ]; then
  INDEX_URL="${PIP_INDEX_URL:-https://repo.huaweicloud.com/repository/pypi/simple}"
  TRUSTED_HOST="${PIP_TRUSTED_HOST:-repo.huaweicloud.com}"
  echo "pip: using mirror $INDEX_URL"
  pip_install -i "$INDEX_URL" --trusted-host "$TRUSTED_HOST"
else
  echo "pip: using default PyPI"
  pip_install
fi
