#!/bin/sh
# Docker 构建时安装 Python 依赖；国内默认使用华为云 PyPI 镜像。
set -eu

PIP_MIRROR="${PIP_MIRROR:-huawei}"

pip_install() {
  python -m pip install --no-cache-dir --upgrade pip "$@"
  python -m pip install --no-cache-dir -r requirements.txt "$@"
}

if [ "$PIP_MIRROR" = "huawei" ]; then
  INDEX_URL="${PIP_INDEX_URL:-https://repo.huaweicloud.com/repository/pypi/simple}"
  TRUSTED_HOST="${PIP_TRUSTED_HOST:-repo.huaweicloud.com}"
  pip_install -i "$INDEX_URL" --trusted-host "$TRUSTED_HOST"
else
  pip_install
fi
