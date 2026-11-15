(function () {
  "use strict";
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var tabs = $("#tabs"), tE = $("#t-entrar"), tS = $("#t-solicitar"), fE = $("#f-entrar"), fS = $("#f-solicitar");

  function mode(m) {
    var req = m === "solicitar";
    tabs.dataset.mode = req ? "solicitar" : "entrar";
    tE.setAttribute("aria-selected", String(!req)); tS.setAttribute("aria-selected", String(req));
    fE.classList.toggle("hidden", req); fS.classList.toggle("hidden", !req);
    var first = (req ? fS : fE).querySelector("input"); if (first && window.innerWidth > 860) first.focus();
    if (history.replaceState) history.replaceState(null, "", req ? "#solicitar" : location.pathname);
  }
  tE.addEventListener("click", function () { mode("entrar"); });
  tS.addEventListener("click", function () { mode("solicitar"); });
  mode(location.hash === "#solicitar" ? "solicitar" : "entrar");
  window.addEventListener("hashchange", function () { mode(location.hash === "#solicitar" ? "solicitar" : "entrar"); });

  document.querySelectorAll(".eye").forEach(function (b) {
    b.addEventListener("click", function () {
      var i = b.parentNode.querySelector("input"), show = i.type === "password";
      i.type = show ? "text" : "password"; b.textContent = show ? "Ocultar" : "Ver";
      b.setAttribute("aria-label", show ? "Ocultar contraseña" : "Mostrar contraseña");
    });
  });

  async function post(url, body) {
    var r = await fetch(url, { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body) });
    var j = {}; try { j = await r.json(); } catch (e) {}
    return { ok: r.ok, status: r.status, data: j };
  }
  function say(el, text, ok) { el.textContent = text; el.className = "msg " + (ok ? "ok" : "err"); }

  // ---- Entrar
  var lf = $("#loginForm"), lm = $("#loginMsg");
  lf.addEventListener("submit", async function (e) {
    e.preventDefault();
    var u = lf.username.value.trim().toLowerCase(), p = lf.password.value, c = lf.code.value.replace(/\s/g, "");
    if (!u || !p) return say(lm, "Escribe tu usuario y tu contraseña.");
    var btn = lf.querySelector("button[type=submit]"); btn.disabled = true; say(lm, "Comprobando…", true);
    try {
      var body = { username: u, password: p }; if (c) body.code = c;
      var r = await post("/api/auth/login", body);
      if (r.ok) { say(lm, "Listo, entrando…", true); location.replace("/app"); return; }
      say(lm, r.data.error || "No se pudo iniciar sesión.");
      if (r.data.totp_required) {               // la contraseña era correcta: falta el código de 6 dígitos
        $("#codeRow").classList.remove("hidden"); lf.code.value = ""; lf.code.focus(); return;
      }
      lf.password.value = ""; lf.password.focus();
    } catch (err) { say(lm, "No hay conexión con el servidor. Inténtalo de nuevo."); }
    finally { btn.disabled = false; }
  });

  // ---- Solicitar acceso
  var rf = $("#reqForm"), rm = $("#reqMsg"), meter = $("#meter");
  function strength(p) {
    var s = 0; if (p.length >= 10) s++; if (p.length >= 14) s++; if (/[a-z]/.test(p) && /[A-Z]/.test(p)) s++;
    if (/\d/.test(p)) s++; if (/[^A-Za-z0-9]/.test(p)) s++; return Math.min(4, s);
  }
  rf.password.addEventListener("input", function () {
    var s = strength(rf.password.value);
    meter.style.width = (s * 25) + "%";
    meter.style.background = s >= 4 ? "#5FBF92" : s >= 3 ? "#F0AE45" : "#E07A6B";
  });
  rf.username.addEventListener("input", function () { rf.username.value = rf.username.value.toLowerCase().replace(/\s/g, ""); });
  rf.addEventListener("submit", async function (e) {
    e.preventDefault();
    var u = rf.username.value.trim().toLowerCase(), p = rf.password.value;
    if (!/^[a-z0-9][a-z0-9._-]{2,31}$/.test(u)) return say(rm, "El usuario debe tener de 3 a 32 caracteres: minúsculas, números, punto, guion o guion bajo.");
    if (p.length < 10) return say(rm, "La contraseña debe tener al menos 10 caracteres.");
    if (p !== rf.password2.value) return say(rm, "Las contraseñas no coinciden.");
    if (!rf.consent.checked) return say(rm, "Para continuar, acepta la política de datos y el aviso de riesgo.");
    var btn = rf.querySelector("button[type=submit]"); btn.disabled = true; say(rm, "Enviando…", true);
    try {
      var r = await post("/api/auth/request", { username: u, password: p, contact: rf.contact.value.trim(), note: rf.note.value.trim(), consent: rf.consent.value });
      if (r.ok) {
        rf.reset(); meter.style.width = "0";
        say(rm, "Solicitud enviada. Podrás entrar con tu usuario «" + u + "» cuando el administrador la apruebe.", true);
      } else say(rm, r.data.error || "No se pudo enviar la solicitud.");
    } catch (err) { say(rm, "No hay conexión con el servidor. Inténtalo de nuevo."); }
    finally { btn.disabled = false; }
  });
})();
