/**
 * 视频播放器：优先 HLS 自适应（hls.js），回退 MP4 Range 渐进播放；弱网流畅优先。
 *
 * 弱网策略（见 docs/weak-network-playback.md）：
 * 1. 收紧缓冲：maxBufferLength/maxMaxBufferLength 取小值，避免把带宽全花在填缓冲上。
 * 2. 显式超时与重试：frag/manifest 超时、重试次数、退避间隔都写死，不依赖默认值。
 * 3. 有限指数退避：致命网络错误先重试 N 次（1s/2s/4s），仍失败才切 MP4，不一次 error 就销毁 HLS。
 * 4. 连续卡顿自动降档：累计 waiting 超过阈值就把 nextLevel 下调一档，弱网下先保流畅。
 * 5. 手动流畅优先：清晰度菜单可强制最低档并关闭自动升档。
 * 6. QoE 采集：TTFF、waiting 次数与累计时长、当前档位、回退原因，供后续分析。
 */
(function (global) {
  // ---------- 弱网策略参数（集中在此，便于限速验收时调整） ----------
  var WEAK = {
    maxBufferLength: 15, // 秒；比默认 30 小，弱网更快起播
    maxMaxBufferLength: 60, // 秒；默认 120，弱网避免过度预取
    maxBufferHole: 0.3,
    fragLoadingTimeOut: 10000,
    manifestLoadingTimeOut: 10000,
    fragLoadingMaxRetry: 4,
    manifestLoadingMaxRetry: 3,
    fragLoadingRetryDelay: 1000,
    fragLoadingMaxRetryTimeout: 8000,
    // 致命网络错误重试次数与退避序列（毫秒）
    networkRetryDelays: [1000, 2000, 4000],
    // 连续卡顿判定：窗口内累计 waiting 超过该值则降档
    stallWindowMs: 10000,
    stallDowngradeMs: 6000,
    // 降档后冷却，避免在临界点反复上下切
    downgradeCooldownMs: 15000
  };

  function esc(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/"/g, "&quot;");
  }

  function bufferPercent(video) {
    if (!video || !isFinite(video.duration) || video.duration <= 0) return 0;
    try {
      if (!video.buffered.length) return 0;
      return Math.min(100, (video.buffered.end(video.buffered.length - 1) / video.duration) * 100);
    } catch (_) {
      return 0;
    }
  }

  function canNativeHls() {
    const v = document.createElement("video");
    return !!(v.canPlayType && v.canPlayType("application/vnd.apple.mpegurl"));
  }

  // ---------- Service Worker 片段缓存 ----------
  var swState = { registered: false, enabled: false };

  function registerServiceWorker(enabled) {
    if (!("serviceWorker" in navigator)) return;
    swState.enabled = !!enabled;
    navigator.serviceWorker.register("/sw.js", { scope: "/" }).then(
      function () {
        swState.registered = true;
        // 把服务端开关同步给 SW；关闭时它会清空缓存并透传
        navigator.serviceWorker.ready.then(function (reg) {
          if (reg.active) {
            reg.active.postMessage({ type: "set-enabled", enabled: swState.enabled });
          }
        });
      },
      function () {
        /* SW 不可用不影响播放 */
      }
    );
  }

  function qoePayload() {
    var base = snapshotQoe();
    base.swCached = swState.registered && swState.enabled;
    return base;
  }

  function now() {
    return Date.now ? Date.now() : +new Date();
  }

  /**
   * @param {HTMLElement} container
   * @param {{ mp4Src: string, hlsSrc?: string|null, poster?: string, onPlay?: function,
   *           onQoe?: function }} opts
   */
  function mount(container, opts) {
    opts = opts || {};
    const mp4Src = opts.mp4Src || opts.src || "";
    const hlsSrc = opts.hlsSrc || null;
    if (!container || !mp4Src) return null;

    container.innerHTML =
      '<div class="video-player-shell">' +
      '  <video class="video-player-el" controls playsinline ' +
      'controlslist="nodownload" disablePictureInPicture preload="metadata"' +
      (opts.poster ? ' poster="' + esc(opts.poster) + '"' : "") +
      "></video>" +
      '  <div class="video-player-overlay" hidden>' +
      '    <div class="video-player-spinner" aria-hidden="true"></div>' +
      '    <p class="video-player-hint">缓冲中…</p>' +
      "  </div>" +
      '  <div class="video-player-buffer-track" aria-hidden="true">' +
      '    <div class="video-player-buffer-bar"></div>' +
      "  </div>" +
      '  <div class="video-player-quality" hidden>' +
      '    <label class="video-player-quality-label" for="video-player-quality-sel">清晰度</label>' +
      '    <select class="video-player-quality-sel">' +
      '      <option value="auto">自动</option>' +
      "    </select>" +
      '    <button class="video-player-quality-smooth" type="button" title="锁定最低清晰度并停止自动升档">流畅优先</button>' +
      "  </div>" +
      '  <p class="video-player-mode muted" style="font-size:12px;margin:8px 0 0;"></p>' +
      '  <div class="video-player-stats" aria-live="polite"></div>' +
      '  <p class="video-player-error" hidden></p>' +
      "</div>";

    const video = container.querySelector(".video-player-el");
    const overlay = container.querySelector(".video-player-overlay");
    const hint = container.querySelector(".video-player-hint");
    const bar = container.querySelector(".video-player-buffer-bar");
    const errEl = container.querySelector(".video-player-error");
    const modeEl = container.querySelector(".video-player-mode");
    const statsEl = container.querySelector(".video-player-stats");
    const qualityBox = container.querySelector(".video-player-quality");
    const qualitySel = container.querySelector(".video-player-quality-sel");
    const smoothBtn = container.querySelector(".video-player-quality-smooth");
    if (!video) return null;

    let playHooked = false;
    let stalledTimer = null;
    let hlsInstance = null;
    let usingHls = false;

    // 重试与降档状态
    let netRetryCount = 0;
    let netRetryTimer = null;
    let waitingSince = 0;
    let stallAccumMs = 0;
    let stallWindowStart = 0;
    let lastDowngradeAt = 0;
    let manualLevel = -1; // -1 = 自动；>=0 锁定该档
    let levels = [];

    // QoE 采集
    const qoe = {
      ttffMs: 0,
      waitingCount: 0,
      waitingMs: 0,
      level: -1,
      autoLevel: -1,
      fallbackReason: "",
      switchedAt: "",
      downgrades: 0
    };
    const startedAt = now();
    let firstPlayingAt = 0;

    function setOverlay(show, text) {
      if (!overlay) return;
      overlay.hidden = !show;
      if (hint && text) hint.textContent = text;
    }

    function updateBar() {
      if (bar) bar.style.width = bufferPercent(video).toFixed(1) + "%";
    }

    function showError(msg) {
      if (errEl) {
        errEl.hidden = false;
        errEl.textContent = msg;
      }
      setOverlay(false);
    }

    function clearStallTimer() {
      if (stalledTimer) {
        clearTimeout(stalledTimer);
        stalledTimer = null;
      }
    }

    function clearNetRetry() {
      if (netRetryTimer) {
        clearTimeout(netRetryTimer);
        netRetryTimer = null;
      }
    }

    function emitQoe() {
      if (typeof opts.onQoe === "function") opts.onQoe(snapshotQoe());
    }

    function snapshotQoe() {
      return {
        swCached: swState.registered && swState.enabled,
        ttffMs: qoe.ttffMs,
        waitingCount: qoe.waitingCount,
        waitingMs: qoe.waitingMs,
        level: manualLevel >= 0 ? manualLevel : qoe.autoLevel,
        autoLevel: qoe.autoLevel,
        manual: manualLevel >= 0,
        fallbackReason: qoe.fallbackReason,
        downgrades: qoe.downgrades,
        elapsedMs: now() - startedAt
      };
    }

    function onPlayHook() {
      if (playHooked) return;
      playHooked = true;
      if (typeof opts.onPlay === "function") opts.onPlay();
    }

    function destroyHls() {
      if (hlsInstance) {
        try {
          hlsInstance.destroy();
        } catch (_) {}
        hlsInstance = null;
      }
      levels = [];
      if (qualityBox) qualityBox.hidden = true;
    }

    function setMode(label) {
      if (modeEl) modeEl.textContent = label;
    }

    // ---------- 实时可观测：码率 / 档位 / 缓冲健康 ----------
    // 让「弱网时到底在播哪档、缓冲够不够」可见，而不是只有一句「缓冲中」。
    var stats = { bytes: 0, since: 0 };
    function fmtKbps(bps) {
      if (!bps || bps <= 0) return "—";
      if (bps >= 1000000) return (bps / 1000000).toFixed(1) + " Mbps";
      return Math.round(bps / 1000) + " kbps";
    }

    function renderStats() {
      if (!statsEl) return;
      var elapsed = (now() - stats.since) / 1000;
      var kbps = elapsed > 1 ? (stats.bytes * 8) / elapsed : 0;
      var lvl = hlsInstance && hlsInstance.currentLevel >= 0 ? levelLabel(hlsInstance.currentLevel) : "自动";
      var buf = bufferPercent(video);
      var sw = swState.registered && swState.enabled ? "SW 缓存开" : "SW 缓存关";
      statsEl.textContent =
        "实测 " + fmtKbps(kbps) + " · 档位 " + lvl + " · 已缓冲 " + buf.toFixed(0) + "% · " + sw;
      // 缓冲过低时高亮，便于现场判断是网络问题还是档位过高
      statsEl.classList.toggle("is-low", buf < 10 && !video.paused);
    }

    // 用 PerformanceObserver 统计分片字节；不可用时退化为不显示实测码率
    function watchTransfer() {
      if (typeof PerformanceObserver !== "function") return;
      try {
        var obs = new PerformanceObserver(function (list) {
          list.getEntries().forEach(function (e) {
            if (e.name && e.name.indexOf("/hls/") >= 0 && e.encodedBodySize) {
              stats.bytes += e.encodedBodySize;
            }
          });
        });
        obs.observe({ entryTypes: ["resource"] });
      } catch (_) {}
    }

    var statsTimer = null;
    function startStatsLoop() {
      if (statsTimer) return;
      watchTransfer();
      stats.since = now();
      statsTimer = setInterval(renderStats, 2000);
    }
    function stopStatsLoop() {
      if (statsTimer) {
        clearInterval(statsTimer);
        statsTimer = null;
      }
    }

    function attachMp4(reason) {
      clearNetRetry();
      destroyHls();
      usingHls = false;
      qoe.fallbackReason = reason || "mp4_fallback";
      video.src = mp4Src;
      setMode(reason ? "播放模式：MP4 渐进加载（" + reason + "）" : "播放模式：MP4 渐进加载");
      emitQoe();
    }

    // ---------- 清晰度 / 流畅优先 ----------
    function levelLabel(idx) {
      const lv = levels[idx];
      if (!lv) return "档位 " + idx;
      return (lv.height || lv.width || "?") + "p";
    }

    function rebuildQualityOptions() {
      if (!qualitySel) return;
      const keep = qualitySel.value;
      qualitySel.innerHTML = '<option value="auto">自动</option>';
      levels.forEach(function (lv, idx) {
        const opt = document.createElement("option");
        opt.value = String(idx);
        opt.textContent = levelLabel(idx);
        qualitySel.appendChild(opt);
      });
      qualitySel.value = keep && keep !== "auto" && levels[Number(keep)] ? keep : "auto";
      if (qualityBox) qualityBox.hidden = levels.length < 2;
      syncSmoothButton();
    }

    function syncSmoothButton() {
      if (!smoothBtn) return;
      const on = manualLevel >= 0;
      smoothBtn.classList.toggle("active", on);
      smoothBtn.textContent = on ? "流畅优先：" + levelLabel(manualLevel) : "流畅优先";
    }

    function applyLevel(idx, why) {
      if (!hlsInstance) return;
      manualLevel = idx;
      if (idx < 0) {
        hlsInstance.nextLevel = -1;
        hlsInstance.autoLevelEnabled = true;
        if (qualitySel) qualitySel.value = "auto";
        setMode("播放模式：HLS 自适应（根据网速自动切换清晰度）");
      } else {
        // 锁定档位并关闭自动升档：弱网下不再被拉回高清
        hlsInstance.autoLevelEnabled = false;
        hlsInstance.currentLevel = idx;
        if (qualitySel) qualitySel.value = String(idx);
        setMode("播放模式：HLS 手动 " + levelLabel(idx) + (why ? "（" + why + "）" : ""));
      }
      syncSmoothButton();
      emitQoe();
    }

    function lowestLevel() {
      if (!levels.length) return -1;
      return levels.length - 1; // hls.js 按码率降序排列，最后一项最低
    }

    // ---------- 自动降档 ----------
    function noteWaiting() {
      qoe.waitingCount++;
      const t = now();
      if (!waitingSince) waitingSince = t;
      if (!stallWindowStart) stallWindowStart = t;
      if (t - stallWindowStart > WEAK.stallWindowMs) {
        // 窗口滑过后重新累计，避免把很久以前的卡顿算进来
        stallWindowStart = t;
        stallAccumMs = 0;
      }
    }

    function notePlaying() {
      const t = now();
      if (waitingSince) {
        stallAccumMs += t - waitingSince;
        qoe.waitingMs += t - waitingSince;
        waitingSince = 0;
      }
      if (!firstPlayingAt) {
        firstPlayingAt = t;
        qoe.ttffMs = t - startedAt;
        emitQoe();
      }
      maybeDowngrade(t);
    }

    function maybeDowngrade(t) {
      if (!hlsInstance || manualLevel >= 0) return; // 手动锁定则不干预
      if (t - lastDowngradeAt < WEAK.downgradeCooldownMs) return;
      if (stallAccumMs < WEAK.stallDowngradeMs) return;
      const current = hlsInstance.currentLevel;
      if (current < 0) current = hlsInstance.nextLevel;
      if (current < 0 || current >= levels.length - 1) return; // 已是最低档
      lastDowngradeAt = t;
      stallAccumMs = 0;
      stallWindowStart = t;
      qoe.downgrades++;
      const target = Math.min(current + 1, levels.length - 1);
      hlsInstance.nextLevel = target;
      setOverlay(true, "网络较慢，已切换到 " + levelLabel(target) + " 以保证流畅");
      emitQoe();
    }

    // ---------- 网络错误：有限退避后再回退 ----------
    function scheduleNetworkRetry() {
      if (netRetryCount >= WEAK.networkRetryDelays.length) {
        attachMp4("HLS 重连失败");
        setOverlay(true, "网络不稳定，已切换 MP4 继续播放");
        video.load();
        return;
      }
      const delay = WEAK.networkRetryDelays[netRetryCount++];
      setOverlay(true, "网络中断，正在重连（第 " + netRetryCount + " 次）…");
      clearNetRetry();
      netRetryTimer = setTimeout(function () {
        netRetryTimer = null;
        if (!hlsInstance) return;
        try {
          hlsInstance.startLoad();
        } catch (_) {
          attachMp4("HLS 重连异常");
          video.load();
        }
      }, delay);
    }

    function onFatal(data) {
      if (!hlsInstance) return;
      if (data && data.type === global.Hls.ErrorTypes.NETWORK_ERROR) {
        scheduleNetworkRetry();
        return;
      }
      // 媒体/其他致命错误无法靠重试解决
      attachMp4(data && data.details ? "HLS 错误：" + data.details : "HLS 错误");
      video.load();
    }

    function attachHlsJs(url) {
      const Hls = global.Hls;
      if (!Hls || !Hls.isSupported()) return false;
      destroyHls();
      usingHls = true;
      hlsInstance = new Hls({
        enableWorker: true,
        lowLatencyMode: false,
        startLevel: -1,
        capLevelToPlayerSize: true,
        maxBufferLength: WEAK.maxBufferLength,
        maxMaxBufferLength: WEAK.maxMaxBufferLength,
        maxBufferHole: WEAK.maxBufferHole,
        fragLoadingTimeOut: WEAK.fragLoadingTimeOut,
        manifestLoadingTimeOut: WEAK.manifestLoadingTimeOut,
        fragLoadingMaxRetry: WEAK.fragLoadingMaxRetry,
        manifestLoadingMaxRetry: WEAK.manifestLoadingMaxRetry,
        fragLoadingRetryDelay: WEAK.fragLoadingRetryDelay,
        fragLoadingMaxRetryTimeout: WEAK.fragLoadingMaxRetryTimeout,
      });
      hlsInstance.loadSource(url);
      hlsInstance.attachMedia(video);

      hlsInstance.on(Hls.Events.MANIFEST_PARSED, function (_e, data) {
        levels = (data && data.levels) || [];
        rebuildQualityOptions();
        setMode("播放模式：HLS 自适应（根据网速自动切换清晰度）");
      });
      hlsInstance.on(Hls.Events.LEVEL_SWITCHED, function (_e, data) {
        qoe.autoLevel = data && data.level >= 0 ? data.level : -1;
        if (manualLevel < 0) {
          setMode(
            "播放模式：HLS 自适应（当前 " +
              levelLabel(qoe.autoLevel) +
              "，根据网速自动切换）"
          );
        }
        emitQoe();
      });
      hlsInstance.on(Hls.Events.ERROR, function (_evt, data) {
        if (!data || !data.fatal) return;
        onFatal(data);
      });
      return true;
    }

    function attachNativeHls(url) {
      destroyHls();
      usingHls = true;
      video.src = url;
      setMode("播放模式：HLS（Safari 原生）");
    }

    function startPlaybackSource() {
      if (hlsSrc) {
        if (global.Hls && global.Hls.isSupported() && attachHlsJs(hlsSrc)) return;
        if (canNativeHls()) {
          attachNativeHls(hlsSrc);
          return;
        }
      }
      attachMp4("");
    }

    // ---------- 事件 ----------
    video.addEventListener("loadedmetadata", updateBar);
    video.addEventListener("progress", updateBar);
    video.addEventListener("timeupdate", updateBar);

    video.addEventListener("play", function () {
      onPlayHook();
      if (video.preload === "metadata") video.preload = "auto";
      startStatsLoop();
    });

    video.addEventListener("playing", function () {
      clearStallTimer();
      setOverlay(false);
      notePlaying();
    });

    video.addEventListener("waiting", function () {
      setOverlay(true, usingHls ? "缓冲中…（HLS 正在加载切片）" : "缓冲中…");
      noteWaiting();
      clearStallTimer();
      stalledTimer = setTimeout(function () {
        if (video.readyState < 3 && !video.paused) {
          setOverlay(true, "网络较慢，正在加载…");
        }
      }, 2000);
    });

    video.addEventListener("stalled", function () {
      setOverlay(true, "网络较慢，正在加载…");
    });

    video.addEventListener("canplay", function () {
      clearStallTimer();
      if (!video.paused) setOverlay(false);
      updateBar();
    });

    video.addEventListener("error", function () {
      if (usingHls && mp4Src) {
        attachMp4("HLS 播放出错");
        video.load();
        setOverlay(true, "已切换 MP4，请点击播放");
        return;
      }
      clearStallTimer();
      const code = video.error && video.error.code;
      const msg =
        code === 4
          ? "视频格式不受支持，请联系管理员重新转码"
          : "视频加载失败，请检查网络后点击播放重试";
      showError(msg);
    });

    video.addEventListener("click", function () {
      if (video.error && errEl && !errEl.hidden) {
        errEl.hidden = true;
        startPlaybackSource();
        video.load();
      }
    });

    if (qualitySel) {
      qualitySel.addEventListener("change", function () {
        const v = qualitySel.value;
        applyLevel(v === "auto" ? -1 : Number(v), v === "auto" ? "" : "手动选择");
      });
    }
    if (smoothBtn) {
      smoothBtn.addEventListener("click", function () {
        if (manualLevel >= 0) {
          applyLevel(-1, "");
          return;
        }
        const low = lowestLevel();
        if (low >= 0) applyLevel(low, "流畅优先");
      });
    }

    startPlaybackSource();

    return {
      video: video,
      getQoe: snapshotQoe,
      destroy: function () {
        clearStallTimer();
        clearNetRetry();
        stopStatsLoop();
        destroyHls();
      },
    };
  }

  global.VideoPlayer = { mount: mount, registerServiceWorker: registerServiceWorker };
})(window);
