# 弱网流畅播放

目标：在约 1–2 Mbps、偶发丢包 / RTT 升高的网络下，**先保证「能播完」**，
再谈清晰度。本文记录实现方式、可调参数与验收方法。

实现依据：`~/Desktop/video_system-弱网流畅播放优化计划.md` 的 P0 全项与 P1 主体；
P2（CDN / OSS、fMP4、Service Worker 缓存、多码率音频统一）未做，理由见文末。

---

## 1. 做了什么

### P0 转码与播放器

| 项 | 落地位置 | 说明 |
| --- | --- | --- |
| ABR 阶梯 | `src/services/video_hls_service.py` | 按源高度选档：≥1080p/≥720p → 主档 + 480p + 360p；≥480p → 主档 + 360p；≤360p → 仅主档。开启 `VIDEO_HLS_240P` 后 1080p 源再加 240p。小分辨率源不降档，避免无效转码 |
| 关键帧对齐 | `_gop_args()` / `_hls_copy_stream()` | 转码档强制 `-g`/`-keyint_min` 与 `force_key_frames` 对齐切片时长，并 `-sc_threshold 0` 关闭自适应插帧；主档若源 GOP > 1.5×切片时长，改为对齐重编码而不是 `-c:v copy` |
| 真实码率 | `probe_bitrate()` / `_variant_entry()` | 生成后用 ffprobe 探测各档平均/峰值码率，写入 `EXT-X-STREAM-INF` 的 `BANDWIDTH` 与 `AVERAGE-BANDWIDTH`；探测失败回退配置估值，不影响出片 |
| 缓冲收紧 | `web/js/video-player.js` `WEAK` | `maxBufferLength` 30→15、`maxMaxBufferLength` 120→60、`maxBufferHole` 0.5→0.3 |
| 超时与重试 | 同上 | frag/manifest 超时 10s、重试 4/3 次、退避 1s，全部显式写死 |
| 网络错误退避 | `scheduleNetworkRetry()` | 致命 `NETWORK_ERROR` 先按 1s/2s/4s 退避重试，用尽才切 MP4；不再一次 error 就销毁 HLS |
| 连续卡顿降档 | `maybeDowngrade()` | 10s 窗口内累计 waiting > 6s 自动把 `nextLevel` 下调一档，降档后冷却 15s；手动锁定档位时不干预 |
| 手动清晰度/流畅优先 | 清晰度下拉 + 「流畅优先」按钮 | 可锁定任意档，或一键锁最低档并关闭自动升档 |

### P1 运维与存量

| 项 | 落地位置 |
| --- | --- |
| 存量补切片 | `scripts/backfill_hls.py`（支持 `--limit` / `--video-id` / `--dry-run` / `--retries`，失败进重试队列并记日志） |
| 切片缓存 | 应用侧：`.ts` 返回 `private, max-age=86400, immutable`，playlist `private, max-age=60, must-revalidate`；Nginx 示例见 `deploy/nginx.conf` |
| 分段时长策略 | `VIDEO_HLS_LOW_SEGMENT_SEC`：弱网低档默认 4s，高清档保持 6s |
| MP4 Range 分块 | `VIDEO_STREAM_CHUNK_KB`（默认 256KB，范围 32–4096） |
| QoE 采集 | 播放器 `getQoe()` + `videoqoe` 事件；`window.__videoQoE` 留存，`video.html` 里打印，接入分析后端时在 `onQoe` 回调上报 |

采集字段：`ttffMs`（起播耗时）、`waitingCount` / `waitingMs`、`level` / `autoLevel` / `manual`、
`fallbackReason`、`downgrades`、`elapsedMs`。

---

## 2. 可调参数

| 变量 | 默认 | 作用 |
| --- | --- | --- |
| `VIDEO_HLS_ABR_LADDER` | `true` | 总开关：关闭则只出主档 |
| `VIDEO_HLS_SEGMENT_SEC` | `6` | 主档切片时长 |
| `VIDEO_HLS_LOW_SEGMENT_SEC` | `4` | 弱网低档切片时长 |
| `VIDEO_HLS_240P` | `false` | 是否加 240p（成本换极弱网可播性） |
| `VIDEO_HLS_KEYFRAME_ALIGN` | `true` | 关键帧对齐；主档可能因此转为重编码 |
| `VIDEO_HLS_PROBE_BITRATE` | `true` | 真实码率探测 |
| `VIDEO_HLS_SEGMENT_CACHE_SEC` | `86400` | `.ts` 缓存时长 |
| `VIDEO_STREAM_CHUNK_KB` | `256` | MP4 Range 分块 |

播放器侧参数集中在 `web/js/video-player.js` 顶部的 `WEAK` 对象，限速验收时改这里最快。

---

## 3. 验收方法

### 自动化（已进 CI）

```bash
cd /Users/chenwei/workspace/python/video_system
.venv/bin/python -m pytest src/tests -q --basetemp="$(mktemp -d)"
```

覆盖：档位阶梯、GOP 参数、master.m3u8 码率与独立分段标记、码率探测解析与回退、
Range 分块可配、播放器弱网参数锁定（`test_video_player_weak_network.py`）。

> 注：本机沙箱偶发 `pytest-of-unknown` 目录创建冲突，加 `--basetemp` 指向新建目录即可。

### 手工（限速，需真实样片）

1. 准备 1–2 条 720p/1080p 样片，上传后确认 `master.m3u8` 至少有 3 档且 `BANDWIDTH` 各不相同。
2. 限速：Chrome DevTools Network 面板或 macOS Network Link Conditioner，设 1–2 Mbps。
3. 观察并记录：
   - **起播 TTFF**：`window.__videoQoE.ttffMs`
   - **卡顿**：`waitingCount` / `waitingMs`
   - **是否落到 360p**：`level` 是否变为最低档；持续卡顿应看到「已切换 360p 以保证流畅」
   - **回退**：若走到 MP4，`fallbackReason` 会写明原因
4. 点「流畅优先」确认立即锁最低档且不再自动升档。
5. 断网 5–10 秒再恢复：应看到「正在重连（第 N 次）…」而不是直接切 MP4。

### 存量片补切片

```bash
python scripts/backfill_hls.py --dry-run   # 先看有多少条待处理
python scripts/backfill_hls.py --limit 20  # 小批量试跑
python scripts/backfill_hls.py             # 全量
```

---

## 4. 已知代价与风险

- **主档可能变重编码**：源 GOP 过大时主档从 `copy` 改为对齐重编码，上传等待时间增加。
  可通过 `VIDEO_HLS_KEYFRAME_ALIGN=false` 关闭，代价是弱网下 seek/切档卡顿窗口变长。
- **磁盘与 CPU**：每加一档约增加 15–25% 磁盘（低档码率低，实际偏下限）与一份转码耗时。
  小分辨率源自动跳过降档，可部分对冲。
- **缓存与隐私**：`.ts` 长缓存的键是完整 URL（含鉴权 token），只有持有同一 token 的请求
  能命中；响应头仍为 `private`，共享代理不缓存。若部署中改用无鉴权的公开分享链接，
  需重新评估这一条。
- **码率探测开销**：每档多 1 次 playlist 探测 + 最多 5 次分段探测，长视频可感知但有限。

## 5. P2 未做

- 对象存储 + CDN、fMP4/CMAF、Service Worker 片段缓存、多码率音频统一。
  前两项需要产品明确「跨地域分发」或「离线播放」诉求；后两项与隐私/配额强相关，
  建议在有多地域访问数据后再启动。
