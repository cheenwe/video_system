/**
 * 根据当前用户角色显示/隐藏管理员菜单（系统设置、用户管理），并显示当前登录用户名。
 * 依赖：axios，且页面已加载 token。在 body onload 中先 CheckLogin 再 ApplyNavRole。
 * Turbolinks 导航不会触发 onload，因此需监听 turbolinks:load 在每次页面展示后重新执行。
 */
function ApplyNavRole() {
    var token = localStorage.getItem("token");
    if (!token) return;
    function apply(showAdmin) {
        var el = document.querySelectorAll(".nav-admin");
        for (var i = 0; i < el.length; i++) el[i].style.display = showAdmin ? "" : "none";
    }
    function setNavUsername(name) {
        var el = document.getElementById("nav-username");
        if (el) el.textContent = name ? name : "";
    }
    var isAdmin = localStorage.getItem("is_admin") === "1";
    apply(isAdmin);
    var cached = localStorage.getItem("username");
    if (cached) setNavUsername(cached);
    if (typeof axios !== "undefined") {
        axios.get("/api/me", { headers: { "Authorization": "Bearer " + token } })
            .then(function(r) {
                if (r.data && r.data.success === 1) {
                    var admin = r.data.is_admin === true;
                    localStorage.setItem("is_admin", admin ? "1" : "0");
                    apply(admin);
                    var u = r.data.username;
                    if (u) {
                        localStorage.setItem("username", u);
                        setNavUsername(u);
                    }
                }
            })
            .catch(function() { apply(false); });
    }
}

(function() {
    if (document.addEventListener) {
        document.addEventListener("turbolinks:load", function() {
            if (typeof CheckLogin === "function") CheckLogin();
            if (localStorage.getItem("token")) ApplyNavRole();
        });
    }
})();
