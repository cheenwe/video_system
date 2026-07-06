#!/bin/sh
# 将 Debian APT 源切换为华为云镜像（构建环境无法访问 deb.debian.org 时使用）。
set -eu

MIRROR_HOST="${APT_MIRROR_HOST:-mirrors.huaweicloud.com}"

replace_in_file() {
  f="$1"
  [ -f "$f" ] || return 0
  sed -i \
    -e "s@deb.debian.org@${MIRROR_HOST}@g" \
    -e "s@security.debian.org@${MIRROR_HOST}@g" \
    -e "s@ftp.debian.org@${MIRROR_HOST}@g" \
    -e 's@http://@https://@g' \
    "$f"
}

replace_in_file /etc/apt/sources.list.d/debian.sources
replace_in_file /etc/apt/sources.list

for f in /etc/apt/sources.list.d/*.list; do
  replace_in_file "$f"
done
