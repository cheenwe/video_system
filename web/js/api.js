/* 通用 API + 鉴权 */
(function (global) {
  const TOKEN_KEY = "lab_token";
  const USER_KEY = "lab_user";
  let axiosLoader = null;

  function getToken() { return localStorage.getItem(TOKEN_KEY) || ""; }
  function setToken(t) { localStorage.setItem(TOKEN_KEY, t || ""); }
  function getUser() {
    try { return JSON.parse(localStorage.getItem(USER_KEY) || "null"); } catch (_) { return null; }
  }
  function setUser(u) { localStorage.setItem(USER_KEY, JSON.stringify(u || {})); }
  function isAdmin() {
    const u = getUser();
    return !!(u && u.is_admin === true);
  }
  function clearAuth() { localStorage.removeItem(TOKEN_KEY); localStorage.removeItem(USER_KEY); }

  /** 当前用户偏好时区（IANA），默认 UTC；与后端存库 UTC 时间配合做展示转换 */
  function getUserTimezone() {
    try {
      const u = getUser();
      if (!u) return "UTC";
      const z = u.timezone != null ? String(u.timezone).trim() : "";
      return z || "UTC";
    } catch (_) {
      return "UTC";
    }
  }

  /**
   * 将后端日期时间字符串按用户时区格式化为 YYYY-MM-DD HH:mm:ss。
   * 无时区信息的 ISO 串按 UTC 解析（与数据库存 UTC 一致）。
   */
  function formatDateTime(iso) {
    if (iso == null || iso === "") return "";
    let raw = String(iso).trim();
    if (/^\d{4}-\d{2}-\d{2}$/.test(raw)) return raw;
    if (/^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}/.test(raw)) raw = raw.replace(" ", "T");
    if (/T/.test(raw) && !/[zZ]$/.test(raw) && !/[+-]\d\d:?\d\d$/.test(raw)) raw += "Z";
    let d;
    try {
      d = new Date(raw);
    } catch (_) {
      return raw.replace("T", " ").replace(/\.\d{3}Z?$/, "").slice(0, 19);
    }
    if (Number.isNaN(d.getTime())) return String(iso).replace("T", " ").replace(/\.\d{3}Z?$/, "").slice(0, 19);
    const tz = getUserTimezone();
    try {
      const fmt = new Intl.DateTimeFormat("sv-SE", {
        timeZone: tz,
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: false,
      });
      return fmt.format(d).replace(" ", " ");
    } catch (_) {
      return String(iso).replace("T", " ").replace(/\.\d{3}Z?$/, "").slice(0, 19);
    }
  }

  function ensureAxios() {
    if (global.axios) return Promise.resolve(global.axios);
    if (axiosLoader) return axiosLoader;
    axiosLoader = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = "js/axios.min.js";
      script.onload = () => resolve(global.axios);
      script.onerror = () => reject(new Error("axios 加载失败"));
      document.head.appendChild(script);
    });
    return axiosLoader;
  }

  function isGuestHubPage() {
    const p = location.pathname.split("/").pop() || "";
    const name = p.endsWith(".html") ? p.slice(0, -5) : p.replace(/^\//, "");
    return name === "index" || name === "" || name === "video" || name === "album";
  }

  async function request(method, path, body, opts) {
    opts = opts || {};
    const axios = await ensureAxios();
    const headers = Object.assign({}, opts.headers || {});
    const isForm = body && body instanceof FormData;
    const t = getToken();
    if (t) headers["Authorization"] = "Bearer " + t;
    try {
      const resp = await axios({
        method,
        url: path,
        headers,
        data: body === undefined || body === null ? undefined : body,
        transformRequest: isForm ? [(d) => d] : undefined,
        ...(opts.timeout != null ? { timeout: opts.timeout } : {}),
      });
      return resp.data;
    } catch (err) {
      const status = err && err.response && err.response.status;
      if (status === 401) {
        if (!isGuestHubPage()) clearAuth();
        if (
          !location.pathname.endsWith("/login") &&
          !location.pathname.endsWith("login.html") &&
          !isGuestHubPage()
        ) {
          location.href = "login";
        }
        return { success: 0, msg: "未登录", code: 401 };
      }
      if (err && err.response && err.response.data) return err.response.data;
      return { success: 0, msg: (err && err.message) || "网络请求失败", code: err && err.response && err.response.status };
    }
  }

  /** 将后端 msg 转为更易理解的说明（不改变技术类动态信息主体） */
  function friendlyMsg(raw) {
    if (raw == null || raw === "") return "操作未成功，请稍后重试。";
    const t = String(raw).trim();
    const EXACT = {
      未登录: "登录已失效，请重新登录。",
      网络请求失败: "网络异常，请检查连接后重试。",
      请求失败: "操作未成功，请稍后重试。",
      配置项已存在: "该配置编号已存在，请使用其他编号或编辑现有项。",
      配置不存在: "未找到该配置，可能已被删除，请刷新页面。",
      同类型下属性编码已存在: "该类型下已有相同编码的业务属性，请更换编码。",
      属性不存在: "未找到该属性，请刷新后重试。",
      客户不存在: "未找到该客户，请确认已选择有效客户或刷新页面。",
      联系人不存在: "未找到该联系人，请刷新后重试。",
      收样单不存在: "未找到该收样单，可能已被删除。",
      样本不存在: "未找到该样本，请刷新后重试。",
      设备不存在: "未找到该设备。",
      检测记录不存在: "未找到该检测记录。",
      检测项不存在: "未找到该检测项。",
      分类不存在: "未找到该分类。",
      模板不存在: "未找到该报告模板。",
      模板不存在或文件丢失: "模板记录存在但文件缺失，请重新上传模板。",
      默认模板文件不存在: "默认模板文件缺失，请联系管理员或重新上传。",
      模板文件不存在: "模板文件不存在，请重新上传。",
      文件不存在: "请求的文件不存在或已被删除。",
      报告不存在: "未找到该报告。",
      用户不存在: "未找到该用户。",
      分类编号已存在: "该分类编号已存在，请使用其他编号。",
      上级分类不存在: "所选上级分类不存在，请重新选择。",
      上级分类不能为自身: "上级分类不能选自己，请重新选择。",
      "存在子分类，无法删除": "该分类下还有子分类，请先删除或调整子分类后再删此项。",
      "分类下存在检测项，无法删除": "该分类下仍有关联的检测项，请先将检测项移到其他分类或删除检测项。",
      检测项编号已存在: "该检测项编号已存在，请使用其他编号。",
      上级检测项不存在: "所选上级检测项不存在，请重新选择。",
      上级检测项不能为自身: "上级检测项不能选自己，请重新选择。",
      "存在子项，无法删除": "该检测项下还有子项，请先处理子项后再删除。",
      用户名已存在: "该用户名已被占用，请更换。",
      不能删除自己: "不能删除当前登录账号，请由其他管理员操作。",
      "新密码至少 5 位": "新密码至少 5 位，请重新输入。",
      原密码错误: "当前密码不正确，请核对后重试。",
      用户名或密码错误: "用户名或密码不正确。",
      账号已禁用: "该账号已被禁用，请联系管理员。",
      文件为空: "上传文件为空，请选择有效文件。",
      "仅支持 .docx/.doc 模板": "仅支持 Word 模板（.docx 或 .doc）。",
      模板编号已存在: "该模板编号已存在，请更换编号。",
      "文件须为 UTF-8 编码的 CSV": "请用 UTF-8 保存 CSV 后再导入（可用记事本「另存为」选择 UTF-8）。",
      "文件须为 UTF-8 编码的 .env 文本": "请用 UTF-8 保存 .env 后再导入。",
      "CSV 无表头": "导入文件缺少表头行，请使用系统导出的模板。",
      "收样单下没有样本，无法生成报告": "该收样单下没有样本，请先添加样本再生成报告。",
      "仅已检测完成的收样单可生成报告": "请先完成收样单下各样本的检测，再生成报告。",
      需要管理员权限: "该操作仅限管理员。",
      "仅管理员可下载 Word 报告": "下载 Word 报告仅限管理员，可下载 PDF 或联系管理员。",
      "仅管理员可预览 Word 报告；请配置 PDF 后使用预览或下载 PDF": "在线预览 Word 报告仅限管理员；请启用 PDF 转换后预览，或下载 PDF。",
      删除操作需要管理员权限: "删除数据仅限管理员，请联系管理员处理。",
      无效的时区: "时区无效，请从列表中选择标准时区（如 Asia/Shanghai）或填写 UTC。",
    };
    if (EXACT[t]) return EXACT[t];
    if (/^收样单 .+ 已存在$/.test(t)) return "该收样单号已存在，请勿重复提交或修改单号规则。";
    if (/^客户编号 .+ 已存在$/.test(t)) return "该客户编号已被使用，请填写其他编号。";
    if (/^设备编号 .+ 已存在$/.test(t)) return "该设备编号已被使用，请填写其他编号。";
    if (/^登录失败过多/.test(t)) return t + "（多次错误将暂时锁定）";
    if (/^文件过大/.test(t)) return t + "，请压缩或拆分后重试。";
    if (/文件内容与.*类型不匹配/.test(t)) return "文件内容与扩展名不一致，请确认是否为真正的 Word 文档。";
    if (/^参数错误/.test(t)) return "提交内容校验未通过，请检查必填项与格式。" + (t.length > 20 ? "（" + t + "）" : "");
    if (/^第 \d+ 行：/.test(t)) return "导入数据有误：" + t;
    if (/^无法解析分类上级编号/.test(t)) return "导入失败：分类的上级编号在文件中不存在或形成循环，请检查 parent_code。";
    if (/^无法解析检测项上级编号/.test(t)) return "导入失败：检测项的上级编号在文件中不存在或形成循环，请检查 parent_code。";
    if (/：category_code 必填/.test(t)) return "导入失败：检测项必须填写有效的 category_code（分类编号）。";
    if (/Connection unexpectedly closed|ECONNRESET|socket hang up|ERR_CONNECTION|Network Error/i.test(t)) {
      return (
        "连接被意外中断。若出现在「调试：备份邮件」，请检查 .env 中 SMTP：465 端口通常需 SMTP_USE_SSL=true；587 通常 SMTP_USE_SSL=false 且 SMTP_USE_TLS=true；大附件发送较慢属正常。" +
        " 也可在服务器执行：python -m src.jobs.run_backup_email"
      );
    }
    return t;
  }

  function toast(msg, type) {
    // 与 web/js/notify.js（Bootstrap Notify）一致：成功/失败均用角标气泡
    if (window.jQuery && typeof window.jQuery.notify === "function") {
      const m = { success: "success", error: "error", info: "info", warn: "warn", warning: "warn" };
      window.jQuery.notify(msg, m[type] || "info");
      return;
    }
    let wrap = document.querySelector(".toast-wrap");
    if (!wrap) {
      wrap = document.createElement("div");
      wrap.className = "toast-wrap";
      document.body.appendChild(wrap);
    }
    const el = document.createElement("div");
    el.className = "toast " + (type || "info");
    el.textContent = msg;
    wrap.appendChild(el);
    setTimeout(() => { el.style.opacity = "0"; el.style.transition = "opacity 0.4s"; }, 1800);
    setTimeout(() => el.remove(), 2400);
  }

  function ok(r) { return r && r.success === 1; }
  function msg(r, def) {
    return friendlyMsg((r && r.msg) || def || "请求失败");
  }

  global.LabAPI = {
    getToken, setToken, getUser, setUser, clearAuth, isAdmin,
    getUserTimezone, formatDateTime,
    get: (p, opts) => request("GET", p, null, opts),
    post: (p, body, opts) => request("POST", p, body, opts),
    put: (p, body, opts) => request("PUT", p, body, opts),
    patch: (p, body, opts) => request("PATCH", p, body, opts),
    del: (p, opts) => request("DELETE", p, null, opts),
    toast,
    ok, msg, friendlyMsg,
  };
})(window);
