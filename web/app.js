// Crypto Radar · panel. JavaScript sin dependencias.
const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
let CSRF = "", ME = null, ACCOUNTS = false, PILOT = {metrics: false, survey: null};
// Instrumentación del piloto (radar/piloto.py): solo si el servidor la tiene encendida; sin terceros, una vez por día
const PILOT_SENT = new Set();
function pilotEvent(body){
  const k = new Date().toISOString().slice(0, 10) + JSON.stringify(body);
  if (!PILOT.metrics || !CSRF || PILOT_SENT.has(k)) return;
  PILOT_SENT.add(k); post("/api/piloto/evento", body).catch(() => PILOT_SENT.delete(k));
}
async function api(p, o) {
  const r = await fetch(p, Object.assign({credentials: "same-origin"}, o));
  let j = null; try { j = await r.json(); } catch (e) {}
  if (r.status === 401 && ACCOUNTS && !p.startsWith("/api/auth/")) { showAuth(); throw new Error("sesión"); }
  if (!r.ok && !j) throw new Error("El servidor respondió " + r.status);
  if (j && typeof j === "object" && !Array.isArray(j)) j._status = r.status;
  return j;
}
const post = (p, b) => api(p, {method: "POST", headers: {"Content-Type": "application/json", "X-CSRF-Token": CSRF}, body: JSON.stringify(b || {})});
function lsGet(k){try{return localStorage.getItem(k)}catch(e){return null}}
function lsSet(k,v){try{localStorage.setItem(k,v)}catch(e){}}

let STATE = null, VIEW = "dash", SORT = {key: "rank_score", dir: -1}, MEME_TAB = "radar", MEMES = null;
let lastAlertSeen = lsGet("seenAlert") || "";

/* ---------- Formato (español) ---------- */
const NF = (min, max) => new Intl.NumberFormat("es-CO", {minimumFractionDigits: min, maximumFractionDigits: max});
const nf0 = NF(0, 0), nf1 = NF(1, 1), nf2 = NF(2, 2);
function num(v, d = 1){ if (v == null || isNaN(v)) return "—"; return NF(d, d).format(v); }
function px(v){
  if (v == null || isNaN(v)) return "—";
  const a = Math.abs(v);
  if (a >= 1000) return "$" + nf0.format(v);
  if (a >= 1) return "$" + NF(2, 2).format(v);
  return "$" + new Intl.NumberFormat("es-CO", {maximumSignificantDigits: 4}).format(v);
}
function big(v){
  if (v == null || isNaN(v)) return "—";
  const a = Math.abs(v);
  if (a >= 1e12) return "$" + nf2.format(v / 1e12) + " bill.";   // billones (10^12)
  if (a >= 1e9) return "$" + nf1.format(v / 1e9) + " mil M";
  if (a >= 1e6) return "$" + nf1.format(v / 1e6) + " M";
  return "$" + nf0.format(v);
}
function pctTxt(v, d = 1){ if (v == null || isNaN(v)) return "—"; return (v >= 0 ? "+" : "−") + NF(d, d).format(Math.abs(v)) + "%"; }
function pct(v, d = 1){ if (v == null || isNaN(v)) return `<span class="muted">—</span>`; return `<span class="${v >= 0 ? "pos" : "neg"}">${pctTxt(v, d)}</span>`; }
function rTxt(v){ if (v == null || isNaN(v)) return "—"; return (v >= 0 ? "+" : "−") + nf1.format(Math.abs(v)) + "×"; }
function esc(s){ return String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c])); }
function ago(iso){
  if (!iso) return "nunca";
  const m = Math.round((Date.now() - new Date(iso)) / 60000);
  return m < 1 ? "ahora" : m < 60 ? `hace ${m} min` : m < 1440 ? `hace ${Math.round(m / 60)} h` : `hace ${Math.round(m / 1440)} d`;
}
function when(iso){ return iso ? new Date(iso).toLocaleString("es-CO", {day: "numeric", month: "short", hour: "numeric", minute: "2-digit"}) : "—"; }
function dayLabel(iso){
  const d = new Date(iso), t = new Date(); const k = x => x.toDateString();
  const y = new Date(t); y.setDate(t.getDate() - 1);
  if (k(d) === k(t)) return "Hoy";
  if (k(d) === k(y)) return "Ayer";
  return d.toLocaleDateString("es-CO", {weekday: "long", day: "numeric", month: "long"});
}
function scoreCls(v){ return v >= 80 ? "s-hi" : v >= 60 ? "s-mid" : "s-lo"; }
function sc(v){ return `<span class="sc ${scoreCls(v)}">${Math.round(v)}</span>`; }
function actCls(a){ a = a || ""; return a.startsWith("COMPRAR") ? "b-buy" : (a.startsWith("ESPERAR") || a.startsWith("VIGILAR")) ? "b-wait" : (a.startsWith("EVITAR") || a.startsWith("RECHAZAR")) ? "b-avoid" : "b-watch"; }
const ACT = {"WATCHLIST": "En vigilancia", "RECHAZAR": "Descartado"};
function actLabel(a){ a = String(a || ""); return ACT[a] || cap(a.replace(/\s*\(.*\)\s*/, "").replace(/\s*\/\s*/, " / ")); }
function act(a){ return `<span class="badge ${actCls(a)}" title="${esc(cap(a))}">${esc(actLabel(a))}</span>`; }
function cap(s){ s = String(s || "").toLowerCase(); return s.charAt(0).toUpperCase() + s.slice(1); }
function ring(v){
  const c = v >= 80 ? "var(--amber)" : v >= 60 ? "var(--info)" : "var(--muted)";
  return `<div class="ring" style="--p:${Math.max(0, Math.min(100, v))};--c:${c}"><span>${Math.round(v)}</span></div>`;
}
const emptyRow = (n, t) => `<tr><td colspan="${n}" class="empty-row">${t}</td></tr>`;

