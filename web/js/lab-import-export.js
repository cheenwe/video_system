/**
 * 列表页「导入 / 导出」弹窗（与 test_items 一致：仅管理员显示按钮；导出用 token 查询串）。
 *
 * LabImportExport.attachAdminToolbar(toolbarEl, {
 *   title: "标题",
 *   hintHtml: "<p class='muted'>...</p>",
 *   exportFilename: "xxx.csv",
 *   getExportUrl: () => "/api/foo/csv/export?token=...&a=1",  // 必须返回完整 URL
 *   importUrl: "/api/foo/csv/import",  // 可选；省略则仅导出
 *   importToast: (r) => "自定义成功提示",  // 可选，默认 r.msg
 *   onImported: async () => { await load(); },
 * });
 */
(function (global) {
  var state = {};

  function ensureShell() {
    if (document.getElementById("_labIeMask")) return;
    var mask = document.createElement("div");
    mask.id = "_labIeMask";
    mask.className = "modal-mask";
    mask.style.display = "none";
    mask.innerHTML =
      '<div class="lab-dialog" style="max-width:640px;">' +
      '<div class="head"><h3 id="_labIeTitle">导入 / 导出</h3>' +
      '<button type="button" class="btn ghost" id="_labIeCloseX">\u2715</button></div>' +
      '<div class="body">' +
      '<div id="_labIeHint"></div>' +
      '<div style="display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-top:12px;">' +
      '<a class="btn primary" id="_labIeExport" href="#" target="_blank" rel="noopener">\u5bfc\u51fa CSV</a>' +
      '<span id="_labIeImportWrap"><label class="btn mb-0" style="cursor:pointer;">' +
      "\u9009\u62e9\u6587\u4ef6\u5e76\u5bfc\u5165" +
      '<input id="_labIeFile" type="file" accept=".csv,text/csv" hidden /></label></span>' +
      "</div></div>" +
      '<div class="foot"><button type="button" class="btn" id="_labIeCloseFoot">\u5173\u95ed</button></div>' +
      "</div>";
    document.body.appendChild(mask);

    function close() {
      mask.style.display = "none";
      mask.classList.remove("show");
    }
    document.getElementById("_labIeCloseX").onclick = close;
    document.getElementById("_labIeCloseFoot").onclick = close;
    document.getElementById("_labIeFile").onchange = function (ev) {
      var input = ev.target;
      var file = input.files && input.files[0];
      input.value = "";
      if (!file || !state.importUrl) return;
      var fd = new FormData();
      fd.append("file", file);
      if (!global.LabAPI || typeof global.LabAPI.post !== "function") return;
      global.LabAPI.post(state.importUrl, fd).then(function (r) {
        if (!global.LabAPI.ok(r)) return global.LabAPI.toast(global.LabAPI.msg(r), "error");
        var msg =
          typeof state.importToast === "function"
            ? state.importToast(r)
            : r.msg || "\u5bfc\u5165\u5b8c\u6210";
        global.LabAPI.toast(msg, "success");
        close();
        if (typeof state.onImported === "function") {
          Promise.resolve(state.onImported()).catch(function () {});
        }
      });
    };
  }

  function open(opts) {
    state = opts || {};
    ensureShell();
    var mask = document.getElementById("_labIeMask");
    document.getElementById("_labIeTitle").textContent = state.title || "\u5bfc\u5165 / \u5bfc\u51fa";
    var hint = document.getElementById("_labIeHint");
    hint.innerHTML = state.hintHtml || "";
    var exp = document.getElementById("_labIeExport");
    exp.href = typeof state.getExportUrl === "function" ? state.getExportUrl() : "#";
    var iw = document.getElementById("_labIeImportWrap");
    if (state.importUrl) {
      iw.style.display = "";
    } else {
      iw.style.display = "none";
    }
    mask.style.display = "flex";
    mask.classList.add("show");
  }

  function bindAdminImportExportButton(buttonEl, opts) {
    if (!buttonEl) return;
    if (!global.LabAPI || typeof global.LabAPI.isAdmin !== "function" || !global.LabAPI.isAdmin()) {
      buttonEl.style.display = "none";
      return;
    }
    ensureShell();
    buttonEl.onclick = function () {
      open(opts);
    };
  }

  function attachAdminToolbar(toolbarEl, opts) {
    if (!toolbarEl || !opts) return;
    if (!global.LabAPI || typeof global.LabAPI.isAdmin !== "function" || !global.LabAPI.isAdmin()) return;
    ensureShell();
    if (toolbarEl.querySelector(":scope > .lab-toolbar-import-export")) return;
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "btn sm lab-toolbar-import-export";
    btn.textContent = "\u5bfc\u5165 / \u5bfc\u51fa";
    var primary = Array.from(toolbarEl.querySelectorAll(":scope > .btn.primary")).pop();
    /* 插在主按钮（如「新建」）之前，与 layout 插在主按钮之后的「刷新」组合为：导入/导出 → 新建 → 刷新 */
    if (primary && primary.parentNode === toolbarEl) {
      toolbarEl.insertBefore(btn, primary);
    } else {
      var grow = toolbarEl.querySelector(":scope > .grow");
      if (grow) grow.insertAdjacentElement("afterend", btn);
      else toolbarEl.appendChild(btn);
    }
    btn.onclick = function () {
      open(opts);
    };
    if (global.LabLayout && typeof global.LabLayout.normalizeListToolbarOrders === "function") {
      global.LabLayout.normalizeListToolbarOrders(toolbarEl);
    }
  }

  global.LabImportExport = {
    attachAdminToolbar: attachAdminToolbar,
    bindAdminImportExportButton: bindAdminImportExportButton,
    open: open,
  };
})(window);
