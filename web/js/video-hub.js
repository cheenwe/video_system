/** 视频站公共工具 */
(function (global) {
  function esc(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/"/g, "&quot;");
  }

  function formatSize(n) {
    n = Number(n) || 0;
    if (n >= 1024 * 1024 * 1024) return (n / 1024 / 1024 / 1024).toFixed(2) + " GB";
    if (n >= 1024 * 1024) return (n / 1024 / 1024).toFixed(1) + " MB";
    if (n >= 1024) return (n / 1024).toFixed(0) + " KB";
    return n + " B";
  }

  function formatDuration(sec) {
    sec = Number(sec) || 0;
    if (!sec) return "";
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return m + ":" + String(s).padStart(2, "0");
  }

  function formatViews(n) {
    n = Number(n) || 0;
    if (n >= 10000) return (n / 10000).toFixed(1).replace(/\.0$/, "") + "万";
    return String(n);
  }

  function pageAccessV() {
    try {
      return new URLSearchParams(location.search).get("v") || "";
    } catch (_) {
      return "";
    }
  }

  function appendQueryParams(base, params) {
    const parts = [];
    Object.keys(params || {}).forEach((k) => {
      const val = params[k];
      if (val != null && val !== "") parts.push(encodeURIComponent(k) + "=" + encodeURIComponent(String(val)));
    });
    if (!parts.length) return base;
    return base + (base.indexOf("?") >= 0 ? "&" : "?") + parts.join("&");
  }

  function videoPageUrl(video, albumId) {
    let ref;
    if (video && typeof video === "object") {
      ref = video.access_v || video.ref;
    } else {
      ref = video;
    }
    let href = "video?v=" + encodeURIComponent(String(ref || ""));
    if (albumId) href += "&album=" + encodeURIComponent(String(albumId));
    return href;
  }

  function streamUrl(videoId, accessV) {
    const v = accessV != null ? accessV : pageAccessV();
    const params = {};
    const t = global.LabAPI && global.LabAPI.getToken();
    if (t) params.token = t;
    if (v) params.v = v;
    return appendQueryParams("/api/videos/" + videoId + "/stream", params);
  }

  function hlsUrl(videoId, accessV) {
    const v = accessV != null ? accessV : pageAccessV();
    const params = {};
    const t = global.LabAPI && global.LabAPI.getToken();
    if (t) params.token = t;
    if (v) params.v = v;
    return appendQueryParams("/api/videos/" + videoId + "/hls/master.m3u8", params);
  }

  function coverUrl(url, accessV) {
    if (!url) return "";
    const accessToken = accessV != null ? accessV : pageAccessV();
    const params = {};
    const auth = global.LabAPI && global.LabAPI.getToken();
    if (auth) params.token = auth;
    const base = url.indexOf("?") >= 0 ? url.split("?")[0] : url;
    const existing = url.indexOf("?") >= 0 ? url.split("?")[1] : "";
    if (existing) {
      existing.split("&").forEach((pair) => {
        const idx = pair.indexOf("=");
        if (idx <= 0) return;
        const k = decodeURIComponent(pair.slice(0, idx));
        const val = decodeURIComponent(pair.slice(idx + 1));
        if (k === "v" && /^\d+$/.test(val)) return;
        params[k] = val;
      });
    }
    if (accessToken) params.v = accessToken;
    return appendQueryParams(base, params);
  }

  function coverImgHtml(coverUrlRaw, alt, accessV) {
    if (!coverUrlRaw) return "";
    return '<img class="cover-img" src="' + esc(coverUrl(coverUrlRaw, accessV)) + '" alt="' + esc(alt || "") + '" loading="lazy" />';
  }

  function recCoverHtml(coverUrlRaw, alt, accessV) {
    if (!coverUrlRaw) return "";
    return '<img class="rec-cover-img" src="' + esc(coverUrl(coverUrlRaw, accessV)) + '" alt="' + esc(alt || "") + '" loading="lazy" />';
  }

  function isLoggedIn() {
    return !!(global.LabAPI && global.LabAPI.getToken());
  }

  async function loadHubConfig() {
    const r = await global.LabAPI.get("/api/videos/config");
    if (global.LabAPI.ok(r)) return r.data;
    return { allow_anonymous_play: true };
  }

  function renderCard(v, albumId) {
    const visCls = v.visibility === "private" ? "private" : "public";
    const visText = v.visibility === "private" ? "隐私" : "公开";
    const dur = formatDuration(v.duration_sec);
    let href = videoPageUrl(v, albumId);
    return (
      '<a class="hub-card" href="' + href + '">' +
      '<div class="cover">' +
      coverImgHtml(v.cover_url, v.title, v.ref || v.access_v) +
      '<span class="cover-icon">▶</span>' +
      '<span class="vis-tag ' + visCls + '">' + visText + "</span>" +
      (dur ? '<span class="dur">' + dur + "</span>" : "") +
      "</div>" +
      '<div class="info"><div class="title">' + esc(v.title) + "</div>" +
      '<div class="meta">' +
      formatViews(v.view_count) +
      "播放 · " +
      (v.category_name ? esc(v.category_name) + " · " : "") +
      esc(v.uploader_name || "UP主") +
      "</div></div></a>"
    );
  }

  function renderAlbumCard(a) {
    const visText = a.visibility === "private" ? "隐私" : "公开";
    return (
      '<a class="hub-card hub-album-card" href="album?id=' + a.id + '">' +
      '<div class="cover album-cover"><span class="cover-icon">📁</span>' +
      '<span class="vis-tag ' + (a.visibility === "private" ? "private" : "public") + '">' + visText + "</span>" +
      "</div>" +
      '<div class="info"><div class="title">' + esc(a.title) + "</div>" +
      '<div class="meta">' +
      (a.video_count || 0) +
      "个视频 · " +
      esc(a.uploader_name || "UP主") +
      "</div></div></a>"
    );
  }

  async function loadCategories() {
    const r = await global.LabAPI.get("/api/video-categories");
    if (global.LabAPI.ok(r)) return r.data || [];
    return [];
  }

  async function loadMyAlbums() {
    if (!isLoggedIn()) return [];
    const r = await global.LabAPI.get("/api/video-albums?visibility=mine&page_size=100");
    if (global.LabAPI.ok(r)) return (r.data && r.data.items) || [];
    return [];
  }

  function renderCategoryBar(categories, activeId, containerId) {
    const el = document.getElementById(containerId);
    if (!el) return;
    let html = '<button type="button" class="hub-cat' + (!activeId ? " active" : "") + '" data-id="">全部</button>';
    categories.forEach((c) => {
      html +=
        '<button type="button" class="hub-cat' +
        (String(activeId) === String(c.id) ? " active" : "") +
        '" data-id="' +
        c.id +
        '">' +
        esc(c.name) +
        (c.video_count ? " (" + c.video_count + ")" : "") +
        "</button>";
    });
    el.innerHTML = html;
  }

  function hubLoginNext() {
    const page = location.pathname.split("/").pop() || "index";
    const qs = location.search || "";
    return encodeURIComponent(page + qs);
  }

  function bindHubSearch(onSearch) {
    const input = document.getElementById("kw");
    const btn = document.getElementById("btnSearch");
    if (!input || !btn) return;
    const run =
      typeof onSearch === "function"
        ? onSearch
        : function () {
            const kw = input.value.trim();
            location.href = kw ? "index?q=" + encodeURIComponent(kw) : "index";
          };
    btn.addEventListener("click", run);
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") run();
    });
  }

  function renderHubActions(containerId) {
    const el = document.getElementById(containerId);
    if (!el) return;
    const uploadBtn = global.SiteBranding
      ? global.SiteBranding.uploadButtonHtml("投稿", "video_upload", null)
      : '<a class="hub-btn-upload" href="video_upload">投稿</a>';
    const guestUploadBtn = global.SiteBranding
      ? global.SiteBranding.uploadButtonHtml("投稿", "#", "btnUploadGuest")
      : '<a class="hub-btn-upload" href="#" id="btnUploadGuest">投稿</a>';
    const parts = [];
    if (isLoggedIn()) {
      parts.push('<a class="hub-btn-login" href="dashboard">后台管理</a>');
      parts.push(uploadBtn);
    } else {
      parts.push('<a class="hub-btn-login" href="login?next=' + hubLoginNext() + '">登录</a>');
      parts.push(guestUploadBtn);
    }
    el.innerHTML = parts.join("");
    const guest = document.getElementById("btnUploadGuest");
    if (guest) {
      guest.addEventListener("click", (e) => {
        e.preventDefault();
        if (global.LabAPI) LabAPI.toast("上传视频请先登录", "warn");
        location.href = "login?next=video_upload";
      });
    }
  }

  global.VideoHub = {
    esc,
    formatSize,
    formatDuration,
    formatViews,
    streamUrl,
    hlsUrl,
    coverUrl,
    coverImgHtml,
    recCoverHtml,
    videoPageUrl,
    pageAccessV,
    appendQueryParams,
    isLoggedIn,
    loadHubConfig,
    renderCard,
    renderAlbumCard,
    renderHubActions,
    bindHubSearch,
    loadCategories,
    loadMyAlbums,
    renderCategoryBar,
  };
})(window);