/* ---------- Iconos (trazo simple) ---------- */
const IC = {
  radar: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><path d="M12 12 18 6"/>',
  list: '<path d="M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01"/>',
  bell: '<path d="M6 16V11a6 6 0 1 1 12 0v5l1.5 2h-15z"/><path d="M10 20a2 2 0 0 0 4 0"/>',
  wallet: '<rect x="3" y="6" width="18" height="13" rx="2.5"/><path d="M16 12.5h2M3 9h18"/>',
  bolt: '<path d="M13 3 5 14h6l-1 7 8-11h-6z"/>',
  history: '<path d="M4 12a8 8 0 1 0 2.3-5.6L4 8.7"/><path d="M4 4v4.7h4.7M12 8v4l3 2"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M19 12a7 7 0 0 0-.1-1.2l2-1.5-2-3.4-2.3.9a7 7 0 0 0-2-1.2L14.2 3h-4l-.4 2.6a7 7 0 0 0-2 1.2l-2.4-.9-2 3.4 2 1.5a7 7 0 0 0 0 2.4l-2 1.5 2 3.4 2.4-.9a7 7 0 0 0 2 1.2l.4 2.6h4l.4-2.6a7 7 0 0 0 2-1.2l2.3.9 2-3.4-2-1.5c.1-.4.1-.8.1-1.2z"/>',
  more: '<circle cx="5" cy="12" r="1.3"/><circle cx="12" cy="12" r="1.3"/><circle cx="19" cy="12" r="1.3"/>',
  refresh: '<path d="M20 11a8 8 0 0 0-14.7-3.5M4 4v4h4M4 13a8 8 0 0 0 14.7 3.5M20 20v-4h-4"/>',
  download: '<path d="M12 4v11M7 10l5 5 5-5M5 20h14"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  lock: '<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
  x: '<path d="M6 6l12 12M18 6 6 18"/>',
  up: '<path d="M4 17 10 11l4 4 6-7"/><path d="M15 8h5v5"/>',
  target: '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="4"/><circle cx="12" cy="12" r=".8"/>',
  warn: '<path d="M12 4 2.5 20h19z"/><path d="M12 10v4M12 17h.01"/>',
  stop: '<rect x="5" y="5" width="14" height="14" rx="3"/>',
  coin: '<circle cx="12" cy="12" r="8"/><path d="M14.5 9.5c-.5-.8-1.4-1.2-2.5-1.2-1.5 0-2.5.8-2.5 1.9 0 2.6 5 1.3 5 3.9 0 1.1-1 1.9-2.5 1.9-1.1 0-2-.4-2.6-1.2M12 6.5v1.8M12 15.7v1.8"/>',
  down: '<path d="M4 7l6 6 4-4 6 7"/><path d="M15 16h5v-5"/>',
  globe: '<circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17M12 3.5c2.5 2.6 2.5 14.4 0 17M12 3.5c-2.5 2.6-2.5 14.4 0 17"/>',
  info: '<circle cx="12" cy="12" r="8.5"/><path d="M12 11v5M12 8h.01"/>'
};
function icon(n){ return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${IC[n] || ""}</svg>`; }
function paintIcons(root = document){ root.querySelectorAll("i[data-ic]:empty").forEach(i => i.innerHTML = icon(i.dataset.ic)); }

/* ---------- Avisos y diálogos dentro de la página ---------- */
let toastT;
function toast(t){ const el = $("#toast"); el.textContent = t; el.classList.remove("hidden"); clearTimeout(toastT); toastT = setTimeout(() => el.classList.add("hidden"), 4000); }
function openOv(id){ $(id).classList.remove("hidden"); document.body.style.overflow = "hidden"; }
function closeOv(el){ el.classList.add("hidden"); if (!$$(".overlay:not(.hidden)").length) document.body.style.overflow = ""; }
$$(".overlay").forEach(o => o.addEventListener("click", e => { if (e.target === o || e.target.closest("[data-close]")) closeOv(o); }));
document.addEventListener("keydown", e => { if (e.key === "Escape") $$(".overlay:not(.hidden)").forEach(closeOv); });
function ask({title, text, input = false, placeholder = "", ok = "Aceptar"}){
  return new Promise(res => {
    $("#dlgTitle").textContent = title; $("#dlgText").textContent = text || ""; $("#dlgOk").textContent = ok;
    const inp = $("#dlgInput"); inp.classList.toggle("hidden", !input); inp.value = ""; inp.placeholder = placeholder;
    const ov = $("#dialog"), f = $("#dialogForm"); let done = false;
    const finish = v => { if (done) return; done = true; obs.disconnect(); closeOv(ov); res(v); };
    const obs = new MutationObserver(() => { if (ov.classList.contains("hidden")) finish(null); });
    f.onsubmit = e => { e.preventDefault(); finish(input ? inp.value : true); };
    openOv("#dialog"); obs.observe(ov, {attributes: true}); (input ? inp : $("#dlgOk")).focus();
  });
}


/* ---------- Navegación (11 secciones) ---------- */
const TITLES = {dash: "Dashboard", early: "Oportunidades tempranas", market: "Mercado", breakouts: "Rupturas", memes: "Memecoins",
  exits: "Salidas", portfolio: "Cartera", backtest: "Backtesting", perf: "Rendimiento", alerts: "Alertas", settings: "Configuración"};
const MORE = ["market", "breakouts", "memes", "exits", "backtest", "perf", "settings"];
const LOADERS = {alerts: loadAlerts, portfolio: loadPositions, exits: loadPositions, memes: loadMemes, perf: loadJournal,
  settings: loadSettings, backtest: loadBacktest};
document.addEventListener("click", e => {
  const b = e.target.closest("[data-view]"); if (!b) return;
  if (b.dataset.view === "more") return openOv("#moreSheet");
  closeOv($("#moreSheet")); show(b.dataset.view);
});
function show(v){
  VIEW = v;
  $$("[data-view]").forEach(b => b.classList.toggle("on", b.dataset.view === v || (b.dataset.view === "more" && MORE.includes(v))));
  $$(".view").forEach(s => s.classList.toggle("on", s.id === "v-" + v));
  $("#viewTitle").textContent = TITLES[v]; document.title = TITLES[v] + " · Crypto Radar";
  $("#exportBtn").classList.toggle("hidden", !["dash", "market", "perf"].includes(v));
  window.scrollTo(0, 0);
  LOADERS[v]?.();
  pilotEvent({event: "tab", tab: v});
  if (v === "alerts") { lastAlertSeen = new Date().toISOString(); lsSet("seenAlert", lastAlertSeen); setCount(0); }
  try { history.replaceState(null, "", "#" + v); } catch (e) {}
}
function setCount(n){ $$("[data-count]").forEach(c => { c.textContent = n > 99 ? "99+" : n; c.classList.toggle("hidden", !n); }); }
const PH = {"PRE-EXPLOSION": "Pre-explosión", "ACCUMULATION": "Acumulación", "BREAKOUT": "Ruptura", "MOMENTUM": "Momentum",
  "OVEREXTENDED": "Sobreextendida", "DISTRIBUTION": "Distribución", "REJECTED": "Descartada"};
const phase = p => PH[p] || cap(p);
const manip = (r, l) => `<span class="${r >= 60 ? "neg" : r >= 35 ? "amb" : "muted"}" title="Riesgo de manipulación">${r ?? "—"}${l ? " · " + esc(cap(l)) : ""}</span>`;

/* ---------- Cuenta (modo SaaS) ---------- */
// El inicio de sesión vive en /entrar (página propia); aquí solo se redirige.
function showAuth(){ location.replace("/entrar"); }
function hideAuth(){ const a = $("#auth"); if (a) a.classList.add("hidden"); $("#app").classList.remove("hidden"); }
function applyUser(){
  const admin = !ACCOUNTS || ME?.is_admin;
  $$(".admin-only").forEach(el => el.classList.toggle("hidden", !admin));
  $$(".user-only").forEach(el => el.classList.toggle("hidden", !ACCOUNTS || !ME));
  const pill = $("#planPill"); pill.classList.toggle("hidden", !ME);
  if (ME) pill.textContent = "Plan " + ME.plan_label;
}

/* ---------- Estado ---------- */
async function scan(){
  try { const r = await post("/api/scan"); toast(r.ok ? "Escaneo iniciado. Tarda unos minutos." : (r.msg || r.error || "No se pudo iniciar el escaneo")); }
  catch (e) { toast("No se pudo contactar el servidor"); }
  refresh();
}
$("#scanBtn").onclick = scan; $("#scanBtnM").onclick = scan;

async function refresh(){
  try { STATE = await api("/api/state"); }
  catch (e) { if (e.message !== "sesión") setStatus("bad", "Sin conexión con el servidor"); return; }
  if (STATE.user) { ME = STATE.user; applyUser(); }
  const st = STATE.status || {}, rep = STATE.report || {};
  $("#scanBtn").disabled = $("#scanBtnM").disabled = !!st.scanning;
  $("#scanBtn").querySelector("span").textContent = st.scanning ? "Escaneando…" : "Escanear ahora";
  if (st.scanning) setStatus("busy", st.progress || "Escaneando…");
  else if (st.last_error) setStatus("bad", "Último escaneo con error");
  else setStatus(rep.at ? "ok" : "", rep.at ? "Actualizado " + ago(rep.at) : "Sin escaneos todavía");
  const eb = $("#errBar"); eb.classList.toggle("hidden", !st.last_error);
  if (st.last_error) eb.textContent = "El último escaneo no terminó: " + st.last_error + ". Los datos mostrados son del último escaneo completo.";
  const lb = $("#lockBar"); lb.classList.toggle("hidden", !rep.locked);
  if (rep.locked) lb.innerHTML = `Plan Libre: ves el top 3 con su plan completo. <button class="linkbtn small" data-view="settings">Mejora a Pro</button> para el ranking completo, cartera, salidas, memecoins y alertas por Telegram.`;
  $("#sideFoot").innerHTML = `Último escaneo: <b>${rep.at ? ago(rep.at) : "nunca"}</b><br>Próximo: ${when(STATE.next_scan)}${STATE.version ? `<br>Versión ${esc(STATE.version)}` : ""}`;
  $("#empty").classList.toggle("hidden", !!rep.at);
  if (rep.at) { renderDash(rep); renderEarly(rep); renderMarket(rep); renderBreakouts(rep); }
  try { const al = await api("/api/alerts"); if (Array.isArray(al)) { setCount(VIEW === "alerts" ? 0 : al.filter(a => a.at > lastAlertSeen).length); renderDashAlerts(al); } } catch (e) {}
}
function setStatus(cls, txt){ const s = $("#status"); s.className = "status " + cls; s.querySelector("span").textContent = txt; s.title = txt; }

/* ---------- 1. Dashboard ---------- */
const FG = {"Extreme Fear": "Miedo extremo", "Fear": "Miedo", "Neutral": "Neutral", "Greed": "Codicia", "Extreme Greed": "Codicia extrema"};
const mini = (l, v, s = "", x = "") => `<div class="mini ${x}"><div class="l">${l}</div><div class="v">${v}</div>${s ? `<div class="s">${s}</div>` : ""}</div>`;
function renderDash(rep){
  const m = rep.market || {}, v = rep.verdict || "", fg = m.fear_greed;
  const vc = v === "OPORTUNIDADES ACTIVAS" ? "v-ok" : v === "ESPERAR ENTRADA" ? "" : "v-cash";
  $("#kpis").innerHTML = `<div class="verdict ${vc}"><div class="k">Veredicto del mercado</div><h2>${esc(cap(v))}</h2><p>${esc(rep.verdict_text || "")}</p></div>` +
    mini("Bitcoin", px(m.btc_price), `7 d ${pctTxt(m.btc_chg_7d)} · 30 d ${pctTxt(m.btc_chg_30d)}`) +
    mini("Régimen", esc(m.regime_label || cap(m.regime || "—")), `Puntaje mínimo ${m.min_buy_score ?? "—"}`) +
    mini("Amplitud", m.breadth != null ? nf0.format(m.breadth) + "%" : "—", "altcoins sobre su EMA50") +
    mini("Sentimiento", fg ? fg.value : "—", fg ? (FG[fg.label] || fg.label) : "sin dato", "x");
  $("#outlook").textContent = rep.outlook || "";
  const pc = rep.phase_counts || {}, tot = Object.values(pc).reduce((a, b) => a + b, 0) || 1;
  $("#phaseBar").innerHTML = Object.keys(PH).filter(k => pc[k]).map(k => `<span class="ph ph-${k.toLowerCase()}" style="flex:${pc[k]}" title="${phase(k)}: ${pc[k]}">${pc[k] / tot > .07 ? phase(k) + " " + pc[k] : ""}</span>`).join("");
  $("#rankMeta").textContent = `${rep.analyzed ?? "—"} activos analizados · prioriza fases tempranas y penaliza lo que ya subió`;
  const R = rep.ranking || [];
  $("#rankCards").innerHTML = R.length ? R.map(oppCard).join("") : emptyCard();
  const cols = ["#", "Token", "Precio", "Puntaje", "Fase", "Vol. rel.", "24 h", "7 d", "30 d", "vs BTC", "Liquidez", "Manip.", "Zona de entrada", "Stop", "TP1", "TP2", "TP3", "R/B", "Acción"];
  $("#rankTable").innerHTML = `<thead><tr>${cols.map(c => `<th>${c}</th>`).join("")}</tr></thead><tbody>` +
    (R.length ? R.map(r => `<tr data-s="${esc(r.symbol)}"><td class="muted">${r.rank}</td><td class="sym">${esc(r.symbol)}</td><td>${px(r.price)}</td>
      <td>${sc(r.score)}</td><td>${phase(r.phase)}</td><td>${r.rel_volume != null ? "×" + nf1.format(r.rel_volume) : "—"}</td><td>${pct(r.chg_24h)}</td><td>${pct(r.chg_7d)}</td>
      <td>${pct(r.chg_30d)}</td><td>${pct(r.rs_btc_30d)}</td><td>${r.liquidity != null ? nf0.format(r.liquidity * 100) : "—"}</td><td>${manip(r.manipulation_risk)}</td>
      <td>${px(r.entry_low)} – ${px(r.entry_high)}</td><td class="neg">${px(r.stop)}</td><td>${px(r.tp1)}</td><td class="pos">${px(r.tp2)}</td><td>${px(r.tp3)}</td>
      <td>${num(r.rr)}</td><td>${act(r.action)}</td></tr>`).join("") : emptyRow(cols.length, "Hoy ningún activo califica. Mantener liquidez también es una decisión.")) + "</tbody>";
  const av = rep.avoid || [];
  $("#avoidList").innerHTML = av.length ? `<div class="avoid">${av.slice(0, 8).map(a => `<div><button class="linkbtn small" data-s="${esc(a.symbol)}">${esc(a.symbol)}</button> · ${esc(a.phase)} · ${esc(a.why)}</div>`).join("")}</div>` : `<p class="note">Nada que destacar.</p>`;
}
function emptyCard(){ return `<div class="card empty"><h2>Hoy ningún activo califica</h2><p>El radar prefiere no operar a forzar una entrada. Mantener liquidez también es una decisión.</p></div>`; }
function oppCard(r){
  return `<button class="opp" data-s="${esc(r.symbol)}">${ring(r.score)}
    <div><div class="t">${esc(r.symbol)}<small>${esc(r.name || "")}</small></div><div class="m">${phase(r.phase)} · 30 d ${pctTxt(r.chg_30d)} · manip. ${r.manipulation_risk ?? "—"}</div></div>
    ${act(r.action)}
    <div class="lv"><div><span>Entrada</span><b>${px(r.entry_low)}–${px(r.entry_high)}</b></div><div><span>Stop</span><b class="neg">${px(r.stop)}</b></div><div><span>TP2</span><b class="pos">${px(r.tp2)}</b></div><div><span>R/B</span><b>${num(r.rr)}</b></div></div>
  </button>`;
}
function renderDashAlerts(al){
  $("#dashAlerts").innerHTML = al.length ? al.slice(0, 5).map(a => `<div class="mini-al"><b>${esc(a.symbol)}</b> · ${esc(a.label)} <span class="muted">${ago(a.at)}</span></div>`).join("") : `<p class="note">Sin alertas todavía.</p>`;
}
document.addEventListener("click", e => { const t = e.target.closest("[data-s]"); if (t && !e.target.closest("[data-pid]")) detail(t.dataset.s); });

/* ---------- 2. Oportunidades tempranas · 4. Rupturas ---------- */
function renderEarly(rep){
  const E = rep.early || [];
  $("#earlyCards").innerHTML = E.length ? E.map(oppCard).join("") :
    `<div class="card empty"><h2>Sin pre-explosiones ni acumulaciones válidas</h2><p>Ninguna moneda muestra a la vez compresión, volumen creciente y precio cerca de la resistencia sin haber corrido ya.</p></div>`;
}
function renderBreakouts(rep){
  const B = rep.breakouts || [];
  const cols = ["Token", "Precio", "Puntaje", "Vol. rel.", "24 h", "30 d", "Manip.", "Retest (zona)", "Stop", "TP1", "TP2", "R/B", "Acción"];
  $("#boTable").innerHTML = `<thead><tr>${cols.map(c => `<th>${c}</th>`).join("")}</tr></thead><tbody>` + (B.length ? B.map(r => `<tr data-s="${esc(r.symbol)}">
    <td class="sym">${esc(r.symbol)}</td><td>${px(r.price)}</td><td>${sc(r.score)}</td><td>${r.rel_volume != null ? "×" + nf1.format(r.rel_volume) : "—"}</td><td>${pct(r.chg_24h)}</td><td>${pct(r.chg_30d)}</td>
    <td>${manip(r.manipulation_risk)}</td><td>${px(r.entry_low)} – ${px(r.entry_high)}</td><td class="neg">${px(r.stop)}</td><td>${px(r.tp1)}</td><td class="pos">${px(r.tp2)}</td><td>${num(r.rr)}</td><td>${act(r.action)}</td></tr>`).join("")
    : emptyRow(cols.length, "Ninguna ruptura con volumen en este escaneo.")) + "</tbody>";
}

/* ---------- 3. Mercado ---------- */
function renderMarket(rep){
  const m = rep.market || {}, pol = m.policy || {};
  $("#mktKpis").innerHTML = mini("Bitcoin", px(m.btc_price), `90 d desde máx. ${pctTxt(m.btc_drawdown_90d_pct)}`) + mini("Volatilidad BTC", m.btc_vol_annual_pct != null ? nf0.format(m.btc_vol_annual_pct) + "%" : "—", "anualizada 20 d") +
    mini("Dominancia BTC", m.btc_dominance != null ? nf1.format(m.btc_dominance) + "%" : "—", `ETH ${num(m.eth_dominance)}%`) + mini("Capitalización total", big(m.total_mcap), `24 h ${pctTxt(m.mcap_chg_24h)}`) +
    mini("Altcoins vs BTC", m.alt_rs_30d != null ? (m.alt_rs_30d >= 0 ? "+" : "") + nf1.format(m.alt_rs_30d) : "—", "mediana 30 d, puntos");
  $("#regimeBox").innerHTML = `<p class="big">${esc(m.regime_label || m.regime || "—")}</p><ul>${(m.regime_reasons || []).map(x => `<li>${esc(x)}</li>`).join("")}</ul>`;
  $("#policyBox").innerHTML = `<div class="meta col"><span>Puntaje mínimo para entrar <b>${pol.min_score ?? "—"}</b></span><span>Exposición máxima en altcoins <b>${pol.max_alt_exposure ?? "—"}%</b></span>
    <span>Multiplicador de tamaño <b>×${pol.size_mult ?? "—"}</b></span><span>Fases que se compran <b>${(pol.phases || []).map(phase).join(", ") || "—"}</b></span></div>`;
  const A = rep.assets || [], ph = $("#fPhase");
  if (ph.options.length < 2) { Object.keys(PH).forEach(p => ph.add(new Option(phase(p), p))); ph.oninput = $("#fSearch").oninput = () => renderMarket(STATE.report); }
  const q = $("#fSearch").value.trim().toUpperCase();
  const rows = A.filter(a => (!q || a.symbol.includes(q) || (a.name || "").toUpperCase().includes(q)) && (!ph.value || a.phase === ph.value));
  const g = {symbol: a => a.symbol, price: a => a.price, chg_24h: a => a.metrics?.chg_24h ?? -999, chg_30d: a => a.metrics?.chg_30d ?? -999, market_cap: a => a.market_cap || 0,
    score: a => a.score ?? -1, rank_score: a => a.rank_score ?? -99, phase: a => a.phase, manip: a => a.manipulation?.risk ?? -1, quality: a => a.quality?.score ?? -1, action: a => a.action || ""};
  rows.sort((a, b) => { const x = g[SORT.key](a), y = g[SORT.key](b); return (x > y ? 1 : x < y ? -1 : 0) * SORT.dir; });
  const H = [["symbol", "Token"], ["price", "Precio"], ["chg_24h", "24 h"], ["chg_30d", "30 d"], ["market_cap", "Capitalización"], ["score", "Puntaje"], ["rank_score", "Ranking"],
    ["phase", "Fase"], ["manip", "Manip."], ["quality", "Calidad datos"], ["action", "Acción"]];
  $("#assetTable").innerHTML = `<thead><tr>${H.map(([k, l]) => `<th data-k="${k}">${l}${SORT.key === k ? (SORT.dir > 0 ? " ↑" : " ↓") : ""}</th>`).join("")}</tr></thead><tbody>` +
    (rows.length ? rows.map(a => a.locked ? `<tr class="locked"><td class="sym">${esc(a.symbol)}</td><td>${px(a.price)}</td><td colspan="2" class="muted">—</td><td>${big(a.market_cap)}</td><td colspan="6" class="muted">Disponible en Pro</td></tr>` :
      `<tr data-s="${esc(a.symbol)}"><td class="sym">${esc(a.symbol)}${a.in_watchlist ? ' <span class="amb" title="En tu lista">★</span>' : ""}</td>
      <td>${px(a.price)}</td><td>${pct(a.metrics?.chg_24h)}</td><td>${pct(a.metrics?.chg_30d)}</td><td>${big(a.market_cap)}</td><td>${sc(a.score)}</td><td>${a.rank_score >= 0 ? nf1.format(a.rank_score) : "—"}</td>
      <td>${phase(a.phase)}</td><td>${manip(a.manipulation?.risk)}</td><td>${a.quality?.score ?? "—"}</td><td>${act(a.action)}</td></tr>`).join("") : emptyRow(11, "Ningún activo coincide con el filtro.")) + "</tbody>";
  $("#assetTable").querySelectorAll("th[data-k]").forEach(th => th.onclick = () => { SORT = {key: th.dataset.k, dir: SORT.key === th.dataset.k ? -SORT.dir : -1}; renderMarket(STATE.report); });
  const sk = rep.skipped || [];
  $("#skipped").textContent = sk.length ? `Fuera del análisis (${sk.length}): ${sk.slice(0, 12).map(s => `${s.symbol} (${s.reason})`).join(", ")}${sk.length > 12 ? "…" : ""}` : "";
}

/* ---------- Ficha de un activo ---------- */
async function detail(sym){
  const a = (STATE?.report?.assets || []).find(x => x.symbol === sym); if (!a || a.locked) return;
  const p = a.plan || {}, mt = a.metrics || {}, mn = a.manipulation || {}, q = a.quality || {};
  const lv = (l, v, c = "") => `<div><span>${l}</span><b class="${c}">${v}</b></div>`;
  const fams = Object.entries(a.families || {}).map(([k, f]) => `<div class="bk"><span>${esc(f.label)} <small class="muted">peso ${f.weight}</small></span>${f.score == null ? `<span class="nd">N/D</span>` :
    `<div class="bar"><i style="width:${Math.round(f.score * 100)}%"></i></div>`}</div>${(f.evidence || []).slice(0, 2).map(e => `<p class="ev">${esc(e)}</p>`).join("")}`).join("");
  const ex = a.exit;
  $("#detailBody").innerHTML = `
    <div class="d-head"><h2 id="dTitle">${esc(a.symbol)}</h2><span class="muted">${esc(a.name || "")}</span>${sc(a.score)}${act(a.action)}</div>
    <div class="d-sub">Fase <b>${phase(a.phase)}</b> · ${esc(a.action_reason || "")} · Cobertura ${a.coverage ?? "—"}% · Calidad de datos ${q.score ?? "—"}/100</div>
    <canvas id="chart"></canvas>
    <div class="plan">
      ${lv("Precio", px(a.price))}${lv("Zona de entrada", `${px(p.entry_low)} – ${px(p.entry_high)}`)}${lv("Ruptura (alternativa)", px(p.trigger_breakout))}
      ${lv("Invalidación / stop", px(p.stop), "neg")}${lv("TP1", px(p.tp1), "pos")}${lv("TP2", px(p.tp2), "pos")}${lv("TP3", px(p.tp3), "pos")}
      ${lv("Riesgo/beneficio (TP2)", num(p.rr))}${lv("Riesgo hasta el stop", pctTxt(-(p.risk_pct || 0)), "neg")}${lv("Tamaño sugerido", px(p.position_usd))}
    </div>
    <p class="note" style="margin-bottom:14px">${esc(p.partials || "")}</p>
    ${ex ? `<div class="card exitbox"><h3>Exit Intelligence: ${esc(ex.decision)}</h3><ul>${ex.reasons.map(x => `<li>${esc(x)}</li>`).join("")}</ul><p class="note">Stop sugerido ${px(ex.suggested_stop)}${ex.trailing_stop ? " · trailing " + px(ex.trailing_stop) : ""}</p></div>` : ""}
    <div class="d-cols">
      <div class="card"><h3>Puntuación por familia</h3>${fams}</div>
      <div class="card"><h3>Por qué esta fase</h3><ul>${(a.phase_reasons || []).map(x => `<li>${esc(x)}</li>`).join("")}</ul>
        <h3>Riesgo de manipulación: ${mn.risk ?? "—"}/100 (${esc(cap(mn.level || ""))})</h3>${(mn.evidence || []).length ? `<ul>${mn.evidence.map(e => `<li>${esc(e.text || e)}</li>`).join("")}</ul>` : `<p class="note">Sin evidencia de manipulación.</p>`}
        <p class="note">${esc(mn.note || "")}${mn.book ? " · Libro de órdenes: " + esc(mn.book) : ""}</p></div>
      <div class="card"><h3>Contexto</h3><div class="meta col"><span>Volumen relativo <b>${mt.rel_volume != null ? "×" + nf1.format(mt.rel_volume) : "—"}</b></span>
        <span>24 h <b>${pctTxt(mt.chg_24h)}</b> · 7 d <b>${pctTxt(mt.chg_7d)}</b> · 30 d <b>${pctTxt(mt.chg_30d)}</b></span><span>Fuerza vs BTC (30 d) <b>${pctTxt(mt.rs_btc_30d)}</b></span>
        <span>Volumen medio <b>${big(mt.avg_volume_usd)}</b></span><span>RSI <b>${mt.rsi != null ? nf0.format(mt.rsi) : "—"}</b> · ATR <b>${num(mt.atr_pct)}%</b></span>
        <span>Capitalización <b>${big(a.market_cap)}</b> · FDV <b>${big(a.fdv)}</b></span>${a.book ? `<span>Spread <b>${num(a.book.spread_pct, 3)}%</b> · Profundidad ±2 % <b>${big(a.book.depth_usd_2pct)}</b></span>` : ""}
        ${(q.issues || []).length ? `<span class="amb">Datos: ${esc(q.issues.join("; "))}</span>` : ""}</div></div>
    </div>
    <div class="row" style="margin-top:16px"><button class="btn a" type="button" id="addPos" data-pid="1"><i data-ic="plus"></i>Registrar posición con este plan</button></div>
    <div class="sec"><h2>Historial del puntaje</h2></div><div class="hist" id="hist">Cargando…</div>`;
  paintIcons($("#detailBody")); openOv("#detail");
  $("#addPos").onclick = () => {
    closeOv($("#detail")); show("portfolio"); openPosForm();
    const f = $("#posForm"), r6 = v => v != null ? +(+v).toPrecision(6) : "";
    f.symbol.value = a.symbol; f.entry.value = r6(p.entry); f.stop.value = r6(p.stop); f.tp1.value = r6(p.tp1); f.tp2.value = r6(p.tp2); f.tp3.value = r6(p.tp3);
  };
  try {
    const c = await api("/api/candles?symbol=" + encodeURIComponent(sym));
    if (c && !c.error && c.c) drawChart($("#chart"), c, p);
    else $("#chart").replaceWith(Object.assign(document.createElement("p"), {className: "note", textContent: "Gráfico disponible para el ranking, las 40 primeras y tus posiciones."}));
  } catch (e) {}
  try {
    const h = await api("/api/history?symbol=" + encodeURIComponent(sym));
    $("#hist").innerHTML = Array.isArray(h) && h.length ? h.slice(-30).reverse().map(([ts, s, ph, pr]) => `${when(ts)} · puntaje ${Math.round(s)} · ${phase(ph)} · ${px(pr)}`).join("<br>") : "Sin historial todavía";
  } catch (e) { $("#hist").textContent = "No se pudo cargar"; }
}
function emaJS(v, n){ const k = 2 / (n + 1); let o = [], p = null; v.forEach((x, i) => { if (i < n - 1) { o.push(null); return; } if (p === null) p = v.slice(0, n).reduce((a, b) => a + b) / n; else p = x * k + p * (1 - k); o.push(p); }); return o; }
function drawChart(cv, c, p){
  const dpr = window.devicePixelRatio || 1, W = cv.clientWidth, H = cv.clientHeight; cv.width = W * dpr; cv.height = H * dpr;
  const g = cv.getContext("2d"); g.scale(dpr, dpr);
  const N = Math.min(W < 500 ? 90 : 160, c.c.length), off = c.c.length - N, e20 = emaJS(c.c, 20).slice(off), e50 = emaJS(c.c, 50).slice(off);
  let hi = Math.max(...c.h.slice(off), p.tp2 ?? -Infinity), lo = Math.min(...c.l.slice(off), p.stop ?? Infinity); const pad = (hi - lo) * .06; hi += pad; lo -= pad;
  const L = 10, R = 64, T = 14, B = 14, w = (W - L - R) / N, y = v => T + (hi - v) / (hi - lo) * (H - T - B);
  g.font = "500 11px Inter, Arial, sans-serif";
  g.strokeStyle = "rgba(191,211,214,.07)"; for (let i = 1; i < 5; i++) { const yy = T + (H - T - B) * i / 5; g.beginPath(); g.moveTo(L, yy); g.lineTo(W - R, yy); g.stroke(); }
  if (p.entry_zone_high && p.entry_ideal) { g.fillStyle = "rgba(240,174,69,.10)"; g.fillRect(L, y(p.entry_zone_high), W - L - R, y(p.entry_ideal) - y(p.entry_zone_high)); }
  for (let i = 0; i < N; i++) {
    const j = off + i, up = c.c[j] >= c.o[j]; g.strokeStyle = g.fillStyle = up ? "#5FBF92" : "#E07A6B"; const x = L + i * w + w / 2;
    g.beginPath(); g.moveTo(x, y(c.h[j])); g.lineTo(x, y(c.l[j])); g.stroke();
    const yo = y(c.o[j]), yc = y(c.c[j]); g.fillRect(x - w * .34, Math.min(yo, yc), Math.max(1, w * .68), Math.max(1, Math.abs(yc - yo)));
  }
  [[e20, "#F0AE45"], [e50, "#7FB3D5"]].forEach(([s, col]) => { g.strokeStyle = col; g.lineWidth = 1.4; g.beginPath(); let st = false; s.forEach((v, i) => { if (v == null) return; const x = L + i * w + w / 2; st ? g.lineTo(x, y(v)) : g.moveTo(x, y(v)); st = true; }); g.stroke(); });
  g.lineWidth = 1;
  const line = (v, col, lab) => { if (v == null || v > hi || v < lo) return; g.strokeStyle = col; g.setLineDash([4, 4]); g.beginPath(); g.moveTo(L, y(v)); g.lineTo(W - R, y(v)); g.stroke(); g.setLineDash([]); g.fillStyle = col; g.fillText(lab, W - R + 6, y(v) + 4); };
  line(p.stop, "#E07A6B", "Stop"); line(p.entry_ideal, "#F0AE45", "Entrada"); line(p.tp1, "#5FBF92", "TP1"); line(p.tp2, "#5FBF92", "TP2"); line(p.tp3, "#5FBF92", "TP3");
  g.fillStyle = "#F0AE45"; g.fillText("EMA 20", L + 6, T + 4); g.fillStyle = "#7FB3D5"; g.fillText("EMA 50", L + 58, T + 4);
}


/* ---------- 10. Alertas ---------- */
const AK = {"PRE-EXPLOSION": ["target", "k-amb"], "BREAKOUT CONFIRMATION": ["up", "k-gain"], "ENTRY ZONE REACHED": ["target", "k-amb"], "STOP LOSS WARNING": ["warn", "k-amb"],
  "STOP LOSS HIT": ["stop", "k-stop"], "TAKE PROFIT REACHED": ["coin", "k-gain"], "DISTRIBUTION DETECTED": ["down", "k-stop"], "RISK": ["warn", "k-stop"], "EXIT": ["down", "k-stop"],
  "MARKET REGIME CHANGE": ["globe", "k-info"], "DAILY SUMMARY": ["info", "k-info"], "WEEKLY SUMMARY": ["info", "k-info"], "SYSTEM": ["info", "k-info"]};
async function loadAlerts(){
  const box = $("#alertList");
  if (ACCOUNTS && ME) {
    $("#tgState").textContent = ME.telegram_linked ? "Telegram vinculado." + (ME.features?.telegram ? "" : " Tu plan no incluye alertas automáticas; los comandos sí funcionan.")
      : "Vincula tu chat de Telegram para recibir las alertas en el celular.";
  }
  try {
    const al = await api("/api/alerts"); let last = "";
    box.innerHTML = al.length ? al.map(a => { const [ic, k] = AK[a.kind] || ["info", "k-info"], d = dayLabel(a.at), h = d !== last ? `<div class="day">${cap(d)}</div>` : ""; last = d;
      return h + `<div class="al"><div class="ic ${k}">${icon(ic)}</div><div><b>${esc(a.symbol)} · ${esc(a.label)}</b><p class="pre">${esc(a.message)}</p></div><time>${new Date(a.at).toLocaleTimeString("es-CO", {hour: "numeric", minute: "2-digit"})}</time></div>`; }).join("")
      : `<div class="card empty"><h2>Sin alertas todavía</h2><p>Aquí aparecen pre-explosiones, rupturas, cambios de régimen, riesgos, salidas y los resúmenes diario y semanal.</p></div>`;
  } catch (e) { box.innerHTML = `<p class="note">No se pudieron cargar las alertas.</p>`; }
}
$("#tgLinkBtn").onclick = async () => {
  const r = await post("/api/telegram/link");
  $("#tgCode").innerHTML = r.code ? `Envía <b>/start ${esc(r.code)}</b> al bot de Crypto Radar en Telegram (válido 15 min).` : esc(r.error || "No disponible");
};

/* ---------- 7. Cartera · 6. Salidas ---------- */
function progBar(lo, hi, cur, loLab, hiLab){
  if (lo == null || hi == null || cur == null || hi <= lo) return "";
  const pos = Math.max(0, Math.min(100, (cur - lo) / (hi - lo) * 100));
  return `<div><div class="prog"><span class="st"></span><span class="tg"></span><i style="left:${pos}%"></i></div><div class="ends"><span>${loLab} ${px(lo)}</span><span>${hiLab} ${px(hi)}</span></div></div>`;
}
function openPosForm(){ $("#posForm").classList.remove("hidden"); $("#newPos").classList.add("hidden"); }
function closePosForm(){ $("#posForm").classList.add("hidden"); $("#newPos").classList.remove("hidden"); $("#posForm").reset(); $("#posMsg").textContent = ""; }
$("#newPos").onclick = () => { openPosForm(); $("#posForm").symbol.focus(); };
$("#posCancel").onclick = closePosForm;
const DEC = {"MANTENER": "b-watch", "PROTEGER GANANCIAS": "b-wait", "REDUCIR POSICIÓN": "b-avoid", "CERRAR POSICIÓN": "b-avoid"};
async function loadPositions(){
  let ps = [];
  try { ps = await api("/api/positions"); } catch (e) { return; }
  if (!Array.isArray(ps)) { const msg = `<div class="card empty"><h2>${esc(ps?.error || "No disponible")}</h2><p>Mejora tu plan en Configuración.</p></div>`; $("#posOpen").innerHTML = msg; $("#exitCards").innerHTML = msg; return; }
  const open = ps.filter(p => p.status === "OPEN"), closed = ps.filter(p => p.status !== "OPEN");
  const wins = closed.filter(p => (p.pnl_pct || 0) > 0).length, avg = closed.length ? closed.reduce((s, p) => s + (p.pnl_pct || 0), 0) / closed.length : null;
  $("#posKpis").innerHTML = mini("Abiertas", open.length) + mini("Cerradas", closed.length) + mini("Ganadoras", closed.length ? Math.round(wins / closed.length * 100) + "%" : "—", closed.length ? `${wins} de ${closed.length}` : "") + mini("Resultado medio", avg != null ? pct(avg) : "—");
  $("#posOpen").innerHTML = open.length ? open.map(p => { const tgt = p.tp3 || p.tp2 || p.tp1, d = (p.exit || {}).decision; return `
    <div class="pcard"><div class="head"><div><span class="sym">${esc(p.symbol)}</span> <span class="tag">${p.paper ? "Simulada" : "Real"}</span> ${d ? `<span class="badge ${DEC[d]}">${esc(cap(d))}</span>` : ""}</div><div class="pl">${pct(p.pnl_pct)}</div></div>
      <div class="meta"><span>Entrada <b>${px(p.entry)}</b></span><span>Ahora <b>${px(p.last_price)}</b></span><span>Stop <b>${px(p.stop)}</b></span><span>Objetivos <b>${(p.hits || []).join(", ").toUpperCase() || "ninguno"}</b></span></div>
      ${progBar(p.stop, tgt, p.last_price, "Stop", "Objetivo")}
      <div class="mini-actions"><button class="btn" data-pid="${esc(p.id)}" data-act="close">Cerrar</button><button class="btn" data-pid="${esc(p.id)}" data-act="del">Eliminar</button></div>
    </div>`; }).join("") : `<div class="card empty"><h2>No tienes posiciones abiertas</h2><p>Registra una desde la ficha de cualquier oportunidad o con el botón de arriba.</p></div>`;
  $("#exitCards").innerHTML = open.length ? open.map(p => { const x = p.exit; return `<div class="pcard"><div class="head"><div><span class="sym">${esc(p.symbol)}</span> ${x ? `<span class="badge ${DEC[x.decision]}">${esc(cap(x.decision))}</span>` : '<span class="tag">Pendiente del próximo escaneo</span>'}</div><div class="pl">${pct(p.pnl_pct)}</div></div>
      ${x ? `<ul>${x.reasons.slice(0, 4).map(r => `<li>${esc(r)}</li>`).join("")}</ul><div class="meta"><span>Ganancia <b>${rTxt(x.gain_R)} el riesgo</b></span><span>Vender <b>${nf0.format((x.sell_fraction || 0) * 100)}%</b></span><span>Stop sugerido <b>${px(x.suggested_stop)}</b></span>${x.trailing_stop ? `<span>Trailing 3 ATR <b>${px(x.trailing_stop)}</b></span>` : ""}</div>` : ""}
    </div>`; }).join("") : `<div class="card empty"><h2>Sin posiciones que evaluar</h2><p>Cuando registres una posición, aquí verás cada día si conviene mantener, proteger, reducir o cerrar.</p></div>`;
  $("#posClosed").innerHTML = `<thead><tr><th>Token</th><th>Tipo</th><th>Entrada</th><th>Salida</th><th>Resultado</th><th>Abierta</th><th>Cerrada</th></tr></thead><tbody>` +
    (closed.length ? closed.map(p => `<tr><td class="sym">${esc(p.symbol)}</td><td>${p.paper ? "Simulada" : "Real"}</td><td>${px(p.entry)}</td><td>${px(p.exit_price)}</td><td>${pct(p.pnl_pct)}</td><td>${when(tsIso(p.opened_at))}</td><td>${when(tsIso(p.closed_at))}</td></tr>`).join("")
      : emptyRow(7, "Aún no hay posiciones cerradas.")) + "</tbody>";
}
const tsIso = v => typeof v === "number" ? new Date(v * 1000).toISOString() : v;
document.addEventListener("click", async e => {
  const b = e.target.closest("[data-act][data-pid]"); if (!b) return;
  const id = b.dataset.pid;
  if (b.dataset.act === "close") {
    const v = await ask({title: "Cerrar posición", text: "Escribe el precio de salida. Si lo dejas vacío, se usa el último precio.", input: true, placeholder: "Último precio", ok: "Cerrar posición"});
    if (v === null) return;
    await post(`/api/positions/${encodeURIComponent(id)}/close`, {price: v.replace(",", ".")}); toast("Posición cerrada"); loadPositions();
  } else {
    if (!await ask({title: "¿Eliminar esta posición?", text: "Se borra del historial y no se puede deshacer.", ok: "Eliminar"})) return;
    await post(`/api/positions/${encodeURIComponent(id)}/delete`); toast("Posición eliminada"); loadPositions();
  }
});
$("#posForm").onsubmit = async e => {
  e.preventDefault(); const f = e.target, b = Object.fromEntries(new FormData(f));
  for (const k of ["entry", "qty", "stop", "tp1", "tp2", "tp3"]) if (b[k]) b[k] = b[k].replace(",", ".");
  b.paper = f.paper.checked;
  try { const r = await post("/api/positions", b); if (r.error) { $("#posMsg").textContent = cap(r.error); return; } }
  catch (err) { $("#posMsg").textContent = "No se pudo guardar"; return; }
  closePosForm(); toast("Posición registrada"); loadPositions();
};
$("#sizer").oninput = () => {
  const f = n => parseFloat(($("#sizer").querySelector(`[name=${n}]`).value || "").replace(",", "."));
  const cap_ = f("cap"), risk = f("risk"), en = f("entry"), st = f("stop");
  if (!(cap_ > 0 && risk > 0 && en > 0 && st > 0 && st < en)) { $("#sizerOut").textContent = "Escribe capital, riesgo, entrada y un stop por debajo de la entrada."; return; }
  const riskUsd = cap_ * risk / 100, value = Math.min(riskUsd / (en - st) * en, cap_ * .2);
  $("#sizerOut").innerHTML = `Comprar <b>${px(value)}</b> (${nf2.format(value / en)} unidades). Si salta el stop pierdes <b class="neg">${px(value / en * (en - st))}</b> (${nf2.format(value / en * (en - st) / cap_ * 100)} % del capital).${value >= cap_ * .2 - 1e-9 ? " Recortado al máximo de 20 % por activo." : ""}`;
};

/* ---------- 5. Memecoins ---------- */
const REASON = {OBJETIVO: "Objetivo", STOP: "Stop", TIEMPO: "Tiempo"};
async function loadMemes(){
  try { MEMES = await api("/api/memes"); } catch (e) { return; }
  if (MEMES?.error) { $("#memeList").innerHTML = `<div class="card empty"><h2>${esc(MEMES.error)}</h2></div>`; return; }
  const s = MEMES.stats || {}, st = MEMES.status || {};
  $("#memeStats").innerHTML = mini("Monedas vigiladas", (MEMES.radar?.coins || []).length) + mini("Señales", s.signals ?? 0) + mini("Abiertas", s.open ?? 0) +
    mini("Aciertos", s.win_rate != null ? nf0.format(s.win_rate) + "%" : "—") + mini("Resultado en vivo", s.closed ? pct(s.portfolio_pct) : "—");
  $("#memeStatus").textContent = (st.checking ? "Revisando… · " : "") + "Última revisión " + ago(st.last_check) + (st.last_error ? " · " + st.last_error : "");
  renderMemes();
}
function renderMemes(){
  if (!MEMES) return;
  $$("#memeSeg button").forEach(b => b.classList.toggle("on", b.dataset.m === MEME_TAB));
  const E = t => `<div class="card empty"><h2>${t[0]}</h2><p>${t[1]}</p></div>`;
  let html = "";
  if (MEME_TAB === "radar") { const C = MEMES.radar?.coins || [];
    html = C.length ? `<div class="tbl"><table><thead><tr><th>Token</th><th>Tipo</th><th>Antigüedad</th><th>Precio</th><th>Liquidez/día</th><th>Vol. rel.</th><th>7 d</th><th>30 d</th><th>Desde máx.</th><th>Cap.</th><th>FDV</th><th>Fase</th><th>Riesgo</th><th>On-chain</th></tr></thead><tbody>` +
      C.map(c => `<tr title="${esc((c.meme_risk_reasons || []).join(" · "))}"><td class="sym">${esc(c.symbol)}</td><td><span class="tag">${esc(c.age_label)}</span></td><td>${esc(c.age_text)}</td><td>${px(c.price)}</td><td>${big(c.avg_volume_usd)}</td>
        <td>${c.rel_volume != null ? "×" + nf1.format(c.rel_volume) : "—"}</td><td>${pct(c.chg_7d)}</td><td>${pct(c.chg_30d)}</td><td>${pct(c.from_high_pct)}</td><td>${big(c.market_cap)}</td><td>${big(c.fdv)}</td>
        <td>${phase(c.phase)}</td><td class="${c.meme_risk >= 50 ? "neg" : c.meme_risk >= 25 ? "amb" : ""}">${c.meme_risk}</td><td class="muted" title="${esc(c.onchain?.holders || "")}">N/D</td></tr>`).join("") + "</tbody></table></div>"
      : E(["El radar aún no se ha ejecutado", "Se actualiza cada hora."]); }
  if (MEME_TAB === "signals") html = (MEMES.signals || []).map(x => `<div class="sig"><div class="head"><span class="sym">${esc(x.symbol)}</span><span class="badge ${x.paper ? "b-buy" : "b-watch"}">${x.paper ? "En práctica" : "Sin cupo"}</span></div>
      <div class="meta"><span>Señal <b>${esc(x.signal_day)}</b></span><span>Entrada <b>${px(x.entry)}</b></span><span>Stop <b class="neg">${px(x.stop)}</b></span><span>Objetivo <b class="pos">${px(x.target)}</b></span></div></div>`).join("")
      || E(["Aún no hay señales", "Son poco frecuentes por diseño."]);
  if (MEME_TAB === "open") html = (MEMES.open || []).map(t => `<div class="sig"><div class="head"><span class="sym">${esc(t.symbol)}</span>${pct((t.last / t.entry - 1) * 100)}</div>
      <div class="meta"><span>Entrada <b>${px(t.entry)}</b></span><span>Ahora <b>${px(t.last)}</b></span><span>Vence <b>${when(t.expires)}</b></span></div>${progBar(t.stop, t.target, t.last, "Stop", "Objetivo")}</div>`).join("")
      || E(["Sin operaciones abiertas", "Cuando salga una señal aparecerá aquí."]);
  if (MEME_TAB === "closed") html = (MEMES.closed || []).length ? `<div class="tbl"><table><thead><tr><th>Token</th><th>Señal</th><th>Entrada</th><th>Salida</th><th>Cómo terminó</th><th>Resultado</th></tr></thead><tbody>` +
      MEMES.closed.map(t => `<tr><td class="sym">${esc(t.symbol)}</td><td>${esc(t.signal_day)}</td><td>${px(t.entry)}</td><td>${px(t.exit)}</td><td>${esc(REASON[t.reason] || t.reason)}</td><td>${pct(t.pnl_pct)}</td></tr>`).join("") + "</tbody></table></div>"
      : E(["Aún no hay operaciones cerradas", "El historial muestra todas, ganadoras y perdedoras."]);
  $("#memeList").innerHTML = html;
}
$("#memeSeg").onclick = e => { const b = e.target.closest("[data-m]"); if (b) { MEME_TAB = b.dataset.m; renderMemes(); } };
$("#memeCheck").onclick = async ev => {
  const b = ev.currentTarget; b.disabled = true;
  try { const r = await post("/api/memes/check"); toast(r.ok ? "Revisando memecoins…" : (r.msg || r.error || "No se pudo revisar")); } catch (e) {}
  setTimeout(() => { loadMemes(); b.disabled = false; }, 8000);
};

/* ---------- 8. Backtesting ---------- */
function mrow(label, m){
  if (!m) return "";
  return `<tr><td>${label}</td><td>${pct(m.total_return_pct)}</td><td>${m.cagr_pct != null ? pct(m.cagr_pct) : "—"}</td><td>${m.trades}</td><td>${m.win_rate_pct ?? "—"}%</td>
    <td>${m.profit_factor ?? "—"}</td><td>${m.avg_R ?? "—"}</td><td>${m.sharpe ?? "—"}</td><td>${m.sortino ?? "—"}</td><td class="neg">${num(m.max_drawdown_pct)}%</td><td>${m.avg_exposure_pct ?? "—"}%</td><td>${px(m.fees_usd)}</td>
    <td>${m.btc_buy_hold_pct != null ? pct(m.btc_buy_hold_pct) : "—"}</td></tr>`;
}
const MH = `<thead><tr><th>Periodo</th><th>Retorno</th><th>CAGR</th><th>Operaciones</th><th>Acierto</th><th>Profit factor</th><th>R medio</th><th>Sharpe</th><th>Sortino</th><th>Máx. caída</th><th>Exposición</th><th>Comisiones</th><th>BTC comprar y mantener</th></tr></thead>`;
function groupTable(title, g){
  const rows = Object.entries(g || {}).sort((a, b) => b[1].trades - a[1].trades);
  return rows.length ? `<div class="card"><h3 class="h3">${title}</h3><div class="tbl"><table><thead><tr><th></th><th>Operaciones</th><th>Acierto</th><th>Resultado (USD)</th></tr></thead><tbody>${rows.map(([k, v]) =>
    `<tr><td>${esc(PH[k] || k)}</td><td>${v.trades}</td><td>${v.win_rate_pct}%</td><td><span class="${v.pnl_usd >= 0 ? "pos" : "neg"}">${px(v.pnl_usd)}</span></td></tr>`).join("")}</tbody></table></div></div>` : "";
}
async function loadBacktest(){
  let r; try { r = await api("/api/backtest/results"); } catch (e) { return; }
  if (r?._status === 402) { $("#btBox").innerHTML = `<div class="card empty"><h2>Plan Élite</h2><p>${esc(r.error)}</p></div>`; return; }
  if (!r || r.available === false || !r.base_full) { $("#btBox").innerHTML = `<div class="card empty"><h2>Aún no hay resultados</h2><p>${esc(r?.note || "")}</p></div>`; return; }
  const c = r.calibration || {}, wf = r.walk_forward || {}, sv = r.score_validation || {};
  $("#btBox").innerHTML = `
    <p class="note">Simulación de cartera con ${r.coins} monedas de Binance (${esc(r.period?.[0])} → ${esc(r.period?.[1])}), universo de las ${r.universe_size} más negociadas cada día, señal al cierre y entrada desde la vela siguiente, comisión ${r.defaults?.fee_pct}% + deslizamiento ${r.defaults?.slippage_pct}% + spread, stops pesimistas. Generado ${esc(r.generated)}.</p>
    <div class="tbl"><table>${MH}<tbody>${mrow("Completo (parámetros por defecto)", r.base_full)}${mrow("Dentro de muestra (hasta " + esc(r.split) + ")", r.base_is)}${mrow("Fuera de muestra (desde " + esc(r.split) + ")", r.base_oos)}
      ${mrow("Calibrado en muestra → resultado fuera de muestra", c.oos)}</tbody></table></div>
    <div class="card"><h3 class="h3">Walk-forward anual (parámetros elegidos con los 2 años previos)</h3><div class="tbl"><table><thead><tr><th>Año</th><th>Retorno</th><th>Operaciones</th><th>Profit factor</th><th>Sharpe</th><th>Máx. caída</th><th>BTC</th></tr></thead><tbody>
      ${(wf.years || []).map(w => `<tr><td>${w.year}</td><td>${pct(w.test.total_return_pct)}</td><td>${w.test.trades}</td><td>${w.test.profit_factor ?? "—"}</td><td>${w.test.sharpe ?? "—"}</td><td class="neg">${num(w.test.max_drawdown_pct)}%</td><td>${pct(w.test.btc_buy_hold_pct)}</td></tr>`).join("")}
      <tr><td><b>Encadenado</b></td><td colspan="6">${pct(wf.chained_return_pct)}</td></tr></tbody></table></div></div>
    <div class="card"><h3 class="h3">Sensibilidad (periodo completo)</h3><div class="tbl"><table>${MH}<tbody>${Object.entries(r.sensitivity || {}).map(([k, m]) => mrow(esc(k), m)).join("")}</tbody></table></div></div>
    <div class="card"><h3 class="h3">¿La puntuación predice? Rendimiento a 20 días por quintil de puntaje (fuera de muestra)</h3><div class="tbl"><table><thead><tr><th>Quintil</th><th>Puntaje</th><th>Muestras</th><th>Media 20 d</th><th>Exceso vs universo</th><th>% que supera al universo</th></tr></thead><tbody>
      ${(sv.oos?.quintiles || []).map(q => `<tr><td>${q.quintile}</td><td>${q.score_min}–${q.score_max}</td><td>${q.n}</td><td>${pct(q.fwd20_mean_pct)}</td><td>${pct(q.excess_mean_pct)}</td><td>${q.hit_rate_pct}%</td></tr>`).join("")}</tbody></table></div>
      <p class="note">Correlación por rangos (IC) con el exceso de rendimiento: ${Object.entries(sv.oos?.rank_ic || {}).map(([k, v]) => `${esc(k)} ${v ?? "—"}`).join(" · ")}</p></div>
    <div class="grid2">${groupTable("Por régimen", r.base_full.by_regime)}${groupTable("Por fase de entrada", r.base_full.by_phase)}${groupTable("Por liquidez", r.base_full.by_cap_bucket)}${groupTable("Por motivo de salida", r.base_full.by_exit)}</div>
    <p class="note">Resultados pasados no garantizan resultados futuros. Sesgo de supervivencia parcial: las monedas retiradas de Binance antes de la descarga no están en los datos.</p>`;
}

/* ---------- 9. Rendimiento ---------- */
let JOURNAL = [];
async function loadJournal(){
  let j; try { j = await api("/api/journal"); } catch (e) { return; }
  const s = j.stats || {}; JOURNAL = j.items || [];
  $("#jStats").innerHTML = mini("Señales publicadas", s.signals ?? 0) + mini("En curso", s.open ?? 0) + mini("Terminadas", s.closed ?? 0) +
    mini("Aciertos", s.win_rate != null ? nf0.format(s.win_rate) + "%" : "—", "de las terminadas") +
    mini("Resultado medio", s.avg_R != null ? `<span class="${s.avg_R >= 0 ? "pos" : "neg"}">${rTxt(s.avg_R)}</span>` : "—", "veces lo arriesgado") +
    mini("Acumulado", `<span class="${(s.total_R || 0) >= 0 ? "pos" : "neg"}">${rTxt(s.total_R || 0)}</span>`, "veces lo arriesgado");
  $("#jTable").innerHTML = `<thead><tr><th>Fecha</th><th>Token</th><th>Puntaje</th><th>Fase</th><th>Mercado</th><th>Entrada</th><th>Stop</th><th>TP1</th><th>TP2</th><th>TP3</th><th>Alcanzado</th><th>Estado</th><th>Resultado</th></tr></thead><tbody>` +
    (JOURNAL.length ? JOURNAL.map(x => `<tr><td>${when(x.at)}</td><td class="sym">${esc(x.symbol)}</td><td>${sc(x.score)}</td><td>${phase(x.phase)}</td><td>${esc(cap(x.regime))}</td>
      <td>${px(x.entry)}</td><td class="neg">${px(x.stop)}</td><td>${px(x.tp1)}</td><td>${px(x.tp2)}</td><td>${px(x.tp3)}</td><td>${(x.hits || []).join(", ").toUpperCase() || "—"}</td>
      <td>${x.status === "OPEN" ? '<span class="badge b-watch">En curso</span>' : '<span class="badge b-wait">Terminada</span>'}</td>
      <td class="${(x.r_multiple || 0) >= 0 ? "pos" : "neg"}">${x.r_multiple != null ? rTxt(x.r_multiple) : "—"}</td></tr>`).join("")
      : emptyRow(13, "Aún no hay señales registradas.")) + "</tbody>";
}

/* ---------- Exportar (CSV) ---------- */
$("#exportBtn").onclick = () => {
  const rep = STATE?.report || {}; let rows = [];
  if (VIEW === "dash") rows = [["#", "Token", "Puntaje", "Fase", "Entrada desde", "Entrada hasta", "Stop", "TP1", "TP2", "TP3", "R/B", "Manipulación", "Acción"],
    ...(rep.ranking || []).map(r => [r.rank, r.symbol, Math.round(r.score), r.phase, r.entry_low, r.entry_high, r.stop, r.tp1, r.tp2, r.tp3, r.rr?.toFixed(2), r.manipulation_risk, r.action])];
  else if (VIEW === "market") rows = [["Token", "Precio", "Capitalización", "Puntaje", "Fase", "Acción"], ...(rep.assets || []).filter(a => !a.locked).map(a => [a.symbol, a.price, a.market_cap, Math.round(a.score), a.phase, a.action])];
  else if (VIEW === "perf") rows = [["Fecha", "Token", "Puntaje", "Fase", "Entrada", "Stop", "TP1", "TP2", "TP3", "Estado", "Resultado (R)"], ...JOURNAL.map(x => [x.at, x.symbol, Math.round(x.score), x.phase, x.entry, x.stop, x.tp1, x.tp2, x.tp3, x.status, x.r_multiple])];
  if (rows.length < 2) return toast("No hay datos para exportar");
  const csv = rows.map(r => r.map(v => `"${String(v ?? "").replace(/"/g, '""')}"`).join(";")).join("\n");
  const a = Object.assign(document.createElement("a"), {href: URL.createObjectURL(new Blob(["﻿" + csv], {type: "text/csv"})), download: `crypto-radar-${VIEW}-${new Date().toISOString().slice(0, 10)}.csv`});
  document.body.append(a); a.click(); a.remove();
  pilotEvent({event: "export_csv"});
};

