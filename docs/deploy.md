# V视频站 部署指南

视频点播 + 用户/配置/日志平台。支持：**本地开发**、**Docker Compose**（含 **Redis**、**ffmpeg 转码**）、**裸机 systemd**、**GitLab CI 镜像**、**PyInstaller 单文件**。

---

## 1. 部署前检查

| 项 | 说明 |
|----|------|
| Python | 3.11+（开发与标准 Docker 镜像） |
| 数据库 | SQLite（单机）或 MySQL 8+（`utf8mb4`） |
| Redis | Docker Compose 默认启动；应用通过 `REDIS_URL` 连接（可选但推荐） |
| ffmpeg | 上传 MOV/MKV 等自动转 MP4；**Docker 镜像已内置**；裸机需自行安装 |
| 磁盘 | 视频/封面/头像/品牌资源均写入 `UPLOAD_ROOT` 本地目录 |
| 密钥 | 生产必须修改 `SECRET_KEY`、`DEFAULT_ADMIN_PASSWORD` |
| 调试 | 生产 `DEBUG=false`（关闭 `/docs`） |
| 反代 | 公网建议 Nginx，`client_max_body_size` ≥ 视频上限 |

---

## 2. 本地开发

```bash
cd video_system
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# 本地可不配 Redis（REDIS_URL 留空）；转码需本机安装 ffmpeg
python scripts/init_data.py
python -m uvicorn src.main:app --host 0.0.0.0 --port 8808 --reload
```

默认管理员：`admin` / `admin2026`（仅首次无用户时创建）。

健康检查：

```bash
curl -fsS http://127.0.0.1:8808/api/health
# 未配置 Redis 时：{"success":1,"msg":"ok"}
# Docker 且 Redis 正常时：{"success":1,"msg":"ok","redis":"ok"}
```

---

## 3. Docker Compose

### 3.1 服务一览

| 服务 | Profile | 说明 |
|------|---------|------|
| `app-sqlite` | `sqlite` | 轻量镜像 + SQLite |
| `app-mysql` | `mysql` | 标准镜像 + MySQL |
| `app-prod` | `prod` | 生产应用（不直接映射端口） |
| `mysql` | `mysql`, `prod` | MySQL 8.0 |
| `redis` | `sqlite`, `mysql`, `prod` | Redis 7（AOF 持久化） |
| `nginx` | `prod` | 内置反代 |

启动顺序（MySQL 模式）：**Redis / MySQL 健康** → 应用等待就绪 → 迁移/初始化 → uvicorn。

### 3.2 SQLite（最快体验）

```bash
cp .env.example .env
# 建议生产改 SECRET_KEY、DEBUG=false
docker compose --profile sqlite up -d --build
curl -fsS http://127.0.0.1:8808/api/health
```

数据卷：`./data`（库）、`./uploads`（上传根）、`redis_data`（Redis 数据）。

### 3.3 MySQL

```bash
cp .env.example .env
# 修改 MYSQL_* 密码；可选 MYSQL_PUBLISH_PORT= 不映射 3306 到宿主机
docker compose --profile mysql up -d --build
```

### 3.4 生产：MySQL + 内置 Nginx

```bash
# 编辑 deploy/nginx.docker.conf 中的 server_name / SSL（或外挂宿主机 Nginx + deploy/nginx.conf）
export DEBUG=false
export SECRET_KEY='请替换为随机长串'
docker compose --profile prod --profile mysql up -d --build
# 对外 HTTP 默认 80 → nginx → app-prod:8808
```

### 3.5 环境变量要点

| 变量 | 默认 | 说明 |
|------|------|------|
| `PORT` | 8808 | **宿主机**映射端口（sqlite/mysql profile） |
| `APP_PORT` | 8808 | 容器内 uvicorn 监听端口 |
| `WEB_CONCURRENCY` | 1 | uvicorn worker 数；>1 时勿依赖应用内备份调度 |
| `WAIT_FOR_DB` | true | MySQL 模式等待数据库就绪 |
| `REDIS_URL` | `redis://redis:6379/0` | Compose 内默认；`.env` 留空时 compose 仍用此默认 |
| `WAIT_FOR_REDIS` | true | 启动时等待 Redis（Docker 建议开启） |
| `REDIS_PUBLISH_PORT` | 6379 | 宿主机映射 Redis 端口 |
| `APT_MIRROR` | `huawei` | 构建时 Debian 源；海外可设 `off` |
| `LAB_SYSTEM_IMAGE` | 本地 build 名 | CI 构建后可改为 Registry 地址 |

