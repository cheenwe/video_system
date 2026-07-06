/** 站点品牌：Logo / Favicon / 投稿图标 / 主页色调 / SEO（前台仅应用后台配置） */
(function (global) {
  const DEFAULT_SITE_NAME = "V视频站";
  const DEFAULT_GITHUB_URL = "https://github.com/cheenwe/video_system";
  const DEFAULT_SEO = {
    seo_title: "V视频站 - 在线视频分享与点播",
    seo_description:
      "V视频站提供公开视频推荐、分类浏览、专辑合集与高清在线播放，支持投稿分享优质视频内容。",
    seo_keywords:
      "视频,在线视频,视频分享,高清视频,短视频,视频点播,视频站,公开视频,V视频站,视频推荐",
    seo_robots: "index,follow",
    seo_indexable: true,
    site_url: "",
  };
  let branding = null;

  function esc(s) {
    return String(s || "").replace(/&/g, "&amp;").replace(/"/g, "&quot;");
  }

  function upsertMeta(attr, key, content) {
    if (content == null || content === "") return;
    let el = document.querySelector("meta[" + attr + '="' + key + '"]');
    if (!el) {
      el = document.createElement("meta");
      el.setAttribute(attr, key);
      document.head.appendChild(el);
    }
    el.setAttribute("content", String(content));
  }

  function upsertCanonical(href) {
    if (!href) return;
    let link = document.querySelector('link[rel="canonical"]');
    if (!link) {
      link = document.createElement("link");
      link.rel = "canonical";
      document.head.appendChild(link);
    }
    link.href = href;
  }

  function resolvePageUrl(pathOrFull) {
    const data = getBranding();
    const base = (data.site_url || "").replace(/\/$/, "");
    if (pathOrFull && /^https?:\/\//i.test(pathOrFull)) return pathOrFull;
    const path = pathOrFull || global.location.pathname + global.location.search;
    if (base) return base + (path.startsWith("/") ? path : "/" + path);
    return global.location.origin + (path.startsWith("/") ? path : "/" + path);
  }

  /**
   * @param {object} [pageOpts]
   * @param {string} [pageOpts.title]
   * @param {string} [pageOpts.description]
   * @param {string} [pageOpts.keywords]
   * @param {string} [pageOpts.image]
   * @param {string} [pageOpts.url]
   * @param {string} [pageOpts.canonical]
   * @param {string} [pageOpts.ogType]
   */
  function applySeo(pageOpts) {
    pageOpts = pageOpts || {};
    const data = getBranding();
    const siteName = data.site_name || DEFAULT_SITE_NAME;
    const title =
      pageOpts.title ||
      data.seo_title ||
      siteName + " - 在线视频";
    const description = pageOpts.description || data.seo_description || DEFAULT_SEO.seo_description;
    const keywords = pageOpts.keywords || data.seo_keywords || DEFAULT_SEO.seo_keywords;
    const indexable = data.seo_indexable !== false;
    const robots = indexable
      ? data.seo_robots || DEFAULT_SEO.seo_robots
      : "noindex,nofollow";
    const url = resolvePageUrl(pageOpts.url || pageOpts.canonical);
    const canonical = resolvePageUrl(pageOpts.canonical || pageOpts.url);
    const image = pageOpts.image || data.logo_url || "";

    document.title = title;
    upsertMeta("name", "description", description);
    upsertMeta("name", "keywords", keywords);
    upsertMeta("name", "robots", robots);
    upsertMeta("property", "og:title", pageOpts.ogTitle || title);
    upsertMeta("property", "og:description", pageOpts.ogDescription || description);
    upsertMeta("property", "og:type", pageOpts.ogType || "website");
    upsertMeta("property", "og:url", url);
    upsertMeta("property", "og:site_name", siteName);
    if (image) upsertMeta("property", "og:image", image.startsWith("http") ? image : resolvePageUrl(image));
    upsertMeta("name", "twitter:card", image ? "summary_large_image" : "summary");
    upsertMeta("name", "twitter:title", title);
    upsertMeta("name", "twitter:description", description);
    upsertCanonical(canonical);
  }

  async function loadBranding(force) {
    if (branding && !force) return branding;
    const r = await global.LabAPI.get("/api/site/branding");
    branding = global.LabAPI.ok(r)
      ? Object.assign({}, DEFAULT_SEO, r.data)
      : Object.assign({ site_name: DEFAULT_SITE_NAME, accent_theme: "pink", github_url: DEFAULT_GITHUB_URL }, DEFAULT_SEO);
    return branding;
  }

  function getBranding() {
    return (
      branding ||
      Object.assign({ site_name: DEFAULT_SITE_NAME, accent_theme: "pink", github_url: DEFAULT_GITHUB_URL }, DEFAULT_SEO)
    );
  }

  function applyAccent(themeId) {
    document.documentElement.setAttribute("data-accent", themeId || "pink");
  }

  function applyFavicon(url) {
    if (!url) return;
    let link = document.querySelector("link[rel='icon']");
    if (!link) {
      link = document.createElement("link");
      link.rel = "icon";
      document.head.appendChild(link);
    }
    link.href = url;
  }

  function applyLogo(data) {
    const wrap = document.getElementById("hubLogoWrap");
    const img = document.getElementById("hubLogoImg");
    const text = document.getElementById("hubLogoText");
    const name = data.site_name || DEFAULT_SITE_NAME;
    const github = (data.github_url || DEFAULT_GITHUB_URL).trim();
    if (wrap && github) {
      wrap.href = github;
      wrap.target = "_blank";
      wrap.rel = "noopener noreferrer";
    }
    if (text) {
      text.textContent = name;
      text.style.display = "";
    }
    if (img && data.logo_url) {
      img.src = data.logo_url;
      img.alt = name;
      img.style.display = "";
    } else if (img) {
      img.style.display = "none";
    }
  }

  function formatCopyright(text) {
    const raw = String(text || "").trim();
    if (!raw) return "";
    return raw.replace(/\{year\}/gi, String(new Date().getFullYear()));
  }

  function applyFooter(data) {
    const page = document.querySelector(".hub-page");
    if (!page) return;
    const text = formatCopyright(data.copyright_text);
    let footer = document.getElementById("hubFooter");
    if (!text) {
      if (footer) footer.remove();
      return;
    }
    if (!footer) {
      footer = document.createElement("footer");
      footer.id = "hubFooter";
      footer.className = "hub-footer";
      page.appendChild(footer);
    }
    footer.textContent = text;
  }

  function uploadButtonHtml(label, href, id) {
    const data = getBranding();
    const icon = data.upload_icon_url
      ? '<img class="hub-upload-icon" src="' + esc(data.upload_icon_url) + '" alt="" />'
      : "";
    const cls = "hub-btn-upload" + (id ? '" id="' + id : "");
    return '<a class="' + cls + '" href="' + href + '">' + icon + esc(label) + "</a>";
  }

  async function init(options) {
    options = options || {};
    const data = await loadBranding();
    applyAccent(data.accent_theme || "pink");
    applyFavicon(data.favicon_url);
    applyLogo(data);
    applyFooter(data);
    applyUploadDropIcon(data.upload_icon_url);
    applySeo(options.seo || {});
    if (options.rerenderActions && typeof global.VideoHub !== "undefined") {
      global.VideoHub.renderHubActions("hubActions");
    }
    return data;
  }

  function applyUploadDropIcon(url) {
    const el = document.getElementById("uploadDropIcon");
    if (!el) return;
    if (url) {
      el.innerHTML = '<img src="' + esc(url) + '" alt="" />';
    } else {
      el.textContent = "↑";
    }
  }

  global.SiteBranding = {
    loadBranding,
    getBranding,
    applyAccent,
    applyLogo,
    applyFavicon,
    applyFooter,
    applySeo,
    uploadButtonHtml,
    applyUploadDropIcon,
    init,
  };
})(window);