/* ---------- 11. Configuración ---------- */
async function loadSettings(){
  if (ACCOUNTS && ME) {
    const until = ME.plan_until ? new Date(ME.plan_until * 1000).toLocaleDateString("es-CO") : null;
    $("#accBox").innerHTML = `<div class="meta col"><span>Usuario <b>${esc(ME.username || ME.email)}</b></span><span>Plan <b>${esc(ME.plan_label)}</b>${until ? ` hasta ${until}` : ""}</span></div>`;
    try {
      const b = await api("/api/billing/status");
      const P = b.prices_usd || {}, can = b.wompi || b.crypto;
      $("#plansBox").innerHTML = `<div class="plans">${[["pro", "Pro"], ["elite", "Élite"]].map(([k, l]) => `<div class="card"><h3>${l}</h3><p>US$${P[k + "_month"]}/mes · US$${P[k + "_year"]}/año</p>
        <div class="row">${b.wompi ? `<button class="btn a" data-buy="${k}" data-per="month" data-prov="wompi">Mensual con tarjeta/PSE</button><button class="btn" data-buy="${k}" data-per="year" data-prov="wompi">Anual</button>` : ""}
        ${b.crypto ? `<button class="btn" data-buy="${k}" data-per="month" data-prov="crypto">Mensual con USDT</button>` : ""}</div></div>`).join("")}</div>
        ${can ? "" : `<p class="note">${b.pilot ? "<b>Piloto cerrado:</b> los pagos están desactivados y no se cobra nada. " : "Los pagos aún no están habilitados en este servidor. "}Ningún plan se activa sin un pago confirmado por el proveedor; durante el piloto los planes los asigna el administrador.</p>`}`;
    } catch (e) {}
    const us = ME.settings || {}, f = $("#userSet");
    f.capital_usd.value = us.capital_usd ?? ""; f.risk_per_trade_pct.value = us.risk_per_trade_pct ?? ""; f.watchlist.value = (us.watchlist || []).join(", "); f.alerts_telegram.checked = us.alerts_telegram !== false;
    renderMfa();
    if (ME.is_admin) loadAdmin();
    if (!ME.is_admin || ME.totp_setup_required) return;
  }
  let s; try { s = await api("/api/settings"); } catch (e) { return; }
  const f = $("#setForm");
  for (const [k, v] of Object.entries(s || {})) {
    const el = f.elements[k]; if (!el) continue;
    if (el.type === "checkbox") el.checked = !!v;
    else if (Array.isArray(v)) el.value = v.join(", ");
    else if (v && typeof v === "object") continue;
    else el.value = v ?? "";
  }
}
document.addEventListener("click", async e => {
  const b = e.target.closest("[data-buy]"); if (!b) return;
  b.disabled = true;
  try { const r = await post("/api/billing/checkout", {plan: b.dataset.buy, period: b.dataset.per, provider: b.dataset.prov});
    if (r.url) location.href = r.url; else toast(r.error || "No se pudo iniciar el pago"); }
  finally { b.disabled = false; }
});
const ST_LABEL = {pending: "Pendiente", active: "Activo", rejected: "Rechazado"};
const PLAN_OPTS = `<option value="free">Libre</option><option value="pro">Pro</option><option value="elite">Élite</option>`;
/* Verificación en dos pasos (TOTP) */
function renderMfa(){
  const box = $("#mfaBox"); if (!box || !ME) return;
  if (ME.totp_enabled) { box.innerHTML = `<h3 class="h3">Verificación en dos pasos</h3><p class="note">Activa. Al entrar se te pide el código de 6 dígitos de tu app de autenticación.</p>`; return; }
  box.innerHTML = `<h3 class="h3">Verificación en dos pasos</h3>
    <p class="note">${ME.totp_setup_required ? "<b>Obligatoria para administradores.</b> Hasta activarla no puedes aprobar usuarios ni cambiar ajustes del sistema. " : ""}Usa Google Authenticator, Authy, 1Password o similar.</p>
    <form id="mfaStart" class="fgrid" autocomplete="off"><label>Contraseña actual<input name="password" type="password" autocomplete="current-password" required></label>
      ${ME.enroll_token_required ? `<label>Código de alta de administrador<input name="enroll" autocomplete="off" required></label><p class="note">Un solo uso. Lo genera quien administra el servidor: <code>python main.py admin enroll-token</code> o la variable CRYPTO_RADAR_ADMIN_ENROLL_TOKEN.</p>` : ""}
      <div class="row"><button class="btn a" type="submit">Generar clave</button></div></form>
    <div id="mfaStep2" class="hidden"></div><p class="msg" id="mfaMsg"></p>`;
  $("#mfaStart").onsubmit = async e => {
    e.preventDefault();
    const enroll = e.target.enroll ? e.target.enroll.value.trim() : undefined;
    const r = await post("/api/auth/totp/setup", {password: e.target.password.value, enroll_token: enroll});
    if (r.error) { $("#mfaMsg").textContent = r.error; return; }
    const s2 = $("#mfaStep2"); s2.classList.remove("hidden"); e.target.classList.add("hidden");
    s2.innerHTML = `<p class="note">1. En tu app elige «Introducir clave manualmente» y escribe esta clave (tipo: basada en tiempo):</p>
      <p><code class="secret">${esc(r.secret.replace(/(.{4})/g, "$1 ").trim())}</code></p>
      <p class="note">O abre este enlace desde el teléfono: <a href="${esc(r.uri)}">añadir a la app</a></p>
      <form id="mfaConfirm" class="fgrid" autocomplete="off"><label>2. Código de 6 dígitos que muestra la app<input name="code" inputmode="numeric" autocomplete="one-time-code" maxlength="6" required></label>
      <div class="row"><button class="btn a" type="submit">Activar</button></div></form>`;
    $("#mfaConfirm").onsubmit = async ev => {
      ev.preventDefault();
      const x = await post("/api/auth/totp/enable", {code: ev.target.code.value.replace(/\s/g, ""), enroll_token: enroll});
      $("#mfaMsg").textContent = x.error || x.msg || "";
      if (x.ok) setTimeout(() => location.replace("/entrar"), 1800);
    };
  };
}
async function loadAdmin(){
  $("#adminBox").classList.remove("hidden");
  $("#pilotBox")?.classList.remove("hidden"); loadPilotMetrics();
  if (ME && ME.totp_setup_required) { $("#adminUsers").innerHTML = `<p class="note">Activa la verificación en dos pasos (arriba, en Cuenta) para gestionar usuarios y solicitudes.</p>`; return; }
  let u; try { u = await api("/api/admin/users"); } catch (e) { return; }
  if (!Array.isArray(u)) { $("#adminUsers").innerHTML = `<p class="note">${esc(u?.error || "No disponible")}</p>`; return; }
  const pend = u.filter(x => x.status === "pending");
  const badge = $("#adminBadge"); if (badge) { badge.textContent = pend.length; badge.classList.toggle("hidden", !pend.length); }
  const st = x => x.disabled && x.status === "active" ? "Desactivado" : (ST_LABEL[x.status] || "Activo");
  const acts = x => {
    if (x.is_admin) return `<span class="muted">—</span>`;
    if (x.status === "pending" || x.status === "rejected") return `<div class="row adm-row"><select data-plan="${x.id}" aria-label="Plan">${PLAN_OPTS}</select>
      <input data-days="${x.id}" type="number" min="0" max="3650" value="30" aria-label="Días de plan" title="Días de plan (Pro/Élite)">
      <button class="btn a small" data-act="approve" data-id="${x.id}">Aprobar</button>
      ${x.status === "pending" ? `<button class="btn small" data-act="reject" data-id="${x.id}">Rechazar</button>` : ""}
      <button class="btn small" data-act="delete" data-id="${x.id}">Eliminar</button></div>`;
    return `<div class="row adm-row">${x.disabled ? `<button class="btn small" data-act="enable" data-id="${x.id}">Activar</button>`
      : `<button class="btn small" data-act="disable" data-id="${x.id}">Desactivar</button>`}
      <button class="btn small" data-act="delete" data-id="${x.id}">Eliminar</button></div>`;
  };
  const rows = u.map(x => `<tr class="${x.status === "pending" ? "pend" : ""}"><td><b>${esc(x.email)}</b>${x.is_admin ? ' <span class="tag">admin</span>' : ""}</td>
    <td>${esc(st(x))}</td><td>${esc(x.contact || "—")}</td><td class="wrap-cell">${esc(x.request_note || "—")}</td>
    <td>${x.is_admin ? "Élite" : ({free: "Libre", pro: "Pro", elite: "Élite"}[x.plan] || esc(x.plan))}${!x.is_admin && x.plan_until ? " hasta " + new Date(x.plan_until * 1000).toLocaleDateString("es-CO") : ""}</td>
    <td>${when(tsIso(x.created_at))}</td><td>${acts(x)}</td></tr>`).join("");
  const opts = u.filter(x => !x.is_admin).map(x => `<option value="${x.id}">${esc(x.email)}</option>`).join("");
  $("#adminUsers").innerHTML = `
    <p class="note">${pend.length ? `<b>${pend.length} solicitud${pend.length > 1 ? "es" : ""} pendiente${pend.length > 1 ? "s" : ""}.</b> ` : "Sin solicitudes pendientes. "}Nadie entra sin tu aprobación.</p>
    <div class="tbl"><table><thead><tr><th>Usuario</th><th>Estado</th><th>Contacto</th><th>Mensaje</th><th>Plan</th><th>Solicitud</th><th>Acciones</th></tr></thead><tbody>${rows}</tbody></table></div>
    <details class="adm-forms"><summary>Crear usuario o restablecer contraseña</summary>
      <form id="admCreate" class="settings" autocomplete="off"><h4>Crear usuario aprobado</h4>
        <div class="grid2"><label>Usuario<input name="username" required maxlength="32" autocapitalize="none" placeholder="usuario"></label>
        <label>Contraseña inicial<input name="password" type="password" required minlength="10" autocomplete="new-password"></label>
        <label>Plan<select name="plan">${PLAN_OPTS}</select></label><label>Días de plan<input name="days" type="number" min="0" max="3650" value="30"></label></div>
        <div class="row"><button class="btn a" type="submit">Crear</button></div></form>
      <form id="admReset" class="settings" autocomplete="off"><h4>Restablecer contraseña</h4>
        <div class="grid2"><label>Usuario<select name="id">${opts}</select></label>
        <label>Contraseña nueva<input name="password" type="password" required minlength="10" autocomplete="new-password"></label></div>
        <div class="row"><button class="btn" type="submit">Restablecer</button></div></form>
    </details>
    <p class="msg" id="admMsg" role="status"></p>`;
  const msg = t => { const m = $("#admMsg"); if (m) m.textContent = t; };
  $("#admCreate").onsubmit = async e => { e.preventDefault(); const f = e.target;
    const r = await post("/api/admin/user/create", {username: f.username.value.trim().toLowerCase(), password: f.password.value, plan: f.plan.value, days: f.days.value});
    if (r.error) return msg(r.error); await loadAdmin(); msg("Usuario creado."); };
  $("#admReset").onsubmit = async e => { e.preventDefault(); const f = e.target;
    const r = await post("/api/admin/user/password", {id: f.id.value, password: f.password.value});
    if (r.error) return msg(r.error); f.reset(); msg("Contraseña restablecida; se cerraron sus sesiones."); };
}
document.addEventListener("click", async e => {
  const b = e.target.closest("[data-act]"); if (!b) return;
  const id = b.dataset.id, act = b.dataset.act;
  if ((act === "delete" || act === "reject") && b.dataset.confirm !== "1") { b.dataset.confirm = "1"; b.textContent = "¿Seguro?"; setTimeout(() => { b.dataset.confirm = ""; b.textContent = act === "delete" ? "Eliminar" : "Rechazar"; }, 4000); return; }
  b.disabled = true;
  const plan = document.querySelector(`[data-plan="${id}"]`)?.value || "free", days = document.querySelector(`[data-days="${id}"]`)?.value || 0;
  try { const r = await post("/api/admin/user", {id, action: act, plan, days}); if (r.error) { toast(r.error); b.disabled = false; return; } await loadAdmin(); }
  catch (err) { toast("No se pudo contactar el servidor"); b.disabled = false; }
});
$("#setForm").onsubmit = async e => {
  e.preventDefault(); const f = e.target, b = {};
  for (const el of f.elements) { if (!el.name) continue; b[el.name] = el.type === "checkbox" ? el.checked : el.value; }
  try { const r = await post("/api/settings", b); $("#setMsg").textContent = r.error ? r.error : "Guardado. Se aplica en el próximo escaneo."; }
  catch (err) { $("#setMsg").textContent = "No se pudo guardar"; }
  setTimeout(() => $("#setMsg").textContent = "", 5000);
};
$("#userSet").onsubmit = async e => {
  e.preventDefault(); const f = e.target;
  const r = await post("/api/me/settings", {capital_usd: f.capital_usd.value.replace(",", "."), risk_per_trade_pct: f.risk_per_trade_pct.value.replace(",", "."), watchlist: f.watchlist.value, alerts_telegram: f.alerts_telegram.checked});
  $("#userSetMsg").textContent = r.error || "Guardado"; if (r.settings && ME) ME.settings = r.settings;
};
$("#pwForm").onsubmit = async e => {
  e.preventDefault(); const f = e.target;
  const r = await post("/api/auth/password", {old: f.old.value, new: f.new.value});
  $("#accMsg").textContent = r.error || r.msg || ""; if (r.ok) setTimeout(() => location.replace("/entrar"), 1500);
};
$("#logoutBtn").onclick = async () => { try { await post("/api/auth/logout"); } catch (e) {} location.replace("/entrar"); };
$("#logoutAll").onclick = async () => { try { await post("/api/auth/logout_all"); } catch (e) {} location.replace("/entrar"); };
$("#tgTest").onclick = async ev => {
  const b = ev.currentTarget; if (b.disabled) return; b.disabled = true; $("#setMsg").textContent = "Enviando…";
  try { const r = await post("/api/telegram/test"); $("#setMsg").textContent = r.ok ? "Mensaje enviado a Telegram." : "Telegram: " + (r.msg || r.error); }
  catch (e) { $("#setMsg").textContent = "No se pudo contactar el servidor"; }
  finally { setTimeout(() => b.disabled = false, 5000); }
};