### 3.6 本地文件目录（`UPLOAD_ROOT`）

| 子路径 | 内容 |
|--------|------|
| `videos/files/` | 合并/转码后的视频（多为 `.mp4`） |
| `videos/chunks/` | 上传中的分片（完成后自动删除） |
| `videos/covers/` | 视频封面 JPEG |
| `user_avatars/` | 用户头像 |
| `site_branding/` | Logo / Favicon / branding.json |
| `db_backups/` | 可选本地数据库备份 ZIP |

播放与下载均通过 API 从本地磁盘读出，**不使用**对象存储。

### 3.7 常用运维命令

```bash
docker compose --profile mysql logs -f app-mysql
docker compose --profile mysql restart app-mysql
docker compose --profile mysql ps
docker compose --profile mysql down
# 备份：打包 data/ uploads/ 与 mysql_data、redis_data 卷
```

---

## 4. 视频自动转码

上传 **MOV、MKV、AVI、WebM** 等浏览器不友好格式时，在**提交视频信息**阶段同步转码为 **MP4（H.264 + AAC）**，并写入 `duration_sec`。

| 变量 | 默认 | 说明 |
|------|------|------|
| `VIDEO_TRANSCODE_ENABLED` | `true` | 设为 `false` 则原样保存（MOV 可能无法播放） |
| `FFMPEG_BIN` / `FFPROBE_BIN` | `ffmpeg` / `ffprobe` | 可执行文件路径 |
| `VIDEO_TRANSCODE_PRESET` | `fast` | x264 预设 |
| `VIDEO_TRANSCODE_CRF` | `23` | 画质（18–32，越小越好） |
| `VIDEO_TRANSCODE_TIMEOUT_SEC` | `3600` | 单次转码超时（秒） |

逻辑见 `src/services/video_transcode_service.py`。大文件转码耗时较长，可能占用请求时间；后续可结合 Redis 做异步任务队列。

验证容器内 ffmpeg：

```bash
docker compose exec app-sqlite ffmpeg -version
```

---

## 5. Docker 镜像构建说明

| 文件 | 内容 |
|------|------|
| `Dockerfile` | MySQL 客户端库、gcc、curl、**ffmpeg** |
| `Dockerfile.slim` | curl、**ffmpeg**（无 gcc，适合 SQLite） |

国内构建无法访问 `deb.debian.org` 时，默认通过 `scripts/docker-apt-mirror.sh` 切换 **华为云 APT 镜像**（`APT_MIRROR=huawei`）。

`pip install` 默认通过 `scripts/docker-pip-install.sh` 使用 **华为云 PyPI 镜像**（`PIP_MIRROR=huawei`，源地址 `https://repo.huaweicloud.com/repository/pypi/simple`）。海外构建：

```bash
APT_MIRROR=off PIP_MIRROR=off docker compose --profile sqlite up -d --build
```

---

## 6. 裸机 / VM（systemd）

```bash
sudo useradd -r -m -d /opt/video_system video || true
sudo rsync -a --exclude .venv --exclude data --exclude uploads ./ /opt/video_system/
cd /opt/video_system
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
# 安装 ffmpeg：apt install ffmpeg  /  brew install ffmpeg
cp .env.example .env   # 编辑 DATABASE_URL、SECRET_KEY、REDIS_URL 等
.venv/bin/python scripts/init_data.py
sudo cp deploy/lab_system.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now lab_system
```

宿主机 Nginx 参考 `deploy/nginx.conf`（`upstream` 指向 `127.0.0.1:8808`）。

---

## 7. GitLab CI 镜像

流水线构建并推送：

- `Dockerfile` → `$CI_REGISTRY_IMAGE:$SHA` / `:latest`
- `Dockerfile.slim` → `$CI_REGISTRY_IMAGE:$SHA-slim` / `:slim`

