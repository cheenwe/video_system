(function (global) {
  function debounce(fn, wait) {
    let timer = null;
    return function (...args) {
      if (timer) clearTimeout(timer);
      timer = setTimeout(() => fn.apply(this, args), wait);
    };
  }

  function bindLiveSearch(root) {
    const scope = root || document;
    const bars = scope.querySelectorAll(".toolbar");
    bars.forEach((bar) => {
      const btnSearch = bar.querySelector("#btnSearch, [data-action='search']");
      if (!btnSearch) return;
      const inputs = bar.querySelectorAll("input[type='text'], input:not([type])");
      inputs.forEach((el) => {
        if (el.dataset.liveSearchBound === "1") return;
        el.dataset.liveSearchBound = "1";
        const trigger = debounce(() => {
          // 仅在有内容或刚被清空时触发，避免无意义重复请求
          const now = (el.value || "").trim();
          if (now === (el.dataset.lastSearchValue || "")) return;
          el.dataset.lastSearchValue = now;
          btnSearch.click();
        }, 300);
        el.addEventListener("input", trigger);
      });
    });
  }

  function reinitSelectizeWhenReady() {
    const $ = global.jQuery;
    if (!$ || !$.fn || typeof $.fn.selectize !== "function") return;
    document.querySelectorAll("select").forEach((el) => {
      if (el.dataset.enhanced === "1") initSelectize(el);
    });
  }

  function applyBootstrapClasses(scope) {
    const root = scope || document;
    root.querySelectorAll("table").forEach((tb) => {
      tb.classList.add("table", "table-hover", "align-middle");
      if (!tb.classList.contains("table-bordered")) tb.classList.add("table-bordered");
    });
    root.querySelectorAll("input, textarea, select").forEach((el) => {
      if (el.closest(".selectize-control")) return;
      if (el.classList.contains("selectized")) return;
      if (el.matches('input[type="checkbox"],input[type="radio"],input[type="button"],input[type="submit"],input[type="reset"],input[type="hidden"],input[type="file"],input[type="range"],input[type="color"]')) return;
      if (el.tagName === "SELECT") {
        // selectize 接管的下拉不要再套 bootstrap select 样式，避免样式冲突
        const useSelectize = el.classList.contains("use-selectize") || !!el.closest(".toolbar");
        if (!useSelectize) el.classList.add("form-select");
      } else {
        el.classList.add("form-control");
      }
      if (el.closest("table")) el.classList.add("form-control-sm");
    });
  }

  function initSelectize(el) {
    if (el.dataset.selectizeInited === "1") return;
    const $ = global.jQuery;
    if (!$ || !$.fn || typeof $.fn.selectize !== "function") return;
    if (el.multiple || el.size > 1) return;
    const useSelectize = el.classList.contains("use-selectize") || !!el.closest(".toolbar");
    if (!useSelectize) return;
    /* 由页面脚本手动 selectize（如远程搜索），仅复用 use-selectize 的样式约定，避免重复初始化 */
    if (el.classList.contains("selectize-remote")) return;
    if (el.closest(".selectize-control")) return;
    if (el.classList.contains("selectized")) {
      el.dataset.selectizeInited = "1";
      return;
    }
    try {
      const inlineWidth = (el.style.width || "").trim();
      const inlineMaxWidth = (el.style.maxWidth || "").trim();
      const computedWidth = Math.round(el.getBoundingClientRect().width || 0);
      el.classList.remove("form-select", "form-control", "form-control-sm");
      const $ret = $(el).selectize({
        create: false,
        allowEmptyOption: true,
        sortField: "text",
      });
      const inst = $ret && $ret[0] && $ret[0].selectize;
      if (inst && inst.$control) {
        if (inlineWidth) inst.$control.css("width", inlineWidth);
        else if (computedWidth > 0) inst.$control.css("width", computedWidth + "px");
        if (inlineMaxWidth) inst.$control.css("max-width", inlineMaxWidth);
      }
      el.dataset.selectizeInited = "1";
    } catch (_) {}
  }

  function initDatepicker(el) {
    if (el.dataset.datepickerInited === "1") return true;
    const $ = global.jQuery;
    if (!$ || !$.fn || typeof $.fn.datepicker !== "function") return false;
    const visible = !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
    if (!visible) return false;
    const old = (el.value || "").trim();
    if (!el.dataset.origType) el.dataset.origType = el.type;
    if (el.type === "date" || el.type === "datetime-local") el.type = "text";
    const fmt = el.dataset.origType === "datetime-local" ? "yyyy-mm-dd hh:ii" : "yyyy-mm-dd";
    try {
      $(el).datepicker({
        language: "zh-CN",
        format: fmt,
        autoclose: true,
        todayHighlight: true,
        container: "body",
        orientation: "auto",
      });
      if (old) $(el).datepicker("setDate", old.replace("T", " "));
      el.dataset.datepickerInited = "1";
      return true;
    } catch (_) {
      return false;
    }
  }

  function bindLazyDatepicker(el) {
    if (el.dataset.datepickerBound === "1") return;
    el.dataset.datepickerBound = "1";
    const onOpen = () => {
      const ok = initDatepicker(el);
      if (!ok) return;
      const $ = global.jQuery;
      try { $(el).datepicker("show"); } catch (_) {}
    };
    el.addEventListener("focus", onOpen);
    el.addEventListener("click", onOpen);
  }

  function hasValue(el) {
    return !!(el.value || "").trim();
  }

  function setFieldState(el, ok, msg) {
    el.classList.remove("is-invalid", "is-valid");
    if (!hasValue(el)) return;
    el.classList.add(ok ? "is-valid" : "is-invalid");
    if (msg && !ok) el.setAttribute("title", msg);
    else el.removeAttribute("title");
    const holder = el.parentElement && el.parentElement.querySelector(".field-error");
    if (holder) holder.textContent = ok ? "" : (msg || "输入不合法");
  }

  function validateInput(el) {
    if (el.disabled || el.readOnly) return true;
    const value = (el.value || "").trim();
    if (el.required && !value) {
      setFieldState(el, false, "该字段为必填项");
      return false;
    }
    if (typeof el.checkValidity === "function" && !el.checkValidity()) {
      setFieldState(el, false, el.validationMessage || "输入格式不正确");
      return false;
    }
    if (!value) {
      setFieldState(el, true);
      return true;
    }
    if (el.type === "number") {
      const n = Number(value);
      if (Number.isNaN(n)) {
        setFieldState(el, false, "请输入有效数字");
        return false;
      }
      if (el.min !== "" && n < Number(el.min)) {
        setFieldState(el, false, "数值不能小于最小值");
        return false;
      }
      if (el.max !== "" && n > Number(el.max)) {
        setFieldState(el, false, "数值不能大于最大值");
        return false;
      }
    }
    if ((el.type === "date" || el.type === "datetime-local") && value.length < 10) {
      setFieldState(el, false, "日期格式不正确");
      return false;
    }
    setFieldState(el, true);
    return true;
  }

  function enhanceFields(root) {
    const scope = root || document;
    applyBootstrapClasses(scope);
    const fields = scope.querySelectorAll("input, select, textarea");
    fields.forEach((el) => {
      if (el.closest(".selectize-control")) return;
      if (el.dataset.enhanced === "1") return;
      el.dataset.enhanced = "1";
      if (el.required && el.id) {
        const label = document.querySelector('label[for="' + el.id + '"]') || (el.parentElement && el.parentElement.querySelector("label"));
        if (label && !label.querySelector(".required-star")) {
          const star = document.createElement("span");
          star.className = "required-star";
          star.textContent = " *";
          label.appendChild(star);
        }
      }
      if (el.closest("table")) el.classList.add("table-input");
      if (el.type === "date" || el.type === "datetime-local" || el.classList.contains("date-input")) el.classList.add("date-input");
      if (el.tagName === "SELECT") initSelectize(el);
      if (el.type === "date" || el.type === "datetime-local" || el.classList.contains("date-input")) {
        bindLazyDatepicker(el);
        initDatepicker(el);
      }
      const isDateLike = el.type === "date" || el.type === "datetime-local" || el.classList.contains("date-input") || !!el.dataset.origType;
      if (isDateLike && !el.value && el.dataset.defaultToday === "1") {
        const now = new Date();
        const dtType = (el.dataset.origType || el.type || "").toLowerCase();
        if (dtType === "date") {
          el.value = now.toISOString().slice(0, 10);
        } else if (el.classList.contains("date-input") || dtType === "text") {
          const z = (n) => String(n).padStart(2, "0");
          el.value = now.getFullYear() + "-" + z(now.getMonth() + 1) + "-" + z(now.getDate());
        } else {
          const z = (n) => String(n).padStart(2, "0");
          el.value = now.getFullYear() + "-" + z(now.getMonth() + 1) + "-" + z(now.getDate()) + " " + z(now.getHours()) + ":" + z(now.getMinutes());
        }
      }
      el.addEventListener("blur", () => validateInput(el));
      el.addEventListener("change", () => validateInput(el));
      if (el.parentElement && !el.parentElement.querySelector(".field-error")) {
        const err = document.createElement("div");
        err.className = "field-error";
        el.parentElement.appendChild(err);
      }
    });
  }

  function bindSubmitValidation() {
    document.querySelectorAll("form").forEach((form) => {
      if (form.dataset.enhancedSubmit === "1") return;
      form.dataset.enhancedSubmit = "1";
      form.addEventListener("submit", (e) => {
        const fields = form.querySelectorAll("input, select, textarea");
        let firstBad = null;
        fields.forEach((el) => {
          const ok = validateInput(el);
          if (!ok && !firstBad) firstBad = el;
        });
        if (firstBad) {
          e.preventDefault();
          firstBad.focus();
          if (global.LabAPI && typeof global.LabAPI.toast === "function") {
            global.LabAPI.toast("请先修正表单中标红字段", "error");
          }
        }
      });
    });
  }

  function boot() {
    enhanceFields(document);
    bindSubmitValidation();
    bindLiveSearch(document);
    // selectize 可能由 layout.js 稍后注入，做一次延迟重试保证已有下拉生效
    setTimeout(reinitSelectizeWhenReady, 0);
    setTimeout(reinitSelectizeWhenReady, 300);
    setTimeout(reinitSelectizeWhenReady, 1000);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }

  const observer = new MutationObserver((mutations) => {
    mutations.forEach((m) => {
      m.addedNodes.forEach((node) => {
        if (node.nodeType === 1) {
          enhanceFields(node);
          bindLiveSearch(node);
        }
      });
    });
  });
  observer.observe(document.documentElement, { childList: true, subtree: true });
})(window);
