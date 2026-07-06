/**
 * B 站风格视频投稿（断点续传 + 分类/专辑手输自动创建）
 */
(function (global) {
  const LS_KEY = "video_upload_session";
  let categories = [];
  let albums = [];
  let uploadId = null;
  let uploadReady = false;
  let uploading = false;
  let coverBlob = null;
  let coverPreviewUrl = null;

  function saveSession(data) {
    try { localStorage.setItem(LS_KEY, JSON.stringify(data)); } catch (_) {}
  }

  function loadSession() {
    try {
      const raw = localStorage.getItem(LS_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch (_) {
      return null;
    }
  }

  function clearSession() {
    try { localStorage.removeItem(LS_KEY); } catch (_) {}
  }

  function esc(s) {
    return String(s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;");
  }

  function setProgress(pct) {
    const el = document.getElementById("progressInner");
    const pctEl = document.getElementById("uploadPct");
    const v = Math.min(100, Math.max(0, pct));
    if (el) el.style.width = v + "%";
    if (pctEl) pctEl.textContent = Math.round(v) + "%";
  }

  function setStatus(text, ok) {
    const el = document.getElementById("uploadStatus");
    if (!el) return;
    el.textContent = text || "";
    el.classList.toggle("upload-status-ok", !!ok);
  }

  function setStep(step) {
    ["stepUpload", "stepInfo", "stepPublish"].forEach((id, i) => {
      const el = document.getElementById(id);
      if (el) el.classList.toggle("active", i <= step);
    });
  }

  function showFilePanel(name) {
    document.getElementById("dropZone").style.display = "none";
    document.getElementById("filePanel").style.display = "";
    document.getElementById("fileName").textContent = name;
    setStep(1);
  }

  function enablePublishIfReady() {
    const btn = document.getElementById("btnPublish");
    if (btn) btn.disabled = !uploadReady || uploading;
  }

  async function apiRequest(method, path, body) {
    const token = global.LabAPI.getToken();
    const headers = { Authorization: token ? "Bearer " + token : "" };
    const resp = await fetch(path, {
      method,
      headers: method === "PUT" ? Object.assign({ "Content-Type": "application/octet-stream" }, headers) : Object.assign({ "Content-Type": "application/json" }, headers),
      body: method === "PUT" ? body : JSON.stringify(body),
    });
    const data = await resp.json();
    if (resp.status === 401) {
      global.LabAPI.clearAuth();
      location.href = "login?next=video_upload";
    }
    return data;
  }

  async function initUpload(file, chunkSize) {
    const r = await global.LabAPI.post("/api/videos/uploads/init", {
      filename: file.name,
      file_size: file.size,
      mime_type: file.type || "application/octet-stream",
      chunk_size: chunkSize,
    });
    if (!global.LabAPI.ok(r)) throw new Error(global.LabAPI.msg(r));
    return r.data;
  }

  async function fetchStatus(id) {
    const r = await global.LabAPI.get("/api/videos/uploads/" + id);
    if (!global.LabAPI.ok(r)) throw new Error(global.LabAPI.msg(r));
    return r.data;
  }

  async function uploadChunk(id, index, blob) {
    const r = await apiRequest("PUT", `/api/videos/uploads/${id}/chunks/${index}`, blob);
    if (!r || r.success !== 1) throw new Error((r && r.msg) || "分片上传失败");
    return r.data;
  }

  async function uploadCoverBlob(blob) {
    if (!uploadId || !blob) return;
    const token = global.LabAPI.getToken();
    const resp = await fetch("/api/videos/uploads/" + uploadId + "/cover", {
      method: "PUT",
      headers: {
        Authorization: token ? "Bearer " + token : "",
        "Content-Type": "image/jpeg",
      },
      body: blob,
    });
    const data = await resp.json();
    if (!data || data.success !== 1) throw new Error((data && data.msg) || "封面上传失败");
  }

  function renderCoverPreview(blob) {
    const el = document.getElementById("coverPreview");
    const clearBtn = document.getElementById("btnClearCover");
    if (!el) return;
    if (coverPreviewUrl) {
      URL.revokeObjectURL(coverPreviewUrl);
      coverPreviewUrl = null;
    }
    el.innerHTML = "";
    if (blob) {
      coverPreviewUrl = URL.createObjectURL(blob);
      const img = document.createElement("img");
      img.src = coverPreviewUrl;
      img.alt = "封面预览";
      el.appendChild(img);
      if (clearBtn) clearBtn.style.display = "";
    } else {
      const ph = document.createElement("span");
      ph.className = "upload-cover-placeholder";
      ph.innerHTML = "16:9<br />640×360";
      el.appendChild(ph);
      if (clearBtn) clearBtn.style.display = "none";
    }
  }

  async function pickAndCropCover(file) {
    if (!global.VideoCoverCrop) throw new Error("裁剪组件未加载");
    const blob = await global.VideoCoverCrop.open(file);
    coverBlob = blob;
    renderCoverPreview(blob);
    if (uploadId) {
      try {
        await uploadCoverBlob(blob);
        global.LabAPI.toast("封面已保存", "success");
      } catch (e) {
        global.LabAPI.toast(e.message || "封面上传失败", "error");
      }
    }
  }

  async function clearCover() {
    coverBlob = null;
    renderCoverPreview(null);
    if (uploadId) {
      try {
        await global.LabAPI.del("/api/videos/uploads/" + uploadId + "/cover");
      } catch (_) {}
    }
  }

  function bindCoverUpload() {
    const input = document.getElementById("coverInput");
    const pick = document.getElementById("btnPickCover");
    const clearBtn = document.getElementById("btnClearCover");
    pick?.addEventListener("click", () => input?.click());
    clearBtn?.addEventListener("click", clearCover);
    input?.addEventListener("change", async () => {
      const file = input.files && input.files[0];
      input.value = "";
      if (!file) return;
      try {
        await pickAndCropCover(file);
      } catch (e) {
        if (e.message !== "cancelled") global.LabAPI.toast(e.message || "封面处理失败", "error");
      }
    });
  }

  async function loadTaxonomy() {
    if (global.VideoHub) {
      categories = await global.VideoHub.loadCategories();
      albums = await global.VideoHub.loadMyAlbums();
    }
  }

  function filterItems(list, key, query) {
    const q = (query || "").trim().toLowerCase();
    if (!q) return list.slice(0, 8);
    return list.filter((x) => String(x[key]).toLowerCase().includes(q)).slice(0, 8);
  }

  function setupCombobox(inputId, listId, items, labelKey, emptyHint) {
    const input = document.getElementById(inputId);
    const listEl = document.getElementById(listId);
    if (!input || !listEl) return;

    function renderList() {
      const q = input.value.trim();
      const matched = filterItems(items, labelKey, q);
      let html = matched.map((x) =>
        '<button type="button" class="upload-combobox-item" data-val="' + esc(x[labelKey]) + '">' + esc(x[labelKey]) + "</button>"
      ).join("");
      if (q && !matched.some((x) => String(x[labelKey]).toLowerCase() === q.toLowerCase())) {
        html += '<button type="button" class="upload-combobox-item upload-combobox-create" data-create="1" data-val="' + esc(q) + '">+ 创建「' + esc(q) + "」</button>";
      }
      if (!html) html = '<div class="upload-combobox-item" style="cursor:default;color:var(--bili-muted);">' + emptyHint + "</div>";
      listEl.innerHTML = html;
      listEl.classList.add("show");
    }

    input.addEventListener("focus", renderList);
    input.addEventListener("input", renderList);
    input.addEventListener("blur", () => {
      setTimeout(() => listEl.classList.remove("show"), 150);
    });
    listEl.addEventListener("mousedown", (e) => {
      const btn = e.target.closest(".upload-combobox-item[data-val]");
      if (!btn) return;
      e.preventDefault();
      input.value = btn.getAttribute("data-val") || "";
      listEl.classList.remove("show");
    });
  }

  async function uploadFile(file) {
    if (uploading) return;
    uploading = true;
    uploadReady = false;
    enablePublishIfReady();

    const defaultChunk = 5 * 1024 * 1024;
    let session = loadSession();
    let chunkSize, totalChunks, receivedSet;

    showFilePanel(file.name);
    if (!document.getElementById("fTitle").value.trim()) {
      document.getElementById("fTitle").value = file.name.replace(/\.[^.]+$/, "");
    }

    if (session && session.filename === file.name && session.file_size === file.size && session.upload_id) {
      try {
        const st = await fetchStatus(session.upload_id);
        if (st.status === "uploading") {
          uploadId = st.upload_id;
          chunkSize = st.chunk_size;
          totalChunks = st.total_chunks;
          receivedSet = new Set(st.received_chunks || []);
          setProgress((receivedSet.size / totalChunks) * 100);
          setStatus(`续传中 ${receivedSet.size}/${totalChunks} 分片`);
        }
      } catch (_) {
        session = null;
      }
    }

    if (!uploadId) {
      setStatus("正在初始化上传…");
      const init = await initUpload(file, defaultChunk);
      uploadId = init.upload_id;
      chunkSize = init.chunk_size;
      totalChunks = init.total_chunks;
      receivedSet = new Set(init.received_chunks || []);
      saveSession({ upload_id: uploadId, filename: file.name, file_size: file.size, chunk_size: chunkSize, total_chunks: totalChunks });
    }

    for (let i = 0; i < totalChunks; i++) {
      if (receivedSet.has(i)) continue;
      const start = i * chunkSize;
      const end = Math.min(file.size, start + chunkSize);
      setStatus(`上传中 ${i + 1}/${totalChunks} 分片…`);
      await uploadChunk(uploadId, i, file.slice(start, end));
      receivedSet.add(i);
      setProgress((receivedSet.size / totalChunks) * 100);
      saveSession({ upload_id: uploadId, filename: file.name, file_size: file.size, chunk_size: chunkSize, total_chunks: totalChunks });
    }

    setProgress(100);
    setStatus("上传完成，可以投稿了", true);
    uploadReady = true;
    uploading = false;
    setStep(2);
    enablePublishIfReady();
  }

  async function handlePublish() {
    if (!uploadReady || !uploadId) return global.LabAPI.toast("请先完成视频上传", "warn");
    const title = document.getElementById("fTitle").value.trim();
    const description = document.getElementById("fDesc").value.trim();
    const visibility = document.querySelector('input[name="vis"]:checked')?.value || "public";
    const categoryName = document.getElementById("fCategory").value.trim();
    const albumTitle = document.getElementById("fAlbum").value.trim();
    if (!title) return global.LabAPI.toast("请填写标题", "error");

    const btn = document.getElementById("btnPublish");
    btn.disabled = true;
    btn.textContent = "发布中…";

    try {
      if (coverBlob) await uploadCoverBlob(coverBlob);
    } catch (e) {
      global.LabAPI.toast(e.message || "封面上传失败", "error");
      btn.disabled = false;
      btn.textContent = "立即投稿";
      return;
    }

    const body = { upload_id: uploadId, title, description, visibility };
    if (categoryName) body.category_name = categoryName;
    if (albumTitle) body.album_title = albumTitle;

    const r = await global.LabAPI.post("/api/videos", body);
    if (!global.LabAPI.ok(r)) {
      global.LabAPI.toast(global.LabAPI.msg(r), "error");
      btn.disabled = false;
      btn.textContent = "立即投稿";
      return;
    }

    clearSession();
    global.LabAPI.toast("投稿成功！", "success");
    let href = VideoHub.videoPageUrl({ ref: r.data.ref, id: r.data.id });
    if (albumTitle && r.data.albums && r.data.albums[0]) href += "&album=" + r.data.albums[0].id;
    location.href = href;
  }

  function bindDropZone() {
    const zone = document.getElementById("dropZone");
    const input = document.getElementById("fileInput");
    const pick = document.getElementById("btnPickFile");
    if (!zone || !input) return;

    pick?.addEventListener("click", (e) => e.stopPropagation());
    zone.addEventListener("click", (e) => {
      if (e.target.closest("#btnPickFile, label[for='fileInput']")) return;
      input.click();
    });

    ["dragenter", "dragover"].forEach((ev) => {
      zone.addEventListener(ev, (e) => { e.preventDefault(); zone.classList.add("dragover"); });
    });
    ["dragleave", "drop"].forEach((ev) => {
      zone.addEventListener(ev, (e) => { e.preventDefault(); zone.classList.remove("dragover"); });
    });
    zone.addEventListener("drop", (e) => {
      const file = e.dataTransfer?.files?.[0];
      if (file) startUpload(file);
    });

    input.addEventListener("change", () => {
      const file = input.files && input.files[0];
      input.value = "";
      if (file) startUpload(file);
    });
  }

  async function startUpload(file) {
    if (!file.type.startsWith("video/") && !/\.(mp4|mov|mkv|webm|m4v|avi)$/i.test(file.name)) {
      return global.LabAPI.toast("请选择视频文件", "error");
    }
    try {
      await uploadFile(file);
    } catch (e) {
      uploading = false;
      uploadReady = false;
      enablePublishIfReady();
      global.LabAPI.toast(e.message || "上传失败", "error");
    }
  }

  async function init() {
    await loadTaxonomy();
    setupCombobox("fCategory", "catList", categories, "name", "输入分类名称");
    setupCombobox("fAlbum", "albumList", albums, "title", "输入专辑名称");
    bindDropZone();
    bindCoverUpload();
    document.getElementById("btnPublish").addEventListener("click", handlePublish);

    const prev = loadSession();
    if (prev && prev.upload_id) {
      setStatus("检测到未完成上传：「" + prev.filename + "」，请重新选择同一文件续传");
    }
  }

  global.VideoUpload = { init };
})(window);