拉取运行示例：

```bash
docker pull registry.example.com/group/video_system:latest
docker run -d --name video_system \
  -p 8808:8808 \
  -e DEBUG=false \
  -e SECRET_KEY='...' \
  -e DATABASE_URL='mysql+pymysql://user:pass@db-host:3306/lab_system?charset=utf8mb4' \
  -e REDIS_URL='redis://redis-host:6379/0' \
  -v video_uploads:/app/uploads \
  -v video_data:/app/data \
  registry.example.com/group/video_system:latest
```

Runner 无 Docker 特权时可设 `DOCKER_USE_KANIKO=true` 使用 Kaniko Job。

---

## 8. PyInstaller 单文件

```bash
# Linux / macOS
bash scripts/build_onefile_ci_unix.sh
# Windows
powershell -ExecutionPolicy Bypass -File scripts/build_windows_exe.ps1
```

将 `dist/lab_system_server`（或 `.exe`）放到目标目录，同目录生成 `data/`、`uploads/` 与 `.env`。监听地址由 `.env` 的 `HOST`/`PORT` 决定。单文件模式需自行保证 **ffmpeg** 在 PATH 中（若启用转码）。

---

## 9. 数据库与迁移

- 无 `alembic/versions` 时，表结构由 `init_data.py` → `create_all()` 创建（幂等）。
- 引入正式迁移后，容器入口与手动部署均应执行：`alembic upgrade head`。
- 历史库列变更由 `ensure_schema_compatibility()` 在启动时补齐。

---

## 10. 定时备份邮件

`BACKUP_EMAIL_ENABLED=true` 时：

- **单 worker**（`WEB_CONCURRENCY=1`）：应用内 APScheduler 每日执行。
- **多 worker / 多副本**：改用 cron / K8s CronJob：

```bash
.venv/bin/python -m src.jobs.run_backup_email
```

MySQL 备份需可执行 `mysqldump`（标准 `Dockerfile` 已含客户端库；`slim` 连外部 MySQL 时需自行处理）。

---

## 11. 上线检查清单

- [ ] `SECRET_KEY`、`DEFAULT_ADMIN_PASSWORD` 已修改
- [ ] `DEBUG=false`
- [ ] `GET /api/health` 返回 `ok`（配置 Redis 时 `redis` 为 `ok`）
- [ ] Nginx `client_max_body_size` ≥ `VIDEO_MAX_UPLOAD_MB`
- [ ] `uploads/`、`data/`（及 MySQL/Redis 卷）已纳入备份
- [ ] 上传测试：MP4 直传 + MOV 转码播放正常
- [ ] 默认管理员密码已改或已建新管理员并禁用默认账号

---

## 12. 排障

| 现象 | 处理 |
|------|------|
| 健康检查失败 | `curl http://127.0.0.1:8808/api/health`；查 `docker logs` |
| `redis: down` | `docker compose ps redis`；确认 `REDIS_URL=redis://redis:6379/0` |
| MySQL 连接拒绝 | 确认 `WAIT_FOR_DB=true`、`MYSQL_HOST`；Compose 内应为 `mysql` |
| 上传 413 | 调大 Nginx `client_max_body_size` 与 `VIDEO_MAX_UPLOAD_MB` |
| MOV 无法播放 | 确认 `VIDEO_TRANSCODE_ENABLED=true` 且容器内 `ffmpeg -version` 正常 |
| 转码超时 | 增大 `VIDEO_TRANSCODE_TIMEOUT_SEC` 或压缩源文件 |
| Docker 构建 apt 失败 | 使用默认 `APT_MIRROR=huawei` 或检查网络 |
| Docker 构建 pip 失败 | 使用默认 `PIP_MIRROR=huawei`；或 `PIP_MIRROR=off` 并确保可访问 PyPI |
| 端口不一致 | 容器内以 `PORT`/`APP_PORT` 为准；日志中 uvicorn 行才是实际监听 |
| API 文档 404 | 生产 `DEBUG=false` 为预期行为 |

---

更多业务向说明见 **[系统使用说明手册.md](./系统使用说明手册.md)**。