/* ---------- Inicio ---------- */
async function boot(){
  paintIcons();
  try {
    const st = await api("/api/public/status");
    ACCOUNTS = !!st?.accounts;
  } catch (e) {}
  if (ACCOUNTS) {
    try { const me = await api("/api/me"); if (me?.user) { ME = me.user; CSRF = me.csrf; PILOT = me.pilot || PILOT; } } catch (e) {}
    if (!ME) { showAuth(); return; }
  }
  hideAuth(); applyUser();
  const start = (location.hash || "").slice(1);
  show(TITLES[start] ? start : "dash");
  refresh(); setInterval(refresh, 20000);
  if (PILOT.survey) renderSurvey(PILOT.survey);
  if (PILOT.metrics) {
    $("#pilotPrivacy")?.classList.remove("hidden");
    const b = $("#pilotWithdraw");
    if (b) b.onclick = async () => {
      const r = await post("/api/piloto/encuesta/retirar", {});
      $("#pilotWithdrawMsg").textContent = r?.ok ? `Listo: ${r.retiradas} respuesta(s) retirada(s).` : (r?.error || "No se pudo");
    };
  }
}

/* ---------- Encuesta del piloto (solo con CRYPTO_RADAR_PILOT_SURVEYS=1) ---------- */
const OPT = {seguro_si: "Seguro que sí", probable_si: "Probablemente sí", no_se: "No sé", probable_no: "Probablemente no",
  seguro_no: "Seguro que no", mensual: "Mensual", anual: "Anual", ninguno: "Ninguno", muy: "Muy decepcionado",
  algo: "Algo decepcionado", nada: "Nada decepcionado", si: "Sí", no: "No",
  historial_auditable: "Historial auditable de señales, con resultados negativos incluidos", alertas_personalizadas: "Alertas con umbrales propios por activo y métrica",
  mas_activos: "Más activos o escaneo más frecuente", api_webhook: "Acceso por API o webhook al ranking",
  equipos: "Varias carteras o cuentas de equipo", soporte_prioritario: "Soporte con tiempo de respuesta escrito"};
