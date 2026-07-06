/**
 * 渐进式 MP4 播放器：弱网边下边播，显示缓冲进度与状态。
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

  /**
   * @param {HTMLElement} container
   * @param {string} src  流地址（含 token / v 参数）
   * @param {{ onPlay?: function, poster?: string }} [opts]
   */
  function mount(container, src, opts) {
    opts = opts || {};
    if (!container || !src) return null;

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
      '  <p class="video-player-error" hidden></p>' +
      "</div>";

    const shell = container.querySelector(".video-player-shell");
    const video = container.querySelector(".video-player-el");
    const overlay = container.querySelector(".video-player-overlay");
    const hint = container.querySelector(".video-player-hint");
    const bar = container.querySelector(".video-player-buffer-bar");
    const errEl = container.querySelector(".video-player-error");
    if (!video) return null;

    let playHooked = false;
    let stalledTimer = null;

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

    video.src = src;

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
      setOverlay(true, "缓冲中…");
      clearStallTimer();
      stalledTimer = setTimeout(function () {
        if (video.readyState < 3 && !video.paused) {
          setOverlay(true, "网络较慢，正在加载…");
        }
      }, 2500);
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
      clearStallTimer();
      const code = video.error && video.error.code;
      const msg =
        code === 4
          ? "视频格式不受支持，请联系管理员重新转码"
          : "视频加载失败，请检查网络后点击播放重试";
      showError(msg);
    });

    video.addEventListener("click", function () {
      if (video.error) {
        video.load();
        if (errEl) errEl.hidden = true;
      }
    });

    return { video: video, shell: shell };
  }

  global.VideoPlayer = { mount: mount };
})(window);
