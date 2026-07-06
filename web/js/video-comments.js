/** 视频评论区 */
(function (global) {
  function esc(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/"/g, "&quot;");
  }

  function avatarChar(name) {
    const n = String(name || "").trim();
    return n ? n.charAt(0).toUpperCase() : "?";
  }

  function renderCommentItem(c, loggedIn) {
    const delBtn = loggedIn && c.can_delete
      ? ' <button type="button" class="comment-del" data-id="' + c.id + '">删除</button>'
      : "";
    const anonTag = c.is_anonymous ? ' <span class="comment-anon-tag">匿名</span>' : "";
    return (
      '<div class="comment-item" data-id="' + c.id + '">' +
      '<div class="comment-avatar" aria-hidden="true">' + esc(avatarChar(c.display_name)) + "</div>" +
      '<div class="comment-main">' +
      '<div class="comment-head"><span class="comment-author">' + esc(c.display_name) + "</span>" +
      anonTag +
      '<span class="comment-time">' + esc(c.created_at || "") + "</span>" + delBtn + "</div>" +
      '<div class="comment-body">' + esc(c.content) + "</div></div></div>"
    );
  }

  function renderForm(loggedIn) {
    const nickRow = loggedIn
      ? '<label class="comment-nick-row" id="nickRow" style="display:none;"><span>昵称</span><input id="commentNick" maxlength="32" placeholder="匿名昵称（可选）" /></label>'
      : '<label class="comment-nick-row"><span>昵称</span><input id="commentNick" maxlength="32" placeholder="匿名昵称（可选，默认匿名用户）" /></label>';
    const anonCheck = loggedIn
      ? '<label class="comment-anon-check"><input type="checkbox" id="commentAnon" /> 匿名发表</label>'
      : '<span class="muted comment-guest-hint">未登录将以匿名身份发表评论</span>';
    return (
      '<div class="comment-form">' +
      '<textarea id="commentContent" rows="3" maxlength="2000" placeholder="发条友善的评论…"></textarea>' +
      '<div class="comment-form-bar">' +
      '<div class="comment-form-left">' + nickRow + anonCheck + "</div>" +
      '<button type="button" class="comment-submit-btn" id="btnCommentSubmit">发布</button>' +
      "</div></div>"
    );
  }

  async function mount(videoId, containerId) {
    const root = document.getElementById(containerId);
    if (!root || !videoId) return;

    const loggedIn = !!(global.LabAPI && global.LabAPI.getToken());
    root.innerHTML =
      '<div class="comment-section">' +
      '<div class="comment-section-title">评论 <span id="commentTotal" class="comment-total"></span></div>' +
      renderForm(loggedIn) +
      '<div id="commentList" class="comment-list"></div>' +
      '<div id="commentMore" class="comment-more"></div>' +
      "</div>";

    if (loggedIn) {
      const anon = document.getElementById("commentAnon");
      const nickRow = document.getElementById("nickRow");
      if (anon && nickRow) {
        anon.addEventListener("change", () => {
          nickRow.style.display = anon.checked ? "" : "none";
        });
      }
    }

    document.getElementById("btnCommentSubmit").addEventListener("click", () => submitComment(videoId, loggedIn));

    document.getElementById("commentList").addEventListener("click", async (e) => {
      const btn = e.target.closest(".comment-del");
      if (!btn) return;
      if (!confirm("确定删除这条评论？")) return;
      const cid = btn.getAttribute("data-id");
      const dr = await global.LabAPI.del("/api/videos/" + videoId + "/comments/" + cid);
      if (!global.LabAPI.ok(dr)) return global.LabAPI.toast(global.LabAPI.msg(dr), "error");
      global.LabAPI.toast("已删除", "success");
      loadComments(videoId, loggedIn, 1);
    });

    await loadComments(videoId, loggedIn, 1);
  }

  async function loadComments(videoId, loggedIn, page) {
    const r = await global.LabAPI.get("/api/videos/" + videoId + "/comments?page=" + page);
    if (!global.LabAPI.ok(r)) {
      document.getElementById("commentList").innerHTML =
        '<div class="muted">' + global.LabAPI.msg(r) + "</div>";
      return;
    }
    const d = r.data;
    document.getElementById("commentTotal").textContent = d.total ? "(" + d.total + ")" : "";
    const items = d.items || [];
    const listEl = document.getElementById("commentList");
    const block = items.length
      ? items.map((c) => renderCommentItem(c, loggedIn)).join("")
      : '<div class="comment-empty muted">还没有评论，来抢沙发吧</div>';
    if (page > 1 && items.length) listEl.insertAdjacentHTML("beforeend", block);
    else listEl.innerHTML = block;

    const moreEl = document.getElementById("commentMore");
    if (d.login_required_for_more) {
      const loginNext = encodeURIComponent(location.pathname.split("/").pop() + location.search);
      moreEl.innerHTML =
        '<p class="comment-login-tip">未登录仅展示前 ' + (d.guest_preview_limit || 2) + " 条评论，" +
        '共 ' + d.total + ' 条。<a href="login?next=' + loginNext + '">登录</a> 查看全部并参与讨论。</p>';
    } else if (!loggedIn) {
      moreEl.innerHTML = "";
    } else if (d.total > d.page * d.page_size) {
      moreEl.innerHTML = '<button type="button" class="btn sm" id="btnCommentMore">加载更多</button>';
      document.getElementById("btnCommentMore").onclick = () => loadComments(videoId, loggedIn, page + 1);
    } else {
      moreEl.innerHTML = "";
    }
  }

  async function submitComment(videoId, loggedIn) {
    const content = (document.getElementById("commentContent").value || "").trim();
    if (!content) return global.LabAPI.toast("请输入评论内容", "warn");
    const body = { content };
    if (loggedIn) {
      const anon = document.getElementById("commentAnon");
      body.anonymous = !!(anon && anon.checked);
      if (body.anonymous) {
        const nick = (document.getElementById("commentNick").value || "").trim();
        if (nick) body.display_name = nick;
      }
    } else {
      body.anonymous = true;
      const nick = (document.getElementById("commentNick").value || "").trim();
      if (nick) body.display_name = nick;
    }
    const r = await global.LabAPI.post("/api/videos/" + videoId + "/comments", body);
    if (!global.LabAPI.ok(r)) return global.LabAPI.toast(global.LabAPI.msg(r), "error");
    global.LabAPI.toast("评论已发布", "success");
    document.getElementById("commentContent").value = "";
    await loadComments(videoId, loggedIn, 1);
  }

  global.VideoComments = { mount };
})(window);
