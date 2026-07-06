/** 播放页点赞 / 收藏 / 分享 */
(function (global) {
  var ICONS = {
    like:
      '<svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor" aria-hidden="true">' +
      '<path d="M1 21h4V9H1v12zm22-11c0-1.1-.9-2-2-2h-6.31l.95-4.57.03-.32c0-.41-.17-.79-.44-1.06L14.17 1 7.59 7.59C7.22 7.95 7 8.45 7 9v10c0 1.1.9 2 2 2h9c.83 0 1.54-.5 1.84-1.22l3.02-7.05c.09-.23.14-.47.14-.73v-2z"/>' +
      "</svg>",
    likeActive:
      '<svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor" aria-hidden="true">' +
      '<path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/>' +
      "</svg>",
    favorite:
      '<svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor" aria-hidden="true">' +
      '<path d="M12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z"/>' +
      "</svg>",
    share:
      '<svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor" aria-hidden="true">' +
      '<path d="M18 16.08c-.76 0-1.44.3-1.96.77L8.91 12.7c.05-.23.09-.46.09-.7s-.04-.47-.09-.7l7.05-4.11c.54.5 1.25.81 2.04.81 1.66 0 3-1.34 3-3s-1.34-3-3-3-3 1.34-3 3c0 .24.04.47.09.7L8.04 9.81C7.5 9.31 6.79 9 6 9c-1.66 0-3 1.34-3 3s1.34 3 3 3c.79 0 1.5-.31 2.04-.81l7.12 4.16c-.05.21-.08.43-.08.65 0 1.61 1.31 2.92 2.92 2.92s2.92-1.31 2.92-2.92-1.31-2.92-2.92-2.92z"/>' +
      "</svg>",
  };

  function formatCount(n) {
    if (global.VideoHub && global.VideoHub.formatViews) return global.VideoHub.formatViews(n);
    n = Number(n) || 0;
    if (n >= 10000) return (n / 10000).toFixed(1).replace(/\.0$/, "") + "万";
    return String(n);
  }

  function loginNext() {
    return "login?next=" + encodeURIComponent(location.pathname + location.search);
  }

  function requireLogin() {
    if (global.VideoHub && global.VideoHub.isLoggedIn && global.VideoHub.isLoggedIn()) return true;
    if (global.LabAPI && global.LabAPI.getToken()) return true;
    if (global.LabAPI) global.LabAPI.toast("请先登录", "warn");
    location.href = loginNext();
    return false;
  }

  function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text);
    }
    return new Promise(function (resolve, reject) {
      var ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed";
      ta.style.left = "-9999px";
      document.body.appendChild(ta);
      ta.select();
      try {
        document.execCommand("copy");
        resolve();
      } catch (e) {
        reject(e);
      } finally {
        document.body.removeChild(ta);
      }
    });
  }

  function buildShareUrl(vToken) {
    var album = new URLSearchParams(location.search).get("album");
    var url = location.origin + location.pathname + "?v=" + encodeURIComponent(vToken);
    if (album) url += "&album=" + encodeURIComponent(album);
    return url;
  }

  function closeShareDialog() {
    var el = document.getElementById("videoShareOverlay");
    if (el) el.remove();
    document.body.style.overflow = "";
  }

  function publicShareUrl(video) {
    var ref = video.ref || video.access_v;
    if (!ref) return "";
    return buildShareUrl(ref);
  }

  async function copyPublicShare(video) {
    var url = publicShareUrl(video);
    if (!url) {
      global.LabAPI.toast("无法生成链接", "error");
      return;
    }
    try {
      await copyText(url);
      global.LabAPI.toast("链接已复制", "success");
    } catch (_) {
      global.LabAPI.toast("复制失败", "error");
    }
  }

  function openShareDialog(video) {
    var canManage = !!video.can_manage;
    var overlay = document.createElement("div");
    overlay.id = "videoShareOverlay";
    overlay.className = "video-share-overlay";
    overlay.innerHTML =
      '<div class="video-share-dialog" role="dialog" aria-modal="true">' +
      '<div class="video-share-head"><strong>分享视频</strong><button type="button" class="video-share-close" aria-label="关闭">×</button></div>' +
      '<p class="video-share-desc muted">隐私视频分享：可生成需登录链接，或由上传者/管理员创建限时公开链接。</p>' +
      '<div class="video-share-options">' +
      '<label class="video-share-option"><input type="radio" name="shareMode" value="login" checked /> 需登录访问（默认）</label>' +
      (canManage
        ? '<label class="video-share-option"><input type="radio" name="shareMode" value="public" /> 公开访问（免登录，须设置有效期）</label>'
        : "") +
      "</div>" +
      (canManage
        ? '<div class="video-share-expire" id="shareExpireWrap" style="display:none;">' +
          '<label>有效期</label>' +
          '<select id="shareExpireHours">' +
          '<option value="1">1 小时</option>' +
          '<option value="6">6 小时</option>' +
          '<option value="24" selected>24 小时</option>' +
          '<option value="168">7 天</option>' +
          '<option value="720">30 天</option>' +
          "</select></div>"
        : "") +
      '<div class="video-share-result" id="shareResult" style="display:none;">' +
      '<label>分享链接</label>' +
      '<div class="video-share-url-row">' +
      '<input id="shareUrlInput" readonly class="video-share-url-input" />' +
      '<button type="button" class="btn sm primary" id="btnCopyShare">复制</button>' +
      "</div>" +
      '<p class="muted video-share-expire-tip" id="shareExpireTip" style="display:none;"></p>' +
      "</div>" +
      '<div class="video-share-actions">' +
      '<button type="button" class="btn" id="btnShareCancel">取消</button>' +
      '<button type="button" class="btn primary" id="btnShareGenerate">生成链接</button>' +
      "</div></div>";
    document.body.appendChild(overlay);
    document.body.style.overflow = "hidden";

    var expireWrap = overlay.querySelector("#shareExpireWrap");
    overlay.querySelectorAll('input[name="shareMode"]').forEach(function (radio) {
      radio.addEventListener("change", function () {
        if (expireWrap) expireWrap.style.display = radio.value === "public" && radio.checked ? "" : "none";
      });
    });

    overlay.querySelector(".video-share-close").onclick = closeShareDialog;
    overlay.querySelector("#btnShareCancel").onclick = closeShareDialog;
    overlay.addEventListener("click", function (e) {
      if (e.target === overlay) closeShareDialog();
    });

    overlay.querySelector("#btnShareGenerate").onclick = async function () {
      var mode = overlay.querySelector('input[name="shareMode"]:checked');
      var publicAccess = mode && mode.value === "public";
      var btn = overlay.querySelector("#btnShareGenerate");
      btn.disabled = true;
      btn.textContent = "生成中…";
      try {
        if (!publicAccess) {
          var ref = video.ref || video.access_v;
          if (!ref) return global.LabAPI.toast("无法生成链接", "error");
          var loginUrl = buildShareUrl(ref);
          overlay.querySelector("#shareResult").style.display = "";
          overlay.querySelector("#shareUrlInput").value = loginUrl;
          var tip0 = overlay.querySelector("#shareExpireTip");
          tip0.style.display = "";
          tip0.textContent = "访客需登录后才能观看。";
          return;
        }
        if (!requireLogin()) return;
        var body = { public_access: true, expires_hours: Number(overlay.querySelector("#shareExpireHours").value) || 24 };
        var r = await global.LabAPI.post("/api/videos/" + video.id + "/share", body);
        if (!global.LabAPI.ok(r)) {
          global.LabAPI.toast(global.LabAPI.msg(r) || "生成失败", "error");
          return;
        }
        var fullUrl = location.origin + (r.data.path || buildShareUrl(r.data.v));
        overlay.querySelector("#shareResult").style.display = "";
        overlay.querySelector("#shareUrlInput").value = fullUrl;
        var tip = overlay.querySelector("#shareExpireTip");
        tip.style.display = "";
        tip.textContent = "公开链接有效期至：" + (r.data.expires_at || "—") + "（到期后无法免登录观看）";
      } finally {
        btn.disabled = false;
        btn.textContent = "生成链接";
      }
    };

    overlay.querySelector("#btnCopyShare").onclick = async function () {
      var val = overlay.querySelector("#shareUrlInput").value;
      if (!val) return global.LabAPI.toast("请先生成链接", "warn");
      try {
        await copyText(val);
        global.LabAPI.toast("链接已复制", "success");
      } catch (_) {
        global.LabAPI.toast("复制失败", "error");
      }
    };
  }

  function canShare() {
    if (global.VideoHub && global.VideoHub.isLoggedIn) return global.VideoHub.isLoggedIn();
    return !!(global.LabAPI && global.LabAPI.getToken());
  }

  function shareBtnHtml() {
    if (!canShare()) return "";
    return (
      '<button type="button" class="play-tool-btn" data-act="share" aria-label="分享">' +
      '<span class="play-tool-icon">' +
      ICONS.share +
      "</span>" +
      '<span class="play-tool-label">分享</span></button>'
    );
  }

  function renderBar(container, video) {
    var el = typeof container === "string" ? document.getElementById(container) : container;
    if (!el) return;
    el.innerHTML =
      '<div class="play-toolbar">' +
      '<button type="button" class="play-tool-btn' +
      (video.liked ? " active" : "") +
      '" data-act="like" aria-label="点赞">' +
      '<span class="play-tool-icon">' +
      (video.liked ? ICONS.likeActive : ICONS.like) +
      "</span>" +
      '<span class="play-tool-label">点赞</span>' +
      '<span class="play-tool-count" data-field="like_count">' +
      formatCount(video.like_count) +
      "</span></button>" +
      '<button type="button" class="play-tool-btn' +
      (video.favorited ? " active" : "") +
      '" data-act="favorite" aria-label="收藏">' +
      '<span class="play-tool-icon">' +
      ICONS.favorite +
      "</span>" +
      '<span class="play-tool-label">收藏</span>' +
      '<span class="play-tool-count" data-field="favorite_count">' +
      formatCount(video.favorite_count) +
      "</span></button>" +
      shareBtnHtml() +
      "</div>";

    el.querySelector('[data-act="like"]').addEventListener("click", function () {
      toggleLike(video, el);
    });
    el.querySelector('[data-act="favorite"]').addEventListener("click", function () {
      toggleFavorite(video, el);
    });
    var shareEl = el.querySelector('[data-act="share"]');
    if (shareEl) {
      shareEl.addEventListener("click", function () {
        shareVideo(video);
      });
    }
  }

  function updateBar(el, video) {
    var likeBtn = el.querySelector('[data-act="like"]');
    var favBtn = el.querySelector('[data-act="favorite"]');
    if (likeBtn) {
      likeBtn.classList.toggle("active", !!video.liked);
      likeBtn.querySelector(".play-tool-icon").innerHTML = video.liked ? ICONS.likeActive : ICONS.like;
      var lc = likeBtn.querySelector('[data-field="like_count"]');
      if (lc) lc.textContent = formatCount(video.like_count);
    }
    if (favBtn) {
      favBtn.classList.toggle("active", !!video.favorited);
      var fc = favBtn.querySelector('[data-field="favorite_count"]');
      if (fc) fc.textContent = formatCount(video.favorite_count);
    }
  }

  async function toggleLike(video, barEl) {
    if (!requireLogin()) return;
    var r = await global.LabAPI.post("/api/videos/" + video.id + "/like");
    if (!global.LabAPI.ok(r)) {
      global.LabAPI.toast(global.LabAPI.msg(r) || "操作失败", "error");
      return;
    }
    video.liked = !!r.data.liked;
    video.like_count = r.data.like_count;
    updateBar(barEl, video);
  }

  async function toggleFavorite(video, barEl) {
    if (!requireLogin()) return;
    var r = await global.LabAPI.post("/api/videos/" + video.id + "/favorite");
    if (!global.LabAPI.ok(r)) {
      global.LabAPI.toast(global.LabAPI.msg(r) || "操作失败", "error");
      return;
    }
    video.favorited = !!r.data.favorited;
    video.favorite_count = r.data.favorite_count;
    updateBar(barEl, video);
  }

  function shareVideo(video) {
    if (!canShare()) {
      if (global.LabAPI) global.LabAPI.toast("请先登录", "warn");
      return;
    }
    if (video.visibility !== "private") {
      copyPublicShare(video);
      return;
    }
    openShareDialog(video);
  }

  global.VideoInteractions = {
    mount: renderBar,
    share: shareVideo,
  };
})(window);
