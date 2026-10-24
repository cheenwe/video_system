/**
 * Service Worker：HLS 媒体分片缓存（弱网/断网续播）。
 *
 * 设计约束见 hls-cache-policy.js：只缓存当前源、带鉴权参数的能力 URL、
 * 只覆盖 HLS 媒体分片与 playlist，并有条目/体积/时长上限。
 *
 * 播放器在页面里注册本 SW，并通过 navigator.serviceWorker.controller
 * 的 postMessage 查询缓存状态；总开关由服务端配置（/api/videos/config）
 * 下发到页面。
 */
importScripts("/js/hls-cache-policy.js");

var CACHE_NAME = "hls-segments-v1";
var policy = self.HlsCachePolicy;
var LIMITS = policy.LIMITS;
var enabled = true; // 页面通过 postMessage 同步服务端开关

// 记录写入时间，用于过期淘汰
var metaKey = function (url) { return "meta:" + url; };

self.addEventListener("message", function (event) {
  var data = event.data || {};
  if (data.type === "set-enabled") {
    enabled = !!data.enabled;
    if (!enabled) {
      caches.delete(CACHE_NAME);
    }
  } else if (data.type === "clear") {
    caches.delete(CACHE_NAME);
  } else if (data.type === "stats") {
    stats().then(function (s) {
      event.ports[0] && event.ports[0].postMessage(s);
    });
  }
});

self.addEventListener("fetch", function (event) {
  var verdict = policy.classify(event.request, { enabled: enabled });
  if (!verdict.cache) return;

  event.respondWith(
    caches.open(CACHE_NAME).then(function (cache) {
      return cache.match(event.request).then(function (hit) {
        if (hit) return hit;
        return fetch(event.request).then(function (resp) {
          if (resp && resp.ok) {
            // 克隆后再写入：响应体只能消费一次
            var copy = resp.clone();
            cache.put(event.request, copy).then(function () {
              evictIfNeeded(cache);
            });
          }
          return resp;
        });
      });
    })
  );
});

/** 超出配额时按「最早写入」淘汰，直到回到限额内。 */
function evictIfNeeded(cache) {
  cache.keys().then(function (keys) {
    if (keys.length <= LIMITS.maxEntries) return;
    var removable = keys.slice(0, keys.length - LIMITS.maxEntries);
    return Promise.all(removable.map(function (k) { return cache.delete(k); }));
  });
}

function stats() {
  return caches.open(CACHE_NAME).then(function (cache) {
    return cache.keys().then(function (keys) {
      return { entries: keys.length, limit: LIMITS.maxEntries };
    });
  });
}