function renderSurvey(s){
  const box = $("#surveyBox"); if (!box) return;
  const q = s.preguntas.map(p => {
    const lab = `<span>${esc(p.texto)}</span>`;
    if (p.tipo === "texto") return `<label>${lab}<textarea name="${p.id}" maxlength="500" rows="2"></textarea></label>`;
    if (p.tipo === "usd") return `<label>${lab}<input name="${p.id}" type="number" min="0" max="10000" step="0.5" inputmode="decimal" placeholder="US$"></label>`;
    if (p.tipo === "escala") return `<fieldset><legend>${esc(p.texto)}</legend>${[1,2,3,4,5].map(n => `<label class="chk"><input type="radio" name="${p.id}" value="${n}">${n}</label>`).join("")}</fieldset>`;
    if (p.tipo === "opcion") return `<fieldset><legend>${esc(p.texto)}</legend>${p.opciones.map(o => `<label class="chk"><input type="radio" name="${p.id}" value="${o}">${esc(OPT[o] || o)}</label>`).join("")}</fieldset>`;
    if (p.tipo === "orden") return `<fieldset><legend>${esc(p.texto)}</legend>${p.opciones.map(o => `<label class="chk"><input type="number" min="1" max="${p.opciones.length}" name="${p.id}:${o}" class="rank-in" aria-label="Orden de ${esc(OPT[o] || o)}">${esc(OPT[o] || o)}</label>`).join("")}</fieldset>`;
    return "";
  }).join("");
  box.innerHTML = `<h3 class="h3">${esc(s.titulo)}</h3><p class="note">Encuesta del piloto. Es voluntaria y puedes omitirla. Tus respuestas ayudan a decidir qué construir; no hay premios ni descuentos por responder.</p>
    <form id="surveyForm" class="fgrid">${q}<div class="row"><button class="btn a" type="submit">Enviar</button><button class="btn" type="button" id="surveySkip">Omitir</button><span class="msg" id="surveyMsg"></span></div></form>`;
  box.classList.remove("hidden");
  const send = async (skipped) => {
    const f = $("#surveyForm"), ans = {};
    if (!skipped) s.preguntas.forEach(p => {
      if (p.tipo === "orden") {
        const v = p.opciones.map(o => [o, +f.elements[p.id + ":" + o].value]).filter(x => x[1] > 0).sort((a, b) => a[1] - b[1]).map(x => x[0]);
        if (v.length) ans[p.id] = v;
      } else {
        const el = f.elements[p.id]; const v = el && (el.value ?? "");
        if (v !== "" && v != null) ans[p.id] = p.tipo === "usd" || p.tipo === "escala" ? +v : v;
      }
    });
    const r = await post("/api/piloto/encuesta", {survey: s.id, answers: ans, skipped});
    if (r?.ok) { box.innerHTML = `<p class="note">Gracias.</p>`; setTimeout(() => box.classList.add("hidden"), 2500); }
    else $("#surveyMsg").textContent = r?.error || "No se pudo enviar";
  };
  $("#surveyForm").onsubmit = ev => { ev.preventDefault(); send(false); };
  $("#surveySkip").onclick = () => send(true);
}

