/**
 * hls-cache-policy 的单元测试（node 直跑，无测试框架依赖）。
 * 运行：node scripts/test-hls-cache-policy.js
 *
 * Service Worker 本身无法在 node 里跑，但缓存策略是纯函数，
 * 正是隐私风险所在，因此必须自动化覆盖。
 */
"use strict";

const fs = require("fs");
const path = require("path");

const src = fs.readFileSync(
  path.join(__dirname, "..", "web", "js", "hls-cache-policy.js"),
  "utf8"
);
// 策略文件同时兼容 window/self；在 node 里用 self 作为 global，
// 并补一个 location stub（浏览器里由 window.location 提供）
global.self = global;
global.location = { origin: "https://site.example.com" };
// eslint-disable-next-line no-eval
eval(src);
const policy = global.HlsCachePolicy;

let passed = 0;
let failed = 0;

function req(url, method = "GET") {
  const u = new URL(url, "https://site.example.com");
  return { url: u.href, method, search: u.search };
}

function check(name, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (ok) {
    passed++;
    console.log("PASS", name);
  } else {
    failed++;
    console.log("FAIL", name, "got", JSON.stringify(got), "want", JSON.stringify(want));
  }
}

const HLS = "https://site.example.com/api/videos/7/hls/";

// 1. 带 token 的媒体分片：缓存
check(
  "ts with token is cacheable",
  policy.classify(req(HLS + "stream_1/seg_000.ts?token=abc")).cache,
  true
);
check(
  "m3u8 with access token is cacheable",
  policy.classify(req(HLS + "master.m3u8?token=abc")).cache,
  true
);
check(
  "fmp4 init segment is cacheable",
  policy.classify(req(HLS + "stream_1/init.mp4?v=xyz")).cache,
  true
);

// 2. 无鉴权参数：不缓存（避免退出登录后仍能放出私有视频）
check(
  "segment without auth param is NOT cached",
  policy.classify(req(HLS + "stream_1/seg_000.ts")).cache,
  false
);

// 3. 跨域一律不缓存
check(
  "cross-origin is not cached",
  policy.classify(req("https://cdn.other.com/api/videos/7/hls/seg_000.ts?token=abc")).cache,
  false
);

// 4. 非 HLS 路径（封面、接口）不缓存
check("cover is not cached", policy.classify(req("https://site.example.com/api/videos/7/cover?token=a")).cache, false);
check("api list is not cached", policy.classify(req("https://site.example.com/api/videos?token=a")).cache, false);

// 5. 非 GET 不缓存
check("POST is not cached", policy.classify(req(HLS + "seg.ts?token=a", "POST")).cache, false);

// 6. 非媒体扩展名不缓存
check("unknown ext is not cached", policy.classify(req(HLS + "stream_1/seg_000.bin?token=a")).cache, false);

// 7. 总开关关闭时不缓存
check(
  "disabled switch disables caching",
  policy.classify(req(HLS + "seg_000.ts?token=a"), { enabled: false }).cache,
  false
);

// 8. 扩展名识别
check("extOf ts", policy.extOf("/a/b/seg_000.ts"), ".ts");
check("extOf none", policy.extOf("/a/b/playlist"), "");
check("hasAuthParam v", policy.hasAuthParam({ search: "?v=1" }), true);
check("hasAuthParam none", policy.hasAuthParam({ search: "" }), false);

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
