/**
 * HLS 片段缓存策略（Service Worker 使用）。
 *
 * 隐私是这里的硬约束，因此规则写得保守：
 * - 只缓存**当前源**的请求，跨域一律不碰；
 * - 只缓存带鉴权参数的能力 URL（token/v），无 token 的公开分享链
 *   默认不缓存，避免「退出登录后仍能放出私有视频」；
 * - 只缓存媒体分片与 playlist，不缓存封面/接口；
 * - 配额上限：条目数与总字节都设上限，超出按 LRU 淘汰；
 * - 总开关关闭时直接透传，不做任何缓存。
 *
 * 抽成独立模块是为了能用 node 跑单元测试（见 scripts/test-hls-cache-policy.js）。
 */
(function (global) {
  "use strict";

  var LIMITS = {
    maxEntries: 400,
    maxBytes: 200 * 1024 * 1024, // 200MB
    maxAgeMs: 6 * 60 * 60 * 1000 // 6 小时
  };

  var CACHEABLE_EXT = [".ts", ".m4s", ".mp4", ".m3u8"];

  function hasAuthParam(url) {
    return /[?&](token|v)=/.test(url.search || "");
  }

  function extOf(pathname) {
    var m = /\.([a-z0-9]+)$/i.exec(pathname || "");
    return m ? "." + m[1].toLowerCase() : "";
  }

  /**
   * 判断一个请求是否应该走缓存。
   * @param {Request} request
   * @param {{enabled: boolean}} options
   * @returns {{cache: boolean, reason: string}}
   */
  function classify(request, options) {
    options = options || {};
    if (options.enabled === false) {
      return { cache: false, reason: "disabled" };
    }
    var url = new URL(request.url);
    if (url.origin !== global.location.origin) {
      return { cache: false, reason: "cross-origin" };
    }
    if (request.method !== "GET") {
      return { cache: false, reason: "method" };
    }
    if (!/\/api\/videos\/\d+\/hls\//.test(url.pathname)) {
      return { cache: false, reason: "not-hls" };
    }
    var ext = extOf(url.pathname);
    if (CACHEABLE_EXT.indexOf(ext) < 0) {
      return { cache: false, reason: "ext" };
    }
    if (!hasAuthParam(url)) {
      // 公开分享链：缓存它等于把「持有链接即可看」扩展到已退出登录的会话
      return { cache: false, reason: "no-auth-param" };
    }
    return { cache: true, reason: "ok" };
  }

  global.HlsCachePolicy = {
    LIMITS: LIMITS,
    classify: classify,
    extOf: extOf,
    hasAuthParam: hasAuthParam
  };
})(typeof window !== "undefined" ? window : self);
