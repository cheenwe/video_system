/* 全量 IANA 时区：GET /api/auth/timezones + Selectize 可搜索 */
(function (global) {
  let cache = null;

  function whenSelectizeReady() {
    return new Promise((resolve) => {
      const tick = () => {
        const $ = global.jQuery;
        if ($ && $.fn && typeof $.fn.selectize === "function") return resolve();
        setTimeout(tick, 50);
      };
      tick();
    });
  }

  async function fetchZones() {
    if (cache && cache.length) return cache;
    const r = await LabAPI.get("/api/auth/timezones");
    if (LabAPI.ok(r) && r.data && Array.isArray(r.data.items) && r.data.items.length) {
      cache = r.data.items;
      return cache;
    }
    return ["UTC"];
  }

  /** 当前时刻相对 UTC 的偏移，如 UTC+8、UTC-5、UTC+5:30（便于列表与搜索） */
  function utcOffsetLabel(iana) {
    const id = (iana || "").trim();
    if (!id) return "";
    try {
      const f = new Intl.DateTimeFormat("en-US", {
        timeZone: id,
        timeZoneName: "shortOffset",
      });
      const part = f.formatToParts(new Date()).find((p) => p.type === "timeZoneName");
      let s = ((part && part.value) || "").replace(/\u2212/g, "-").trim();
      if (!s) return "";
      s = s.replace(/^GMT/i, "UTC");
      if (s === "UTC") return "UTC+0";
      return s;
    } catch (_) {
      return "";
    }
  }

  function zoneOptionText(iana) {
    const id = (iana || "").trim();
    const off = utcOffsetLabel(id);
    return off ? id + " (" + off + ")" : id;
  }

  function destroyIfSelectized(selectEl) {
    if (selectEl && selectEl.selectize) {
      try {
        selectEl.selectize.destroy();
      } catch (_) {}
    }
  }

  async function setupTimezoneSelect(selectEl, current) {
    if (!selectEl) return;
    destroyIfSelectized(selectEl);
    const zones = await fetchZones();
    const cur = (current || "UTC").trim();
    const zoneSet = new Set(zones);
    selectEl.innerHTML = "";
    if (cur && !zoneSet.has(cur)) {
      const o = document.createElement("option");
      o.value = cur;
      o.textContent = zoneOptionText(cur) + "（当前）";
      selectEl.appendChild(o);
    }
    for (const z of zones) {
      const o = document.createElement("option");
      o.value = z;
      o.textContent = zoneOptionText(z);
      selectEl.appendChild(o);
    }
    const hasCur =
      cur &&
      (zoneSet.has(cur) || Array.from(selectEl.options).some((o) => o.value === cur));
    selectEl.value = hasCur ? cur : "UTC";

    await whenSelectizeReady();
    const $ = global.jQuery;
    if ($ && $.fn.selectize) {
      $(selectEl).selectize({
        create: false,
        sortField: [{ field: "text", direction: "asc" }],
        maxOptions: 2000,
        openOnFocus: true,
      });
    }
  }

  function getSelectValue(selectEl) {
    if (!selectEl) return "UTC";
    if (selectEl.selectize) {
      const v = selectEl.selectize.getValue();
      return (v || "UTC").trim();
    }
    return (selectEl.value || "UTC").trim();
  }

  global.LabTimezones = { fetchZones, setupTimezoneSelect, getSelectValue, utcOffsetLabel, zoneOptionText };
})(window);
