/** 视频分片上传（供投稿页与管理页复用） */
(function (global) {
  async function apiRequest(method, path, body) {
    const token = global.LabAPI && global.LabAPI.getToken();
    const headers = { Authorization: token ? "Bearer " + token : "" };
    const resp = await fetch(path, {
      method,
      headers:
        method === "PUT"
          ? Object.assign({ "Content-Type": "application/octet-stream" }, headers)
          : Object.assign({ "Content-Type": "application/json" }, headers),
      body: method === "PUT" ? body : JSON.stringify(body),
    });
    const data = await resp.json();
    if (resp.status === 401 && global.LabAPI) {
      global.LabAPI.clearAuth();
      location.href = "login?next=" + encodeURIComponent(location.pathname.split("/").pop() || "index");
    }
    return data;
  }

  async function uploadFile(file, opts) {
    opts = opts || {};
    const onProgress = opts.onProgress || function () {};
    const chunkSize = opts.chunkSize || 5 * 1024 * 1024;

    if (!file) throw new Error("请选择视频文件");
    if (
      !String(file.type || "").startsWith("video/") &&
      !/\.(mp4|mov|mkv|webm|m4v|avi)$/i.test(file.name)
    ) {
      throw new Error("请选择视频文件");
    }

    onProgress(0, "正在初始化…");
    const initResp = await global.LabAPI.post("/api/videos/uploads/init", {
      filename: file.name,
      file_size: file.size,
      mime_type: file.type || "application/octet-stream",
      chunk_size: chunkSize,
    });
    if (!global.LabAPI.ok(initResp)) throw new Error(global.LabAPI.msg(initResp));

    const uploadId = initResp.data.upload_id;
    const cs = initResp.data.chunk_size;
    const total = initResp.data.total_chunks;
    const received = new Set(initResp.data.received_chunks || []);

    for (let i = 0; i < total; i++) {
      if (received.has(i)) continue;
      const start = i * cs;
      const end = Math.min(file.size, start + cs);
      onProgress((received.size / total) * 100, "上传中 " + (i + 1) + "/" + total + "…");
      const r = await apiRequest("PUT", "/api/videos/uploads/" + uploadId + "/chunks/" + i, file.slice(start, end));
      if (!r || r.success !== 1) throw new Error((r && r.msg) || "分片上传失败");
      received.add(i);
      onProgress((received.size / total) * 100, "上传中 " + received.size + "/" + total + "…");
    }

    onProgress(100, "上传完成");
    return uploadId;
  }

  global.VideoChunkUpload = { uploadFile };
})(window);
