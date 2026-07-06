# lab_system 标准镜像（MySQL 客户端 + 健康检查 curl）
FROM python:3.11-slim

WORKDIR /app

# APT_MIRROR=huawei（默认）使用华为云镜像；海外构建可设 APT_MIRROR=off
ARG APT_MIRROR=huawei
COPY scripts/docker-apt-mirror.sh /tmp/docker-apt-mirror.sh
RUN if [ "$APT_MIRROR" = "huawei" ]; then \
      APT_MIRROR_HOST=mirrors.huaweicloud.com sh /tmp/docker-apt-mirror.sh; \
    fi \
    && apt-get update && apt-get install -y --no-install-recommends \
    default-libmysqlclient-dev \
    gcc \
    curl \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
ARG PIP_MIRROR=huawei
COPY scripts/docker-pip-install.sh /tmp/docker-pip-install.sh
RUN PIP_MIRROR="${PIP_MIRROR}" sh /tmp/docker-pip-install.sh

COPY . .

RUN mkdir -p /app/data /app/uploads \
    && chmod +x scripts/docker-entrypoint.sh scripts/wait-for-tcp.sh

EXPOSE 8808

ENV HOST=0.0.0.0 \
    PORT=8808 \
    PYTHONUNBUFFERED=1 \
    DATABASE_URL=sqlite:///./data/lab_system.db

HEALTHCHECK --interval=15s --timeout=5s --start-period=25s --retries=5 \
    CMD curl -fsS "http://127.0.0.1:8808/api/health" || exit 1

ENTRYPOINT ["sh", "scripts/docker-entrypoint.sh"]
