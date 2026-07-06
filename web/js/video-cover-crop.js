/** 视频封面在线裁剪（固定 16:9，输出 JPEG） */
(function (global) {
  const DEFAULT_W = 640;
  const DEFAULT_H = 360;

  function clamp(v, min, max) {
    return Math.min(max, Math.max(min, v));
  }

  function openCropper(file, options) {
    options = options || {};
    const outW = options.width || DEFAULT_W;
    const outH = options.height || DEFAULT_H;
    const aspect = outW / outH;

    return new Promise(function (resolve, reject) {
      if (!file || !String(file.type || "").startsWith("image/")) {
        reject(new Error("请选择图片文件"));
        return;
      }

      const reader = new FileReader();
      reader.onload = function () {
        const img = new Image();
        img.onload = function () {
          showModal(img, outW, outH, aspect, resolve, reject);
        };
        img.onerror = function () {
          reject(new Error("图片加载失败"));
        };
        img.src = reader.result;
      };
      reader.onerror = function () {
        reject(new Error("读取文件失败"));
      };
      reader.readAsDataURL(file);
    });
  }

  function showModal(img, outW, outH, aspect, resolve, reject) {
    const viewW = Math.min(480, window.innerWidth - 48);
    const viewH = Math.round(viewW / aspect);

    const overlay = document.createElement("div");
    overlay.className = "cover-crop-overlay";
    overlay.innerHTML =
      '<div class="cover-crop-dialog" role="dialog" aria-modal="true">' +
      '<div class="cover-crop-head"><strong>裁剪封面</strong><span class="cover-crop-size">' +
      outW +
      "×" +
      outH +
      "（16:9）</span></div>" +
      '<div class="cover-crop-viewport" id="cropViewport" style="width:' +
      viewW +
      "px;height:" +
      viewH +
      'px">' +
      '<canvas id="cropCanvas"></canvas>' +
      '<div class="cover-crop-mask"></div></div>' +
      '<div class="cover-crop-tools">' +
      '<label class="cover-crop-zoom">缩放<input type="range" id="cropZoom" min="100" max="300" value="100" /></label>' +
      '<span class="cover-crop-hint">拖拽图片调整位置 · 滚轮缩放</span></div>' +
      '<div class="cover-crop-actions">' +
      '<button type="button" class="btn" id="cropCancel">取消</button>' +
      '<button type="button" class="btn primary" id="cropOk">确认裁剪</button></div></div>';

    document.body.appendChild(overlay);
    document.body.style.overflow = "hidden";

    const canvas = overlay.querySelector("#cropCanvas");
    const ctx = canvas.getContext("2d");
    const zoomInput = overlay.querySelector("#cropZoom");
    const viewport = overlay.querySelector("#cropViewport");

    canvas.width = viewW;
    canvas.height = viewH;

    let scale = Math.max(viewW / img.naturalWidth, viewH / img.naturalHeight);
    const minScale = scale;
    let offsetX = (viewW - img.naturalWidth * scale) / 2;
    let offsetY = (viewH - img.naturalHeight * scale) / 2;
    let dragging = false;
    let lastX = 0;
    let lastY = 0;

    function clampOffset() {
      const dw = img.naturalWidth * scale;
      const dh = img.naturalHeight * scale;
      if (dw <= viewW) offsetX = (viewW - dw) / 2;
      else offsetX = clamp(offsetX, viewW - dw, 0);
      if (dh <= viewH) offsetY = (viewH - dh) / 2;
      else offsetY = clamp(offsetY, viewH - dh, 0);
    }

    function draw() {
      ctx.fillStyle = "#111";
      ctx.fillRect(0, 0, viewW, viewH);
      ctx.drawImage(img, offsetX, offsetY, img.naturalWidth * scale, img.naturalHeight * scale);
    }

    function setScale(next) {
      const cx = viewW / 2;
      const cy = viewH / 2;
      const imgX = (cx - offsetX) / scale;
      const imgY = (cy - offsetY) / scale;
      scale = clamp(next, minScale, minScale * 3);
      offsetX = cx - imgX * scale;
      offsetY = cy - imgY * scale;
      clampOffset();
      zoomInput.value = String(Math.round((scale / minScale) * 100));
      draw();
    }

    function exportBlob(done, fail) {
      draw();
      const out = document.createElement("canvas");
      out.width = outW;
      out.height = outH;
      out.getContext("2d").drawImage(canvas, 0, 0, viewW, viewH, 0, 0, outW, outH);
      out.toBlob(
        function (blob) {
          if (blob) done(blob);
          else fail(new Error("裁剪导出失败"));
        },
        "image/jpeg",
        0.92
      );
    }

    function close() {
      overlay.remove();
      document.body.style.overflow = "";
    }

    clampOffset();
    draw();
    zoomInput.value = "100";

    zoomInput.addEventListener("input", function () {
      setScale(minScale * (Number(zoomInput.value) / 100));
    });

    viewport.addEventListener("mousedown", function (e) {
      dragging = true;
      lastX = e.clientX;
      lastY = e.clientY;
    });
    window.addEventListener("mousemove", function (e) {
      if (!dragging) return;
      offsetX += e.clientX - lastX;
      offsetY += e.clientY - lastY;
      lastX = e.clientX;
      lastY = e.clientY;
      clampOffset();
      draw();
    });
    window.addEventListener("mouseup", function () {
      dragging = false;
    });

    viewport.addEventListener(
      "wheel",
      function (e) {
        e.preventDefault();
        const delta = e.deltaY > 0 ? -0.08 : 0.08;
        setScale(scale * (1 + delta));
      },
      { passive: false }
    );

    overlay.querySelector("#cropCancel").addEventListener("click", function () {
      close();
      reject(new Error("cancelled"));
    });

    overlay.querySelector("#cropOk").addEventListener("click", function () {
      exportBlob(
        function (blob) {
          close();
          resolve(blob);
        },
        function (err) {
          global.LabAPI && global.LabAPI.toast(err.message || "裁剪失败", "error");
        }
      );
    });

    overlay.addEventListener("click", function (e) {
      if (e.target === overlay) {
        close();
        reject(new Error("cancelled"));
      }
    });
  }

  global.VideoCoverCrop = {
    open: openCropper,
    DEFAULT_W,
    DEFAULT_H,
  };
})(window);