/* ---------- Métricas del piloto (administrador) ---------- */
const pctCI = r => r && r.tasa != null ? `${nf1.format(r.tasa * 100)} % <span class="muted">(${r.numerador}/${r.denominador}; IC95 ${nf0.format(r.ic95[0] * 100)}–${nf0.format(r.ic95[1] * 100)} %${r.pendientes ? "; " + r.pendientes + " pendientes" : ""})</span>` : `<span class="muted">sin datos${r && r.pendientes ? " · " + r.pendientes + " pendientes" : ""}</span>`;
async function loadPilotMetrics(){
  const box = $("#pilotBox"); if (!box) return;
  let r; try { r = await api("/api/admin/piloto"); } catch (e) { return; }
  if (!r || r.error) { box.querySelector("div").innerHTML = `<p class="note">${esc(r?.error || "No disponible")}</p>`; return; }
  const t = r.total, s = r.solicitudes;
  const coh = Object.entries(r.cohortes).map(([k, c]) => `<tr><td>${esc(k)}</td><td>${c.aprobados}</td><td>${c.elegibles}</td><td>${c.pendientes}</td><td>${c.activados}</td><td>${c.no_activados}</td><td>${pctCI(c.activacion)}</td><td>${pctCI(c.retencion_30d)}</td><td>${pctCI(c.retencion_60d)}</td></tr>`).join("");
  const pi = t.intencion_de_pago;
  box.querySelector("div").innerHTML = `${r.avisos.map(a => `<p class="note amb">${esc(a)}</p>`).join("")}
    <p class="note">Generado ${new Date(r.generado_utc).toLocaleString()} · solicitudes ${s.total} · aprobadas ${s.aprobadas} · rechazadas ${s.rechazadas} · pendientes ${s.pendientes}</p>
    <table class="tbl"><tbody><tr><th>Activación</th><td>${pctCI(t.activacion)}</td></tr><tr><th>Retención 30 d</th><td>${pctCI(t.retencion_30d)}</td></tr>
    <tr><th>Retención 60 d</th><td>${pctCI(t.retencion_60d)}</td></tr><tr><th>Telegram vinculado</th><td>${pctCI(t.telegram_vinculado)}</td></tr>
    <tr><th>Activos semanales (7 d)</th><td>${r.uso.activos_semanales_ultimos_7_dias}</td></tr><tr><th>Intención de pago (sobre ${pi.elegibles_30d} elegibles a 30 d; usa B5)</th><td>${pctCI(pi.tasa_sobre_elegibles)}</td></tr>
    <tr><th>Intención entre respondientes</th><td>${pctCI(pi.tasa_entre_respondientes)}</td></tr><tr><th>Participación (respondieron / no respondieron)</th><td>${pctCI(pi.participacion)} · ${pi.respondieron} / ${pi.no_respondieron}${pi.aviso ? ` <span class="amb">${esc(pi.aviso)}</span>` : ""}</td></tr>
    <tr><th>Muy decepcionado</th><td>${pctCI(r.encuestas.dia45.muy_decepcionado)}</td></tr><tr><th>Compuerta B</th><td>${esc(r.compuerta_b.lectura)}</td></tr></tbody></table>
    <table class="tbl"><thead><tr><th>Cohorte (semana de aprobación)</th><th>Aprob.</th><th>Elegibles</th><th>Pend.</th><th>Activados</th><th>No activ.</th><th>Activación</th><th>Ret. 30 d</th><th>Ret. 60 d</th></tr></thead><tbody>${coh || `<tr><td colspan="9" class="muted">Sin cohortes</td></tr>`}</tbody></table>`;
}
boot();
