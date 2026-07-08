/**
 * 视频播放器：优先 HLS 自适应（hls.js），回退 MP4 Range 渐进播放；弱网缓冲提示。
 */
(function (global) {
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

  /**
   * @param {HTMLElement} container
   * @param {{ mp4Src: string, hlsSrc?: string|null, poster?: string, onPlay?: function }} opts
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
      '  <p class="video-player-mode muted" style="font-size:12px;margin:8px 0 0;"></p>' +
      '  <p class="video-player-error" hidden></p>' +
      "</div>";

    const video = container.querySelector(".video-player-el");
    const overlay = container.querySelector(".video-player-overlay");
    const hint = container.querySelector(".video-player-hint");
    const bar = container.querySelector(".video-player-buffer-bar");
    const errEl = container.querySelector(".video-player-error");
    const modeEl = container.querySelector(".video-player-mode");
    if (!video) return null;

    let playHooked = false;
    let stalledTimer = null;
    let hlsInstance = null;
    let usingHls = false;

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
    }

    function setMode(label) {
      if (modeEl) modeEl.textContent = label;
    }

    function attachMp4() {
      destroyHls();
      usingHls = false;
      video.src = mp4Src;
      setMode("播放模式：MP4 渐进加载");
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
        maxBufferLength: 30,
        maxMaxBufferLength: 120,
        maxBufferHole: 0.5,
        fragLoadingTimeOut: 20000,
        manifestLoadingTimeOut: 15000,
      });
      hlsInstance.loadSource(url);
      hlsInstance.attachMedia(video);
      hlsInstance.on(Hls.Events.MANIFEST_PARSED, function () {
        setMode("播放模式：HLS 自适应（根据网速自动切换清晰度）");
      });
      hlsInstance.on(Hls.Events.ERROR, function (_evt, data) {
        if (!data || !data.fatal) return;
        if (data.type === Hls.ErrorTypes.NETWORK_ERROR) {
          try {
            hlsInstance.startLoad();
            setOverlay(true, "网络中断，正在重连…");
            return;
          } catch (_) {}
        }
        destroyHls();
        attachMp4();
        setOverlay(true, "HLS 加载失败，已切换 MP4…");
        video.load();
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
      attachMp4();
    }

    video.addEventListener("loadedmetadata", updateBar);
    video.addEventListener("progress", updateBar);
    video.addEventListener("timeupdate", updateBar);

    video.addEventListener("play", function () {
      onPlayHook();
      if (video.preload === "metadata") video.preload = "auto";
    });

    video.addEventListener("playing", function () {
      clearStallTimer();
      setOverlay(false);
    });

    video.addEventListener("waiting", function () {
      setOverlay(true, usingHls ? "缓冲中…（HLS 正在加载切片）" : "缓冲中…");
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
        destroyHls();
        attachMp4();
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

    startPlaybackSource();

    return {
      video: video,
      destroy: function () {
        clearStallTimer();
        destroyHls();
      },
    };
  }

  global.VideoPlayer = { mount: mount };
})(window);
