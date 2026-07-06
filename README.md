# V视频站

开源仓库：[github.com/cheenwe/video_system](https://github.com/cheenwe/video_system)

### 项目名称

基于 Python 的视频点播网站（FastAPI 版）

### 项目介绍

一个可自部署的视频点播与管理平台，参考 B 站、YouTube 等常见视频站点的浏览与播放体验，实现从投稿、**自动转码**、存储、前台播放到后台运营的一体化能力。前台面向观众与 UP 主，后台面向管理员与内容维护者，适合学习 Web 全栈开发、作为课程作品或内部小型视频库使用。

技术实现采用 **FastAPI + SQLAlchemy** 提供 REST API，前台为原生 HTML / CSS / JavaScript（B 站风格 UI），支持 SQLite / MySQL，可 **Docker Compose** 一键部署（含 **Redis**、**ffmpeg**）。默认端口 **8808**。

### 项目功能

本项目分为 **前台（视频站）** 与 **后台（管理端）** 两部分。

#### 前台功能

- 视频列表展示（公开推荐、分类筛选、关键词搜索）
- 隐私视频专区（登录后可见）
- 视频播放详情（HTML5 流式播放、断点续传、相关推荐 / 专辑分集）
- 视频互动（点赞、收藏、分享；加密播放链接）
- 详情评论（登录发表；游客可预览前 N 条）
- 视频投稿（分片上传、封面裁剪、分类与专辑关联）
- 专辑浏览
- 个人中心（头像、时区、修改密码）
- 登录 / 注册会话（JWT）

#### 后台功能

- 系统概览（数据统计）
- 视频管理（列表、搜索、预览、编辑、删除、替换视频文件）
- 专辑管理（合集创建与维护）
- 分类管理（管理员）
- 评论管理（播放页删除；管理员权限）
- 用户管理（管理员）
- 站点外观（Logo / Favicon / 主题色 / 版权信息）
- 系统配置、操作日志
- 运行环境（`.env`）查看与导出、服务器指标
- 可选定时数据库备份邮件

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | FastAPI、SQLAlchemy 2.x、Alembic |
| 数据库 | SQLite（开发）/ MySQL（生产） |
| 缓存 | Redis 7（Docker Compose 可选启用，健康检查集成） |
| 转码 | ffmpeg / ffprobe（MOV·MKV 等 → MP4 H.264+AAC） |
| 鉴权 | JWT（Header 或 `?token=` 查询参数） |
| 定时任务 | APScheduler（可选数据库备份邮件） |
| 前端 | 原生 HTML / CSS / JavaScript |
| 部署 | Docker Compose、Nginx、systemd |

## 功能说明（补充）

### 视频转码

- 上传 **MOV、MKV、AVI、WebM** 等格式时，提交视频信息后**自动转码**为浏览器可播的 **MP4（H.264 + AAC）**
- 已是 H.264+AAC 的 MOV 等会优先 **重封装**（`-c copy`），速度更快
- 可通过 `VIDEO_TRANSCODE_ENABLED=false` 关闭；裸机 / Docker 均需安装 **ffmpeg**（镜像已内置）
- 详见 **[docs/deploy.md](docs/deploy.md)** §4

### 分享与链接

- 播放地址使用加密参数：`/video?v=<ref>`（不再暴露数字 ID）
- 未登录用户不可分享
- **公开视频**：点击分享直接复制链接
- **隐私视频**：弹窗选择「需登录访问」或「公开访问（限时免登录，上传者/管理员设置有效期）」

### 可见性与权限

- **公开视频**：首页默认展示；是否允许游客播放由 `VIDEO_ALLOW_ANONYMOUS_PLAY` 控制
- **隐私视频**：仅登录用户可见；普通用户仅可管理自己上传的视频，管理员可管理全站

## 适合人群

- Python / Web 后端初学者
- 需要视频上传、播放、管理一体化方案的团队
- 课程设计、毕业设计、面试作品参考
- 希望快速搭建内网或小型公网视频库的场景

## 目录结构

```
video_system/
├── src/
│   ├── main.py              # 应用入口
│   ├── api/                 # 路由（auth / video / site_branding / …）
│   ├── models/              # ORM 模型
│   ├── services/            # 业务逻辑（含 video_transcode_service）
│   ├── core/                # 配置、数据库、Redis、鉴权、异常
│   └── jobs/                # 备份邮件等定时任务
├── web/                     # 静态前端页面与 JS
├── scripts/                 # 初始化、构建、Docker 脚本
├── deploy/                  # Nginx / systemd 示例
├── docs/                    # 部署与用户文档（见下方）
├── alembic/                 # 数据库迁移
├── uploads/                 # 上传根目录（视频、封面、品牌资源等）
├── docker-compose.yml       # app + mysql + redis + nginx
├── Dockerfile               # 标准镜像（MySQL 客户端、ffmpeg）
├── Dockerfile.slim          # 轻量镜像（SQLite）
└── requirements.txt
```

## 快速启动

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # 按需修改 DATABASE_URL、SECRET_KEY 等
# 转码需本机 ffmpeg；Redis 可选（REDIS_URL 留空即禁用）
python scripts/init_data.py        # 建表 + 默认管理员
python -m uvicorn src.main:app --host 0.0.0.0 --port 8808 --reload
```

### 访问地址

| 页面 | URL |
|------|-----|
| 视频首页 | `http://127.0.0.1:8808/` 或 `/index` |
| 播放页 | `http://127.0.0.1:8808/video?v=<ref>` |
| 投稿 | `http://127.0.0.1:8808/video_upload` |
| 登录 | `http://127.0.0.1:8808/login` |
| 管理后台入口 | `http://127.0.0.1:8808/dashboard` |
| API 文档 | `/docs`、`/redoc`（**仅 `DEBUG=true` 时开放**） |

### 默认管理员（首次 `init_data.py` 创建）

| 字段 | 值 |
|------|-----|
| 用户名 | `admin` |
| 密码 | `admin2026` |

生产环境务必修改密码与 `SECRET_KEY`。

## 配置说明（`.env`）

复制 `.env.example` 为 `.env` 后修改。常用项：

| 变量 | 说明 |
|------|------|
| `DEBUG` | 生产设为 `false`（关闭 Swagger） |
| `DATABASE_URL` | `sqlite:///./data/lab_system.db` 或 MySQL 连接串 |
| `SECRET_KEY` | JWT 签名密钥，**生产必须修改** |
| `UPLOAD_ROOT` | 上传根目录，默认 `uploads` |
| `VIDEO_ALLOW_ANONYMOUS_PLAY` | `true` 时游客可播放公开视频 |
| `VIDEO_MAX_UPLOAD_MB` | 单文件上限（默认 5120 MB） |
| `VIDEO_CHUNK_SIZE_MB` | 分片大小（默认 5 MB） |
| `VIDEO_TRANSCODE_ENABLED` | 是否自动转码为 MP4（默认 `true`） |
| `REDIS_URL` | Redis 连接串；Docker 内默认 `redis://redis:6379/0` |
| `BACKUP_EMAIL_*` / `SMTP_*` | 可选定时数据库备份邮件 |
| `APT_MIRROR` | Docker 构建 Debian 源：`huawei`（默认）/ `off` |
| `PIP_MIRROR` | Docker 构建 PyPI：`tsinghua`（默认）/ `off` |

完整说明见 `.env.example` 与 **[docs/deploy.md](docs/deploy.md)**。

## Docker 部署

```bash
cp .env.example .env

# SQLite 单机（含 Redis）
docker compose --profile sqlite up -d --build

# MySQL
docker compose --profile mysql up -d --build

# 生产：MySQL + Nginx 反代
docker compose --profile prod --profile mysql up -d --build

# 健康检查
curl -fsS http://127.0.0.1:8808/api/health
```

或使用 Makefile：`make docker-sqlite` / `make docker-mysql` / `make docker-prod`。

**说明：**

- Compose 会启动 **redis** 服务，并注入 `REDIS_URL`（`.env` 中留空时使用默认 `redis://redis:6379/0`）
- 国内构建默认 **清华 PyPI**（`PIP_MIRROR=tsinghua`）、**华为云 APT**（`APT_MIRROR=huawei`）
- 海外构建：`PIP_MIRROR=off APT_MIRROR=off docker compose --profile sqlite build --no-cache`

详细步骤、转码、Redis、数据卷、Nginx、systemd 见 **[docs/deploy.md](docs/deploy.md)**。

## 文档

| 文档 | 说明 |
|------|------|
| [docs/deploy.md](docs/deploy.md) | 部署指南（Docker、转码、Redis、CI、排障） |
| [docs/系统使用说明手册.md](docs/系统使用说明手册.md) | 面向业务用户的功能与 FAQ |
| [docs/项目目录规范.md](docs/项目目录规范.md) | 仓库目录与模块划分 |

## 测试与构建

```bash
# 单元测试
pytest -q

# Linux 打包
bash scripts/build_linux_package.sh

# Windows 单文件
powershell -ExecutionPolicy Bypass -File scripts/build_windows_exe.ps1
```

## 主要 API 前缀

| 前缀 | 说明 |
|------|-----|
| `/api/health` | 健康检查（配置 Redis 时含 `redis` 状态） |
| `/api/auth` | 登录、个人资料、头像 |
| `/api/videos` | 列表、播放、上传、分享、封面、流 |
| `/api/videos/access?v=` | 按加密引用解析视频详情 |
| `/api/video-categories` | 分类 CRUD |
| `/api/video-albums` | 专辑 CRUD |
| `/api/videos/{id}/comments` | 评论 |
| `/api/site/branding` | 站点外观（公开读 / 管理员写） |
| `/api/dashboard` | 概览统计 |
| `/api/users` | 用户管理 |
| `/api/sys-configs` | 系统配置 |
| `/api/sys-logs` | 操作日志 |

## 许可证

见 [LICENSE](LICENSE)。
