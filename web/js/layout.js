/* 通用布局：左侧导航 + 顶栏 */
(function () {
  function disableLegacyNavigation() {
    document.documentElement.setAttribute("data-turbolinks", "false");
    if (window.__labTurbolinksStopped) return;
    if (window.Turbolinks && window.Turbolinks.controller && typeof window.Turbolinks.controller.stop === "function") {
      window.Turbolinks.controller.stop();
      window.__labTurbolinksStopped = true;
    }
  }

  function ensureLegacyAssets() {
    const cssFiles = [
      "css/main-vendors.css",
      "css/selectize.default.css",
      "css/main.css",
      "css/demo.css",
      "css/datepicker.min.css",
    ];
    cssFiles.forEach((href) => {
      if (!document.querySelector('link[data-legacy="' + href + '"],link[href="' + href + '"]')) {
        if (!document.querySelector('link[data-preload="' + href + '"]')) {
          const preload = document.createElement("link");
          preload.rel = "preload";
          preload.as = "style";
          preload.href = href;
          preload.dataset.preload = href;
          document.head.appendChild(preload);
        }
        const link = document.createElement("link");
        link.rel = "stylesheet";
        link.href = href;
        link.dataset.legacy = href;
        document.head.appendChild(link);
      }
    });

    // 公共脚本：Bootstrap + 日期控件 + 页面增强
    const jsFiles = [
      "js/application-default.js",
      "js/jquery.slim.min.js",
      "js/notify.js",
      "js/selectize.min.js",
      "js/bootstrap.bundle.min.js",
      "js/datepicker.min.js",
      "js/datepicker.zh-CN.js",
      "js/form-enhance.js",
    ];
    jsFiles.forEach((src) => {
      if (!document.querySelector('script[data-legacy="' + src + '"],script[src="' + src + '"]')) {
        const script = document.createElement("script");
        script.src = src;
        script.async = false;
        script.dataset.legacy = src;
        if (src === "js/application-default.js") {
          script.setAttribute("data-turbolinks-suppress-warning", "");
        }
        document.head.appendChild(script);
      }
    });
  }

  function ensureFavicon() {
    let link = document.querySelector("link[rel='icon']");
    if (!link) {
      link = document.createElement("link");
      link.rel = "icon";
      document.head.appendChild(link);
    }
    link.type = "image/svg+xml";
    link.href = "icon-favicon.svg";
  }

  const NAV = [
    { group: "视频", items: [
      { href: "index", label: "视频首页", icon: "home" },
      { href: "video_upload", label: "上传视频", icon: "upload" },
      { href: "video_system", label: "视频管理", icon: "records" },
      { href: "video_albums", label: "专辑管理", icon: "listDetail" },
      { href: "video_categories", label: "分类管理", icon: "items", admin: true },
    ]},
    { group: "工作台", items: [
      { href: "dashboard", label: "系统概览", icon: "config" },
      { href: "profile", label: "个人中心", icon: "users" },
    ]},
    { group: "系统", items: [
      { href: "site_branding", label: "站点外观", icon: "config", admin: true },
      { href: "sys_configs", label: "系统配置", icon: "config", admin: true },
      { href: "users", label: "用户管理", icon: "users", admin: true },
      { href: "sys_logs", label: "操作日志", icon: "logs", admin: true },
    ]},
  ];

  const ICONS = {
    upload: "M12 16V4m0 12l-4-4m4 4l4-4M4 20h16",
    home: "M3 10.5 12 3l9 7.5v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z",
    clients: "M8 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6zm8 2a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM3 20a5 5 0 0 1 10 0M11 20a5 5 0 0 1 10 0",
    receipts: "M6 3h10l5 5v13a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1zm9 1v5h5M8 13h8M8 17h8",
    records: "M5 4h14a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1zm3 11 3-3 2 2 3-4",
    listDetail: "M5 5h14M5 9h14M5 13h10M5 17h14",
    reports: "M5 4h14v16H5zM8 8h8M8 12h8M8 16h5",
    devices: "M8 5h8v3H8zM6 8h12v10H6zM9 20h6",
    items: "M4 6h16M4 12h16M4 18h10",
    template: "M5 4h14v16H5zM8 8h8M8 12h8M8 16h8",
    config: "M12 8a4 4 0 1 1 0 8 4 4 0 0 1 0-8zm0-5 1.2 2.3 2.6.4-.9 2.5 1.9 1.8-1.9 1.8.9 2.5-2.6.4L12 17l-1.2-2.3-2.6-.4.9-2.5-1.9-1.8 1.9-1.8-.9-2.5 2.6-.4z",
    users: "M12 12a4 4 0 1 0-4-4 4 4 0 0 0 4 4zm-7 8a7 7 0 0 1 14 0",
    logs: "M7 4h10v16H7zM10 8h4M10 12h4M10 16h4",
  };

  function iconSvg(name) {
    const path = ICONS[name] || ICONS.template;
    return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="' + path + '"></path></svg>';
  }

  /** 顶栏用户菜单用小图标（描边，与侧栏 nav-icon 一致） */
  function userMenuIconSvg(pathD) {
    return (
      '<span class="user-dd-icon" aria-hidden="true">' +
      '<svg viewBox="0 0 24 24"><path d="' +
      pathD +
      '" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>' +
      "</span>"
    );
  }

  const USER_MENU_ICON = {
    profile: ICONS.users,
    password: "M7 10.5V8a5 5 0 0 1 10 0v2.5M6 10h12a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2z",
    logout: "M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9",
  };

  function applyTheme(theme) {
    const t = theme === "dark" ? "dark" : "light";
    document.documentElement.setAttribute("data-theme", t);
    try { localStorage.setItem("lab_theme", t); } catch (_) {}
    const toggle = document.getElementById("btnThemeToggle");
    if (toggle) {
      toggle.setAttribute("aria-label", t === "dark" ? "切换浅色模式" : "切换深色模式");
      toggle.setAttribute("title", t === "dark" ? "切换浅色模式" : "切换深色模式");
      toggle.classList.toggle("is-dark", t === "dark");
    }
  }

  function applyStoredTheme() {
    let theme = "light";
    try { theme = localStorage.getItem("lab_theme") || "light"; } catch (_) {}
    applyTheme(theme);
  }

  function applySidebarCollapsed(collapsed) {
    const on = !!collapsed;
    document.documentElement.classList.toggle("sidebar-collapsed", on);
    try { localStorage.setItem("lab_sidebar_collapsed", on ? "1" : "0"); } catch (_) {}
  }

  function applyStoredSidebarState() {
    let collapsed = false;
    try { collapsed = localStorage.getItem("lab_sidebar_collapsed") === "1"; } catch (_) {}
    applySidebarCollapsed(collapsed);
  }

  function setMobileMenuOpen(open) {
    document.documentElement.classList.toggle("sidebar-open", !!open);
  }

  function ensureNavHoverTip() {
    let tip = document.getElementById("navHoverTip");
    if (!tip) {
      tip = document.createElement("div");
      tip.id = "navHoverTip";
      tip.className = "nav-hover-tip";
      document.body.appendChild(tip);
    }
    return tip;
  }

  function bindCollapsedNavTooltip(wrap) {
    const side = wrap.querySelector(".app-side");
    if (!side || side.dataset.tipBound === "1") return;
    side.dataset.tipBound = "1";
    const tip = ensureNavHoverTip();
    let activeAnchor = null;

    const hide = () => {
      tip.classList.remove("show");
      activeAnchor = null;
    };
    const showFor = (a) => {
      if (!a) return hide();
      if (!document.documentElement.classList.contains("sidebar-collapsed")) return hide();
      if (window.matchMedia("(max-width: 900px)").matches) return hide();
      const label = a.dataset.label || "";
      if (!label) return hide();
      const r = a.getBoundingClientRect();
      tip.textContent = label;
      tip.style.left = Math.round(r.right + 10) + "px";
      tip.style.top = Math.round(r.top + r.height / 2) + "px";
      tip.classList.add("show");
      activeAnchor = a;
    };

    side.addEventListener("mouseover", (e) => {
      const a = e.target && e.target.closest ? e.target.closest("a[data-label]") : null;
      if (!a || !side.contains(a)) return;
      showFor(a);
    });
    side.addEventListener("mousemove", (e) => {
      if (!activeAnchor) return;
      const r = activeAnchor.getBoundingClientRect();
      tip.style.left = Math.round(r.right + 10) + "px";
      tip.style.top = Math.round(r.top + r.height / 2) + "px";
    });
    side.addEventListener("mouseout", (e) => {
      if (!activeAnchor) return;
      const to = e.relatedTarget;
      if (to && activeAnchor.contains(to)) return;
      if (to && side.contains(to)) {
        const nextA = to.closest ? to.closest("a[data-label]") : null;
        if (nextA) return;
      }
      hide();
    });
    window.addEventListener("scroll", hide, true);
    window.addEventListener("resize", hide);
  }

  const TOOLBAR_REFRESH_SVG =
    '<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" focusable="false" fill="none">' +
    '<path stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" ' +
    'd="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/>' +
    '<path stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" d="M21 3v5h-5"/>' +
    '<path stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" ' +
    'd="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/>' +
    '<path stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" d="M3 21v-5h5"/>' +
    "</svg>";

  /** 列表工具栏：刷新整页（幂等），插在最后一个「主按钮」.btn.primary 之后（通常为「新增」右侧） */
  function appendToolbarRefreshBtn(toolbar) {
    if (!toolbar || toolbar.querySelector("[data-lab-toolbar-refresh='1']")) return;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "lab-toolbar-refresh";
    btn.setAttribute("data-lab-toolbar-refresh", "1");
    btn.setAttribute("aria-label", "刷新页面");
    btn.title = "刷新页面";
    btn.innerHTML = TOOLBAR_REFRESH_SVG;
    btn.addEventListener("click", () => {
      location.reload();
    });
    const primary = Array.from(toolbar.querySelectorAll(":scope > .btn.primary")).pop();
    if (primary && primary.parentNode === toolbar) {
      primary.insertAdjacentElement("afterend", btn);
    } else {
      toolbar.appendChild(btn);
    }
  }

  /**
   * 列表工具栏右侧动作统一顺序：导入/导出 → 主操作（.btn.primary，如新增）→ 刷新。
   * 将三者依次 append 到工具栏末尾（保留左侧筛选、.grow 等原有顺序）。
   */
  function normalizeListToolbarOrders(scope) {
    if (!scope || scope.nodeType !== 1) return;
    let bars;
    if (scope.classList && scope.classList.contains("toolbar") && scope.classList.contains("toolbar-list")) {
      bars = [scope];
    } else if (typeof scope.querySelectorAll === "function") {
      bars = Array.from(scope.querySelectorAll(".toolbar.toolbar-list"));
    } else {
      return;
    }
    bars.forEach((toolbar) => {
      const ie = toolbar.querySelector(":scope > .lab-toolbar-import-export");
      const refresh = toolbar.querySelector(":scope > [data-lab-toolbar-refresh='1']");
      const primaries = Array.from(toolbar.querySelectorAll(":scope > .btn.primary"));
      const primary = primaries.length ? primaries[primaries.length - 1] : null;
      [ie, primary, refresh].forEach((el) => {
        if (el && el.parentNode === toolbar) toolbar.appendChild(el);
      });
    });
  }

  function injectListToolbarRefresh(contentEl) {
    if (!contentEl || isLoginPath()) return;
    const searchBtn = contentEl.querySelector("#btnSearch");
    if (searchBtn) {
      const bar = searchBtn.closest(".toolbar");
      if (bar) appendToolbarRefreshBtn(bar);
    } else {
      const viewList = contentEl.querySelector("#viewList");
      if (viewList) {
        viewList.querySelectorAll(":scope > .toolbar").forEach(appendToolbarRefreshBtn);
      }
    }
    setTimeout(() => normalizeListToolbarOrders(contentEl), 0);
  }

  function applyUserAvatar(el, user, displayName) {
    if (!el) return;
    const letter = (displayName || "U").slice(0, 1).toUpperCase();
    const url = user && user.avatar_url;
    if (url) {
      el.innerHTML = '<img src="' + url + '" alt="" />';
    } else {
      el.textContent = letter;
    }
  }

  function normalizePageHref(href) {
    const raw = String(href || "").trim().split("?")[0].split("#")[0];
    if (!raw) return "index";
    const name = raw.split("/").pop() || "index";
    return name.endsWith(".html") ? name.slice(0, -5) : name;
  }

  function getCurrentPageHref() {
    const name = location.pathname.split("/").pop();
    return normalizePageHref(name || "index");
  }

  function isLoginPath() {
    const p = normalizePageHref(location.pathname.split("/").pop());
    return p === "login";
  }

  /** 视频首页 / 播放页 / 专辑页：全屏沉浸，不套后台侧栏 */
  function isHubFullScreenPage() {
    const p = getCurrentPageHref();
    return p === "index" || p === "video" || p === "album" || p === "video_upload";
  }

  function initHubPage() {
    ensureLegacyAssets();
    disableLegacyNavigation();
    ensureFavicon();
    applyStoredTheme();
    document.documentElement.classList.add("hub-fullscreen");
  }

  function buildSideHtml(activeHref, isAdmin) {
    const sideHtml = [
      '<div class="brand">' +
      '  <img src="logo.svg" alt="基础平台" class="brand-logo">' +
      '  <img src="icon-favicon.svg" alt="基础平台" class="brand-logo-mini">' +
      '</div>'
    ];
    NAV.forEach(g => {
      sideHtml.push('<div class="nav-group">' + g.group + '</div>');
      g.items.forEach(it => {
        if (it.admin && !isAdmin) return;
        const cls = (activeHref === it.href) ? ' class="active"' : "";
        sideHtml.push(
          '<a href="' + it.href + '" data-turbolinks="false" data-label="' + it.label + '"' + cls + '>' +
          '<span class="nav-icon">' + iconSvg(it.icon) + '</span>' +
          '<span class="nav-label">' + it.label + "</span>" +
          "</a>"
        );
      });
    });
    return sideHtml.join("");
  }

  function ensureLayoutShell(activeHref, pageTitle, u) {
    const user = u || {};
    const isAdmin = !!u.is_admin;
    const root = document.body;
    let wrap = root.querySelector(":scope > .app-layout");

    if (!wrap) {
      wrap = document.createElement("div");
      wrap.className = "app-layout";
      wrap.innerHTML =
        '<aside class="app-side"></aside>' +
        '<div class="app-main">' +
        '  <div class="app-top">' +
        '    <div class="top-left">' +
        '      <button class="btn sm menu-toggle-btn" id="btnMenuToggle" aria-label="展开或收起菜单" title="展开或收起菜单">☰</button>' +
        '      <div class="quick-launch">' +
        '        <button class="btn sm quick-launch-trigger" id="btnQuickLauncher" aria-label="快捷入口" title="快捷入口">◫</button>' +
        '        <div class="quick-launch-panel" id="quickLaunchPanel">' +
        '          <a class="quick-launch-item" href="video_upload"><span class="qli-icon">↑</span><span class="qli-main"><b>上传视频</b><small>支持断点续传</small></span></a>' +
        '          <a class="quick-launch-item" href="profile"><span class="qli-icon">U</span><span class="qli-main"><b>个人中心</b><small>修改资料与密码</small></span></a>' +
        "        </div>" +
        "      </div>" +
        '      <div class="page-title"></div>' +
        "    </div>" +
        '    <div class="top-actions">' +
        '      <button class="btn sm theme-toggle-btn" id="btnThemeToggle" aria-label="切换主题" title="切换主题">' +
        '        <span class="theme-icon theme-sun" aria-hidden="true">☀</span>' +
        '        <span class="theme-icon theme-moon" aria-hidden="true">☾</span>' +
        "      </button>" +
        '      <div class="user-menu">' +
        '        <button class="user-trigger" id="btnUserMenu">' +
        '          <span class="user-avatar">U</span>' +
        '          <span class="user-name"></span>' +
        '          <span class="user-caret" aria-hidden="true">' +
        '            <svg viewBox="0 0 24 24" width="14" height="14" focusable="false">' +
        '              <path d="M6 9l6 6 6-6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>' +
        "            </svg>" +
        "          </span>" +
        '        </button>' +
        '        <div class="user-dropdown" id="userDropdown">' +
        '          <button type="button" class="user-dd-item" id="btnProfile">' +
        userMenuIconSvg(USER_MENU_ICON.profile) +
        '<span class="user-dd-text">个人中心</span></button>' +
        '          <button type="button" class="user-dd-item" id="btnChangePwd">' +
        userMenuIconSvg(USER_MENU_ICON.password) +
        '<span class="user-dd-text">修改密码</span></button>' +
        '          <button type="button" class="user-dd-item danger" id="btnLogout">' +
        userMenuIconSvg(USER_MENU_ICON.logout) +
        '<span class="user-dd-text">退出系统</span></button>' +
        "        </div>" +
        "      </div>" +
        '    </div>' +
        '  </div>' +
        '  <div class="app-content" id="pageContent"></div>' +
        '</div>';
      root.insertBefore(wrap, root.firstChild);
    }

    const content = wrap.querySelector("#pageContent");
    const existing = Array.from(root.children).filter(el =>
      el !== wrap &&
      !el.classList.contains("toast-wrap") &&
      !el.classList.contains("modal-mask") &&
      el.tagName !== "SCRIPT"
    );
    existing.forEach(el => content.appendChild(el));
    injectListToolbarRefresh(content);

    wrap.querySelector(".app-side").innerHTML = buildSideHtml(activeHref, isAdmin);
    bindCollapsedNavTooltip(wrap);
    wrap.querySelector(".page-title").textContent = pageTitle || "";
    const userNameEl = wrap.querySelector(".user-name");
    const rawName = (user.real_name || user.username || "");
    const loggedIn = !!(window.LabAPI && LabAPI.getToken());
    const topActions = wrap.querySelector(".top-actions");
    if (loggedIn) {
      userNameEl.textContent = rawName + (isAdmin ? "（管理员）" : "");
      const avatar = wrap.querySelector(".user-avatar");
      applyUserAvatar(avatar, user, rawName);
      const guestBtn = topActions && topActions.querySelector(".hub-top-login");
      if (guestBtn) guestBtn.remove();
      const userMenu = wrap.querySelector(".user-menu");
      if (userMenu) userMenu.style.display = "";
    } else {
      userNameEl.textContent = "游客";
      const avatar = wrap.querySelector(".user-avatar");
      avatar.textContent = "游";
      const userMenu = wrap.querySelector(".user-menu");
      if (userMenu) userMenu.style.display = "none";
      if (topActions && !topActions.querySelector(".hub-top-login")) {
        const loginBtn = document.createElement("a");
        loginBtn.href = "login?next=" + encodeURIComponent(getCurrentPageHref());
        loginBtn.className = "btn sm hub-top-login";
        loginBtn.style.marginRight = "8px";
        loginBtn.textContent = "登录";
        topActions.insertBefore(loginBtn, topActions.firstChild);
      }
    }

    const btnLogout = wrap.querySelector("#btnLogout");
    const btnProfile = wrap.querySelector("#btnProfile");
    const btnChangePwd = wrap.querySelector("#btnChangePwd");
    const btnThemeToggle = wrap.querySelector("#btnThemeToggle");
    const btnMenuToggle = wrap.querySelector("#btnMenuToggle");
    const btnQuickLauncher = wrap.querySelector("#btnQuickLauncher");
    const quickLaunchPanel = wrap.querySelector("#quickLaunchPanel");
    const btnUserMenu = wrap.querySelector("#btnUserMenu");
    const userDropdown = wrap.querySelector("#userDropdown");
    if (btnMenuToggle && !btnMenuToggle.dataset.bound) {
      btnMenuToggle.dataset.bound = "1";
      btnMenuToggle.addEventListener("click", () => {
        const isMobile = window.matchMedia("(max-width: 900px)").matches;
        if (isMobile) {
          const opened = document.documentElement.classList.contains("sidebar-open");
          setMobileMenuOpen(!opened);
          return;
        }
        const collapsed = document.documentElement.classList.contains("sidebar-collapsed");
        applySidebarCollapsed(!collapsed);
      });
    }
    if (btnThemeToggle && !btnThemeToggle.dataset.bound) {
      btnThemeToggle.dataset.bound = "1";
      btnThemeToggle.addEventListener("click", () => {
        const cur = document.documentElement.getAttribute("data-theme") || "light";
        applyTheme(cur === "dark" ? "light" : "dark");
      });
    }
    if (btnUserMenu && !btnUserMenu.dataset.bound) {
      btnUserMenu.dataset.bound = "1";
      btnUserMenu.addEventListener("click", (e) => {
        e.stopPropagation();
        if (userDropdown) userDropdown.classList.toggle("show");
      });
      document.addEventListener("click", (e) => {
        if (!userDropdown || !btnUserMenu) return;
        if (btnUserMenu.contains(e.target)) return;
        if (userDropdown.contains(e.target)) return;
        userDropdown.classList.remove("show");
      });
    }
    if (btnQuickLauncher && !btnQuickLauncher.dataset.bound) {
      btnQuickLauncher.dataset.bound = "1";
      // 移动端保留点击触发
      btnQuickLauncher.addEventListener("click", (e) => {
        if (!window.matchMedia("(max-width: 900px)").matches) return;
        e.stopPropagation();
        if (quickLaunchPanel) quickLaunchPanel.classList.toggle("show");
      });
      document.addEventListener("click", (e) => {
        if (!quickLaunchPanel || !btnQuickLauncher) return;
        if (btnQuickLauncher.contains(e.target)) return;
        if (quickLaunchPanel.contains(e.target)) return;
        quickLaunchPanel.classList.remove("show");
      });
    }
    if (btnProfile && !btnProfile.dataset.bound) {
      btnProfile.dataset.bound = "1";
      btnProfile.addEventListener("click", () => {
        if (userDropdown) userDropdown.classList.remove("show");
        location.href = "profile";
      });
    }
    if (btnChangePwd && !btnChangePwd.dataset.bound) {
      btnChangePwd.dataset.bound = "1";
      btnChangePwd.addEventListener("click", async () => {
        if (userDropdown) userDropdown.classList.remove("show");
        const oldPwd = prompt("请输入当前密码");
        if (oldPwd === null) return;
        const newPwd = prompt("请输入新密码（至少5位）");
        if (newPwd === null) return;
        if (!newPwd || newPwd.length < 5) return LabAPI.toast("新密码至少 5 位", "error");
        const r = await LabAPI.post("/api/auth/change-password", { old_password: oldPwd, new_password: newPwd });
        if (!LabAPI.ok(r)) return LabAPI.toast(LabAPI.msg(r), "error");
        LabAPI.toast("密码已修改，请重新登录", "success");
        setTimeout(() => {
          LabAPI.clearAuth();
          location.href = "login";
        }, 600);
      });
    }
    if (btnLogout && !btnLogout.dataset.bound) {
      btnLogout.dataset.bound = "1";
      btnLogout.addEventListener("click", async () => {
        if (userDropdown) userDropdown.classList.remove("show");
        try { await LabAPI.post("/api/auth/logout"); } catch (_) {}
        LabAPI.clearAuth();
        location.href = "login";
      });
    }

    if (!window.__labSidebarResizeBound) {
      window.__labSidebarResizeBound = true;
      window.addEventListener("resize", () => {
        if (!window.matchMedia("(max-width: 900px)").matches) setMobileMenuOpen(false);
      });
    }
  }

  function ensureBackToTopButton() {
    let btn = document.getElementById("btnBackToTop");
    if (!btn) {
      btn = document.createElement("button");
      btn.id = "btnBackToTop";
      btn.className = "back-to-top";
      btn.type = "button";
      btn.title = "返回顶部";
      btn.setAttribute("aria-label", "返回顶部");
      btn.innerHTML = "↑";
      document.body.appendChild(btn);
    }
    if (!btn.dataset.bound) {
      btn.dataset.bound = "1";
      btn.addEventListener("click", () => {
        window.scrollTo({ top: 0, behavior: "smooth" });
      });
    }
  }

  function updateBackToTopVisible() {
    const btn = document.getElementById("btnBackToTop");
    if (!btn) return;
    const scrollTop = window.scrollY || document.documentElement.scrollTop || 0;
    const viewport = window.innerHeight || document.documentElement.clientHeight || 0;
    const docHeight = document.documentElement.scrollHeight || document.body.scrollHeight || 0;
    const atBottom = scrollTop + viewport >= docHeight - 24;
    if (atBottom && docHeight > viewport + 80) {
      btn.classList.add("show");
    } else {
      btn.classList.remove("show");
    }
  }

  function render(activeHref, pageTitle) {
    if (isHubFullScreenPage()) {
      initHubPage();
      return;
    }
    ensureLegacyAssets();
    disableLegacyNavigation();
    ensureFavicon();
    applyStoredTheme();
    applyStoredSidebarState();
    const u = LabAPI.getUser() || {};
    ensureLayoutShell(normalizePageHref(activeHref), pageTitle, u);
  }

  async function ensureLogin(required) {
    if (required === undefined) required = true;
    const t = LabAPI.getToken();
    if (!t) {
      if (required) { location.href = "login"; throw new Error("not logged in"); }
      return null;
    }
    const r = await LabAPI.get("/api/auth/me");
    if (LabAPI.ok(r)) {
      LabAPI.setUser(r.data);
      return r.data;
    }
    const code = r && r.code;
    const raw = String((r && r.msg) || "");
    const authFailed =
      code === 401 ||
      raw === "未登录" ||
      /登录已过期|登录已失效|无效凭证/.test(raw);
    if (authFailed) {
      LabAPI.clearAuth();
      if (required) {
        location.href = "login";
        throw new Error("auth failed");
      }
      return null;
    }
    if (typeof LabAPI.toast === "function") {
      LabAPI.toast(LabAPI.friendlyMsg(raw) || "暂时无法验证登录，请检查网络后刷新。", "warn");
    }
    throw new Error("verify_login_failed");
  }

  function bootstrapLayoutShell() {
    if (isLoginPath() || isHubFullScreenPage()) return;
    ensureLegacyAssets();
    disableLegacyNavigation();
    ensureFavicon();
    applyStoredTheme();
    applyStoredSidebarState();
    const u = (window.LabAPI && typeof LabAPI.getUser === "function") ? (LabAPI.getUser() || {}) : {};
    const title = (document.title || "").split(" - ")[0] || "";
    ensureLayoutShell(getCurrentPageHref(), title, u);
    ensureBackToTopButton();
    updateBackToTopVisible();
  }

  if (document.body) bootstrapLayoutShell();
  else document.addEventListener("DOMContentLoaded", bootstrapLayoutShell, { once: true });

  window.addEventListener("scroll", updateBackToTopVisible, { passive: true });
  window.addEventListener("resize", updateBackToTopVisible, { passive: true });

  window.LabLayout = { render, ensureLogin, initHubPage, isHubFullScreenPage, normalizeListToolbarOrders };
})();
