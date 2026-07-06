#!/bin/sh
# 本地 / Docker 安装依赖：默认清华 PyPI；PIP_MIRROR=off 时用官方源。
set -eu

PIP_MIRROR="${PIP_MIRROR:-tsinghua}"
PYTHON="${PYTHON:-python}"

if [ "$PIP_MIRROR" = "off" ]; then
  echo "pip: PIP_MIRROR=off"
  "$PYTHON" -m pip install --no-cache-dir -U pip
  "$PYTHON" -m pip install --no-cache-dir -r requirements.txt
  exit 0
fi

echo "pip: Tsinghua mirror"
"$PYTHON" -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple \
  --trusted-host pypi.tuna.tsinghua.edu.cn pip -U
"$PYTHON" -m pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
"$PYTHON" -m pip config set global.trusted-host pypi.tuna.tsinghua.edu.cn
"$PYTHON" -m pip install --no-cache-dir -r requirements.txt
