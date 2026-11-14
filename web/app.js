// Crypto Radar · panel. JavaScript sin dependencias.
const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
async function api(p, o) {
  const r = await fetch(p, o);
  let j = null; try { j = await r.json(); } catch (e) {}
  if (!r.ok && !j) throw new Error("El servidor respondió " + r.status);
  return j;
}
const post = (p, b) => api(p, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(b || {})});
function lsGet(k){try{return localStorage.getItem(k)}catch(e){return null}}
function lsSet(k,v){try{localStorage.setItem(k,v)}catch(e){}}

let STATE = null, VIEW = "radar", SORT = {key: "score", dir: -1}, CAT = "", MEME_TAB = "signals", MEMES = null;
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

/* ---------- Navegación ---------- */
const TITLES = {radar: "Radar", assets: "Todos los activos", alerts: "Alertas", positions: "Mi cartera", memes: "Memecoins", journal: "Historial de señales", settings: "Ajustes"};
const LOADERS = {alerts: loadAlerts, positions: loadPositions, memes: loadMemes, journal: loadJournal, settings: loadSettings};
document.addEventListener("click", e => {
  const b = e.target.closest("[data-view]"); if (!b) return;
  if (b.dataset.view === "more") return openOv("#moreSheet");
  closeOv($("#moreSheet")); show(b.dataset.view);
});
function show(v){
  VIEW = v;
  $$("[data-view]").forEach(b => b.classList.toggle("on", b.dataset.view === v || (b.dataset.view === "more" && ["memes", "journal", "settings"].includes(v))));
  $$(".view").forEach(s => s.classList.toggle("on", s.id === "v-" + v));
  $("#viewTitle").textContent = TITLES[v]; document.title = TITLES[v] + " · Crypto Radar";
  $("#exportBtn").classList.toggle("hidden", !["radar", "assets", "journal"].includes(v));
  window.scrollTo(0, 0);
  LOADERS[v]?.();
  if (v === "alerts") { lastAlertSeen = new Date().toISOString(); lsSet("seenAlert", lastAlertSeen); setCount(0); }
  try { history.replaceState(null, "", "#" + v); } catch (e) {}
}
function setCount(n){ $$("[data-count]").forEach(c => { c.textContent = n > 99 ? "99+" : n; c.classList.toggle("hidden", !n); }); }

/* ---------- Escaneo y estado ---------- */
async function scan(){
  try { const r = await post("/api/scan"); toast(r.ok ? "Escaneo iniciado. Tarda unos minutos." : (r.msg || "No se pudo iniciar el escaneo")); }
  catch (e) { toast("No se pudo contactar el servidor"); }
  refresh();
}
$("#scanBtn").onclick = scan; $("#scanBtnM").onclick = scan;
document.addEventListener("click", e => { if (e.target.closest("[data-scan]")) scan(); });

async function refresh(){
  try { STATE = await api("/api/state"); }
  catch (e) { setStatus("bad", "Sin conexión con el servidor"); return; }
  const st = STATE.status || {}, rep = STATE.report || {};
  $("#scanBtn").disabled = $("#scanBtnM").disabled = !!st.scanning;
  $("#scanBtn").querySelector("span").textContent = st.scanning ? "Escaneando…" : "Escanear ahora";
  if (st.scanning) setStatus("busy", st.progress || "Escaneando…");
  else if (st.last_error) setStatus("bad", "Último escaneo con error");
  else setStatus(rep.at ? "ok" : "", rep.at ? "Actualizado " + ago(rep.at) : "Sin escaneos todavía");
  const eb = $("#errBar");
  eb.classList.toggle("hidden", !st.last_error);
  if (st.last_error) eb.textContent = "El último escaneo no terminó: " + st.last_error + ". Se reintentará en el próximo ciclo; los datos mostrados son del último escaneo completo.";
  $("#sideFoot").innerHTML = `Último escaneo: <b>${rep.at ? ago(rep.at) : "nunca"}</b><br>Próximo: ${when(STATE.next_scan)}${STATE.version ? `<br>Versión ${esc(STATE.version)}` : ""}`;
  $("#empty").classList.toggle("hidden", !!rep.at);
  if (rep.at) { renderRadar(rep); renderAssets(rep); }
  try { const al = await api("/api/alerts"); setCount(VIEW === "alerts" ? 0 : al.filter(a => a.at > lastAlertSeen).length); } catch (e) {}
}
function setStatus(cls, txt){ const s = $("#status"); s.className = "status " + cls; s.querySelector("span").textContent = txt; s.title = txt; }

/* ---------- Radar ---------- */
const FG = {"Extreme Fear": "Miedo extremo", "Fear": "Miedo", "Neutral": "Neutral", "Greed": "Codicia", "Extreme Greed": "Codicia extrema"};
function renderRadar(rep){
  const m = rep.market || {}, v = rep.verdict || "", fg = m.fear_greed;
  const vc = v === "OPORTUNIDADES ACTIVAS" ? "v-ok" : v === "ESPERAR ENTRADA" ? "" : "v-cash";
  const mini = (l, val, s, x = "") => `<div class="mini ${x}"><div class="l">${l}</div><div class="v">${val}</div><div class="s">${s}</div></div>`;
  $("#kpis").innerHTML = `<div class="verdict ${vc}"><div class="k">Veredicto del mercado</div><h2>${esc(cap(v))}</h2><p>${esc(rep.verdict_text || "")}</p></div>` +
    mini("Bitcoin", px(m.btc_price), `30 d ${pctTxt(m.btc_chg_30d)}`) +
    mini("Sentimiento", fg ? fg.value : "—", fg ? (FG[fg.label] || fg.label) : "sin dato") +
    mini("Mercado", esc(cap(m.regime || "—")), esc(cap(m.alt_bias || ""))) +
    mini("Exposición máx. altcoins", m.max_alt_exposure != null ? m.max_alt_exposure + "%" : "—", `Dominancia BTC ${num(m.btc_dominance)}%`, "x");
  $("#outlook").textContent = rep.outlook || "";
  $("#rankMeta").textContent = `${rep.analyzed ?? "—"} activos analizados`;
  const R = rep.ranking || [];
  $("#oppCards").innerHTML = R.length ? R.map(r => { const p = r.plan; return `
    <button class="opp" data-s="${esc(r.symbol)}">${ring(r.score)}
      <div><div class="t">${esc(r.symbol)}<small>${esc(r.name || "")}</small></div><div class="m">${esc(cap(r.phase))} · Entrada ${px(p.entry_ideal)}–${px(p.entry_zone_high)}</div></div>
      ${act(r.action)}
      <div class="lv"><div><span>Stop</span><b class="neg">${px(p.stop)}</b></div><div><span>TP1</span><b>${px(p.tp1)}</b></div><div><span>TP2</span><b class="pos">${px(p.tp2)}</b></div><div><span>R/B</span><b>${num(p.rr)}</b></div></div>
    </button>`; }).join("") : `<div class="card empty"><h2>Hoy ningún activo califica</h2><p>El radar prefiere no operar a forzar una entrada. Mantener liquidez también es una decisión.</p></div>`;
  const cols = ["#", "Token", "Puntaje", "Fase", "Zona de entrada", "Stop", "TP1", "TP2", "TP3", "R/B", "Acción"];
  $("#rankTable").innerHTML = `<thead><tr>${cols.map(c => `<th>${c}</th>`).join("")}</tr></thead><tbody>` +
    (R.length ? R.map(r => { const p = r.plan; return `<tr data-s="${esc(r.symbol)}"><td class="muted">${r.rank}</td>
      <td class="sym">${esc(r.symbol)}<small>${esc(r.name || "")}</small></td><td>${sc(r.score)}</td><td>${esc(cap(r.phase))}</td>
      <td>${px(p.entry_ideal)} – ${px(p.entry_zone_high)}</td><td class="neg">${px(p.stop)}</td><td>${px(p.tp1)}</td><td class="pos">${px(p.tp2)}</td><td>${px(p.tp3)}</td>
      <td>${num(p.rr)}</td><td>${act(r.action)}</td></tr>`; }).join("") : emptyRow(11, "Hoy ningún activo califica. Mantener liquidez también es una decisión.")) + "</tbody>";
  const x = rep.extra || {}, L = s => s ? `<button class="linkbtn" data-s="${esc(s)}">${esc(s)}</button>` : `<span class="muted">Ninguno califica</span>`;
  $("#extra").innerHTML = [
    ["Top 3", (x.top3 || []).length ? x.top3.map(L).join(" · ") : L(null)],
    ["Mejor entrada temprana", L(x.best_early_entry)],
    ["Mejor riesgo/beneficio", L(x.best_risk_reward)],
    ["Mayor potencial", L(x.highest_growth)],
    ["Mejor para corto plazo", L(x.short_term_trade)],
    ["Para evitar", (x.avoid || []).length ? `<div class="avoid wide">${x.avoid.slice(0, 4).map(a => `<div><b>${esc(a.symbol)}</b> · ${esc(a.why)}</div>`).join("")}</div>` : `<span class="muted">—</span>`]
  ].map(([h, b]) => `<div class="card${h === "Para evitar" ? " span2" : ""}"><h3>${h}</h3><div class="val">${b}</div></div>`).join("");
}
document.addEventListener("click", e => { const t = e.target.closest("[data-s]"); if (t && !e.target.closest("[data-pid]")) detail(t.dataset.s); });

/* ---------- Todos los activos ---------- */
function renderAssets(rep){
  const A = rep.assets || [], ph = $("#fPhase");
  if (ph.options.length < 2) {
    [...new Set(A.map(a => a.phase))].sort().forEach(p => ph.add(new Option(cap(p), p)));
    ph.oninput = $("#fSearch").oninput = () => renderAssets(STATE.report);
  }
  const cats = [...new Set(A.flatMap(a => a.categories || []))].sort();
  $("#fCats").innerHTML = ["", ...cats].map(c => `<button class="chip ${c === CAT ? "on" : ""}" data-cat="${esc(c)}">${c ? esc(c) : "Todas"}</button>`).join("");
  const q = $("#fSearch").value.trim().toUpperCase();
  const rows = A.filter(a => (!q || a.symbol.includes(q) || (a.name || "").toUpperCase().includes(q)) && (!ph.value || a.phase === ph.value) && (!CAT || (a.categories || []).includes(CAT)));
  const get = {symbol: a => a.symbol, price: a => a.price, chg_24h: a => a.chg_24h ?? -999, chg_30d: a => a.tech?.chg_30d ?? -999, market_cap: a => a.market_cap || 0,
    score: a => a.score, phase: a => a.phase, rsi: a => a.tech?.rsi ?? 0, exit: a => a.exit_risk, rr: a => a.plan?.rr ?? 0, action: a => a.action};
  rows.sort((a, b) => { const x = get[SORT.key](a), y = get[SORT.key](b); return (x > y ? 1 : x < y ? -1 : 0) * SORT.dir; });
  const H = [["symbol", "Token"], ["price", "Precio"], ["chg_24h", "24 h"], ["chg_30d", "30 d"], ["market_cap", "Capitalización"], ["score", "Puntaje"], ["phase", "Fase"],
    ["rsi", "RSI"], ["exit", "Riesgo de salida"], ["rr", "R/B"], ["action", "Acción"]];
  $("#assetTable").innerHTML = `<thead><tr>${H.map(([k, l]) => `<th data-k="${k}">${l}${SORT.key === k ? (SORT.dir > 0 ? " ↑" : " ↓") : ""}</th>`).join("")}</tr></thead><tbody>` +
    (rows.length ? rows.map(a => `<tr data-s="${esc(a.symbol)}"><td class="sym">${esc(a.symbol)}${a.in_watchlist ? ' <span class="amb" title="En tu lista">★</span>' : ""}</td>
      <td>${px(a.price)}</td><td>${pct(a.chg_24h)}</td><td>${pct(a.tech?.chg_30d)}</td><td>${big(a.market_cap)}</td><td>${sc(a.score)}</td><td>${esc(cap(a.phase))}</td>
      <td>${a.tech?.rsi != null ? nf0.format(a.tech.rsi) : "—"}</td><td class="${a.exit_risk >= 50 ? "neg" : ""}">${a.exit_risk ?? "—"}</td><td>${num(a.plan?.rr)}</td><td>${act(a.action)}</td></tr>`).join("")
      : emptyRow(11, "Ningún activo coincide con el filtro.")) + "</tbody>";
  $("#assetTable").querySelectorAll("th[data-k]").forEach(th => th.onclick = () => { SORT = {key: th.dataset.k, dir: SORT.key === th.dataset.k ? -SORT.dir : -1}; renderAssets(STATE.report); });
  const sk = rep.skipped || [];
  $("#skipped").textContent = sk.length ? `Sin datos suficientes: ${sk.slice(0, 12).map(s => s.symbol).join(", ")}${sk.length > 12 ? "…" : ""}` : "";
}
document.addEventListener("click", e => { const c = e.target.closest("[data-cat]"); if (c) { CAT = c.dataset.cat; renderAssets(STATE.report); } });

/* ---------- Ficha de un activo ---------- */
const BK = {technical_structure: "Estructura técnica", volume_and_liquidity: "Volumen y liquidez", on_chain_activity: "Actividad on-chain",
  fundamentals_and_tokenomics: "Fundamentales", market_catalysts: "Catalizadores", risk_reward_ratio: "Riesgo/beneficio", market_sentiment: "Sentimiento"};
const BKMAX = {technical_structure: 20, volume_and_liquidity: 15, on_chain_activity: 15, fundamentals_and_tokenomics: 15, market_catalysts: 15, risk_reward_ratio: 10, market_sentiment: 10};
async function detail(sym){
  const a = (STATE?.report?.assets || []).find(x => x.symbol === sym); if (!a) return;
  const p = a.plan || {}, t = a.tech || {};
  const lv = (l, v, c = "") => `<div><span>${l}</span><b class="${c}">${v}</b></div>`;
  const list = (h, arr) => `<h3>${h}</h3>${(arr || []).length ? `<ul>${arr.slice(0, 6).map(s => `<li>${esc(s)}</li>`).join("")}</ul>` : `<p class="note" style="margin-bottom:12px">Ninguna por ahora</p>`}`;
  $("#detailBody").innerHTML = `
    <div class="d-head"><h2 id="dTitle">${esc(a.symbol)}</h2><span class="muted">${esc(a.name || "")}</span>${sc(a.score)}${act(a.action)}</div>
    <div class="d-sub">Fase: <b>${esc(cap(a.phase))}</b> · Confianza ${esc(a.confidence || "—")} · Datos disponibles ${a.coverage ?? "—"}%${(a.categories || []).length ? " · " + a.categories.map(esc).join(", ") : ""}</div>
    <canvas id="chart"></canvas>
    <div class="plan">
      ${lv("Precio actual", px(a.price))}${lv("Zona de entrada", `${px(p.entry_ideal)} – ${px(p.entry_zone_high)}`)}${lv("Entrada con confirmación", px(p.entry_confirmation))}
      ${lv("Stop", px(p.stop), "neg")}${lv("TP1", px(p.tp1), "pos")}${lv("TP2", px(p.tp2), "pos")}${lv("TP3", px(p.tp3), "pos")}
      ${lv("Riesgo/beneficio", num(p.rr))}${lv("Potencial a TP2", pctTxt(p.return_tp2_pct, 0), "pos")}${lv("Riesgo hasta el stop", pctTxt(-(p.risk_pct || 0)), "neg")}
      ${lv("Tamaño sugerido", px(p.position_usd))}${lv("Pérdida máx. si salta el stop", px(p.risk_usd), "neg")}
    </div>
    ${p.final_exit || p.plan_note ? `<p class="note" style="margin-bottom:14px">${p.final_exit ? `<b>Salida final:</b> ${esc(p.final_exit)}. ` : ""}${esc(p.plan_note || "")}</p>` : ""}
    <div class="d-cols">
      <div class="card">${list("A favor", [...(a.signals_early || []), ...(a.signals_momentum || [])])}${a.catalyst ? `<h3>Catalizador</h3><p class="note">${esc(a.catalyst)}</p>` : ""}</div>
      <div class="card">${list("Señales de salida", a.signals_exit)}${list("Riesgos a tener en cuenta", a.notes)}</div>
      <div class="card"><h3>Cómo se ve cada área</h3>${Object.entries(BK).map(([k, l]) => { const v = a.breakdown?.[k];
        return `<div class="bk"><span>${l}</span>${v == null ? `<span class="nd">sin datos</span>` : `<div class="bar"><i style="width:${Math.round(v / BKMAX[k] * 100)}%"></i></div>`}</div>`; }).join("")}
        <h3 style="margin-top:14px">Contexto</h3><div class="meta"><span>RSI <b>${t.rsi != null ? nf0.format(t.rsi) : "—"}</b></span><span>7 d <b>${pctTxt(t.chg_7d)}</b></span><span>30 d <b>${pctTxt(t.chg_30d)}</b></span><span>90 d <b>${pctTxt(t.chg_90d)}</b></span><span>Desde máximo <b>${pctTxt(t.from_high_pct, 0)}</b></span></div></div>
    </div>
    <div class="row" style="margin-top:16px"><button class="btn a" type="button" id="addPos" data-pid="1"><i data-ic="plus"></i>Registrar posición con este plan</button></div>
    <div class="sec"><h2>Historial del puntaje</h2></div><div class="hist" id="hist">Cargando…</div>`;
  paintIcons($("#detailBody")); openOv("#detail");
  $("#addPos").onclick = () => {
    closeOv($("#detail")); show("positions"); openPosForm();
    const f = $("#posForm"), r6 = v => v != null ? +(+v).toPrecision(6) : "";
    f.symbol.value = a.symbol; f.entry.value = r6(p.entry_ideal); f.stop.value = r6(p.stop); f.tp1.value = r6(p.tp1); f.tp2.value = r6(p.tp2); f.tp3.value = r6(p.tp3);
  };
  try {
    const c = await api("/api/candles?symbol=" + encodeURIComponent(sym));
    if (c && !c.error && c.c) drawChart($("#chart"), c, p);
    else $("#chart").replaceWith(Object.assign(document.createElement("p"), {className: "note", textContent: "El gráfico está disponible para las 40 mejores y para tus posiciones."}));
  } catch (e) {}
  try {
    const h = await api("/api/history?symbol=" + encodeURIComponent(sym));
    $("#hist").innerHTML = h.length ? h.slice(-30).reverse().map(([ts, s, ph, pr]) => `${when(ts)} · puntaje ${Math.round(s)} · ${esc(cap(ph))} · ${px(pr)}`).join("<br>") : "Sin historial todavía";
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

/* ---------- Alertas ---------- */
const AK = {"NEW EARLY ENTRY": ["up", "k-gain"], "BREAKOUT CONFIRMATION": ["up", "k-gain"], "ENTRY ZONE REACHED": ["target", "k-amb"], "STOP LOSS WARNING": ["warn", "k-amb"],
  "STOP LOSS HIT": ["stop", "k-stop"], "TAKE PROFIT REACHED": ["coin", "k-gain"], "DISTRIBUTION DETECTED": ["down", "k-stop"], "BEARISH REVERSAL": ["down", "k-stop"],
  "MARKET REGIME CHANGE": ["globe", "k-info"], "SYSTEM": ["info", "k-info"]};
async function loadAlerts(){
  const box = $("#alertList");
  try {
    const al = await api("/api/alerts"); let last = "";
    box.innerHTML = al.length ? al.map(a => { const [ic, k] = AK[a.kind] || ["info", "k-info"], d = dayLabel(a.at), h = d !== last ? `<div class="day">${cap(d)}</div>` : ""; last = d;
      return h + `<div class="al"><div class="ic ${k}">${icon(ic)}</div><div><b>${esc(a.symbol)} · ${esc(a.label)}</b><p>${esc(a.message)}</p></div><time>${new Date(a.at).toLocaleTimeString("es-CO", {hour: "numeric", minute: "2-digit"})}</time></div>`; }).join("")
      : `<div class="card empty"><h2>Sin alertas todavía</h2><p>Aquí aparecen las entradas, los stops, los objetivos alcanzados y los cambios de mercado. Conecta Telegram en Ajustes para recibirlas en el celular.</p></div>`;
  } catch (e) { box.innerHTML = `<p class="note">No se pudieron cargar las alertas.</p>`; }
}

/* ---------- Cartera ---------- */
function progBar(lo, hi, cur, loLab, hiLab){
  if (lo == null || hi == null || cur == null || hi <= lo) return "";
  const pos = Math.max(0, Math.min(100, (cur - lo) / (hi - lo) * 100));
  return `<div><div class="prog"><span class="st"></span><span class="tg"></span><i style="left:${pos}%"></i></div><div class="ends"><span>${loLab} ${px(lo)}</span><span>${hiLab} ${px(hi)}</span></div></div>`;
}
function openPosForm(){ $("#posForm").classList.remove("hidden"); $("#newPos").classList.add("hidden"); }
function closePosForm(){ $("#posForm").classList.add("hidden"); $("#newPos").classList.remove("hidden"); $("#posForm").reset(); $("#posMsg").textContent = ""; }
$("#newPos").onclick = () => { openPosForm(); $("#posForm").symbol.focus(); };
$("#posCancel").onclick = closePosForm;
async function loadPositions(){
  let ps = [];
  try { ps = await api("/api/positions"); } catch (e) { $("#posOpen").innerHTML = `<p class="note">No se pudieron cargar las posiciones.</p>`; return; }
  const open = ps.filter(p => p.status === "OPEN"), closed = ps.filter(p => p.status !== "OPEN");
  const wins = closed.filter(p => (p.pnl_pct || 0) > 0).length, avg = closed.length ? closed.reduce((s, p) => s + (p.pnl_pct || 0), 0) / closed.length : null;
  const mini = (l, v, s = "") => `<div class="mini"><div class="l">${l}</div><div class="v">${v}</div>${s ? `<div class="s">${s}</div>` : ""}</div>`;
  $("#posKpis").innerHTML = mini("Abiertas", open.length) + mini("Cerradas", closed.length) + mini("Ganadoras", closed.length ? Math.round(wins / closed.length * 100) + "%" : "—", closed.length ? `${wins} de ${closed.length}` : "") + mini("Resultado medio", avg != null ? pct(avg) : "—", "por operación cerrada");
  $("#posOpen").innerHTML = open.length ? open.map(p => { const tgt = p.tp3 || p.tp2 || p.tp1; return `
    <div class="pcard"><div class="head"><div><span class="sym">${esc(p.symbol)}</span> <span class="tag">${p.paper ? "Simulada" : "Real"}</span></div><div class="pl">${pct(p.pnl_pct)}</div></div>
      <div class="meta"><span>Entrada <b>${px(p.entry)}</b></span><span>Ahora <b>${px(p.last_price)}</b></span><span>Objetivos alcanzados <b>${(p.hits || []).join(", ").toUpperCase() || "ninguno"}</b></span></div>
      ${progBar(p.stop, tgt, p.last_price, "Stop", "Objetivo")}
      ${(p.exit_risk || 0) >= 50 ? `<p class="note neg">Atención: ${esc((p.exit_signals || []).slice(0, 2).join(", ") || "señales de salida")}</p>` : ""}
      <div class="mini-actions"><button class="btn" data-pid="${esc(p.id)}" data-act="close">Cerrar</button><button class="btn" data-pid="${esc(p.id)}" data-act="del">Eliminar</button></div>
    </div>`; }).join("") : `<div class="card empty"><h2>No tienes posiciones abiertas</h2><p>Registra una desde la ficha de cualquier oportunidad o con el botón de arriba. El radar te avisará si toca el stop o un objetivo.</p></div>`;
  $("#posClosed").innerHTML = `<thead><tr><th>Token</th><th>Tipo</th><th>Entrada</th><th>Salida</th><th>Resultado</th><th>Abierta</th><th>Cerrada</th></tr></thead><tbody>` +
    (closed.length ? closed.map(p => `<tr><td class="sym">${esc(p.symbol)}</td><td>${p.paper ? "Simulada" : "Real"}</td><td>${px(p.entry)}</td><td>${px(p.exit_price)}</td><td>${pct(p.pnl_pct)}</td><td>${when(p.opened_at)}</td><td>${when(p.closed_at)}</td></tr>`).join("") : emptyRow(7, "Aún no has cerrado posiciones.")) + "</tbody>";
}
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

/* ---------- Memecoins (sin revelar la regla) ---------- */
const REASON = {TP: "Objetivo", TAKE_PROFIT: "Objetivo", SL: "Stop", STOP: "Stop", STOP_LOSS: "Stop", TIME: "Tiempo", TIMEOUT: "Tiempo", EXPIRED: "Tiempo"};
async function loadMemes(){
  try { MEMES = await api("/api/memes"); } catch (e) { $("#memeList").innerHTML = `<p class="note">No se pudieron cargar las memecoins.</p>`; return; }
  const s = MEMES.stats || {}, st = MEMES.status || {};
  const mini = (l, v) => `<div class="mini"><div class="l">${l}</div><div class="v">${v}</div></div>`;
  $("#memeStats").innerHTML = mini("Señales", s.signals ?? 0) + mini("Abiertas", s.open ?? 0) + mini("Aciertos", s.win_rate != null ? nf0.format(s.win_rate) + "%" : "—") +
    mini("Gana por cada $1 perdido", s.profit_factor != null ? "$" + nf2.format(s.profit_factor) : "—") + mini("Resultado de la cartera", s.closed ? pct(s.portfolio_pct) : "—");
  $("#memeStatus").textContent = (st.checking ? "Revisando… · " : "") + "Última revisión " + ago(st.last_check) + (st.last_error ? " · " + st.last_error : "") + " · Se revisa cada día al cierre (7 p. m. hora Colombia).";
  renderMemes();
}
function renderMemes(){
  if (!MEMES) return;
  $$("#memeSeg button").forEach(b => b.classList.toggle("on", b.dataset.m === MEME_TAB));
  const E = t => `<div class="card empty"><h2>${t[0]}</h2><p>${t[1]}</p></div>`;
  let html = "";
  if (MEME_TAB === "signals") html = (MEMES.signals || []).map(x => `<div class="sig"><div class="head"><span class="sym">${esc(x.symbol)}</span><span class="badge ${x.paper ? "b-buy" : "b-watch"}">${x.paper ? "En práctica" : "Sin cupo"}</span></div>
      <div class="meta"><span>Señal <b>${esc(x.signal_day)}</b></span><span>Entrada <b>${px(x.entry)}</b></span><span>Stop <b class="neg">${px(x.stop)}</b></span><span>Objetivo <b class="pos">${px(x.target)}</b></span></div></div>`).join("")
      || E(["Aún no hay señales", "Son poco frecuentes por diseño: solo aparecen cuando una memecoin cumple todas las condiciones. Te avisamos por Telegram cuando salga una."]);
  if (MEME_TAB === "open") html = (MEMES.open || []).map(t => `<div class="sig"><div class="head"><span class="sym">${esc(t.symbol)}</span>${pct((t.last / t.entry - 1) * 100)}</div>
      <div class="meta"><span>Entrada <b>${px(t.entry)}</b></span><span>Ahora <b>${px(t.last)}</b></span><span>Vence <b>${when(t.expires)}</b></span></div>${progBar(t.stop, t.target, t.last, "Stop", "Objetivo")}</div>`).join("")
      || E(["Sin operaciones abiertas", "Cuando salga una señal, la operación de práctica aparecerá aquí con su avance hacia el objetivo o el stop."]);
  if (MEME_TAB === "closed") html = (MEMES.closed || []).length ? `<div class="tbl"><table><thead><tr><th>Token</th><th>Señal</th><th>Entrada</th><th>Salida</th><th>Cómo terminó</th><th>Resultado</th></tr></thead><tbody>` +
      MEMES.closed.map(t => `<tr><td class="sym">${esc(t.symbol)}</td><td>${esc(t.signal_day)}</td><td>${px(t.entry)}</td><td>${px(t.exit)}</td><td>${esc(REASON[String(t.reason).toUpperCase()] || t.reason)}</td><td>${pct(t.pnl_pct)}</td></tr>`).join("") + "</tbody></table></div>"
      : E(["Aún no hay operaciones cerradas", "El historial muestra todas las operaciones, ganadoras y perdedoras."]);
  $("#memeList").innerHTML = html;
}
$("#memeSeg").onclick = e => { const b = e.target.closest("[data-m]"); if (b) { MEME_TAB = b.dataset.m; renderMemes(); } };
$("#memeCheck").onclick = async ev => {
  const b = ev.currentTarget; b.disabled = true;
  try { const r = await post("/api/memes/check"); toast(r.ok ? "Revisando memecoins…" : (r.msg || "No se pudo revisar")); } catch (e) { toast("No se pudo contactar el servidor"); }
  setTimeout(() => { loadMemes(); b.disabled = false; }, 8000);
};

/* ---------- Historial de señales ---------- */
let JOURNAL = [];
async function loadJournal(){
  let j; try { j = await api("/api/journal"); } catch (e) { $("#jTable").innerHTML = emptyRow(1, "No se pudo cargar el historial."); return; }
  const s = j.stats || {}; JOURNAL = j.items || [];
  const mini = (l, v, sub = "") => `<div class="mini"><div class="l">${l}</div><div class="v">${v}</div>${sub ? `<div class="s">${sub}</div>` : ""}</div>`;
  $("#jStats").innerHTML = mini("Señales publicadas", s.signals ?? 0) + mini("En curso", s.open ?? 0) + mini("Terminadas", s.closed ?? 0) +
    mini("Aciertos", s.win_rate != null ? nf0.format(s.win_rate) + "%" : "—", "de las terminadas") +
    mini("Resultado medio", s.avg_R != null ? `<span class="${s.avg_R >= 0 ? "pos" : "neg"}">${rTxt(s.avg_R)}</span>` : "—", "veces lo arriesgado") +
    mini("Acumulado", `<span class="${(s.total_R || 0) >= 0 ? "pos" : "neg"}">${rTxt(s.total_R || 0)}</span>`, "veces lo arriesgado");
  $("#jTable").innerHTML = `<thead><tr><th>Fecha</th><th>Token</th><th>Puntaje</th><th>Fase</th><th>Mercado</th><th>Entrada</th><th>Stop</th><th>TP1</th><th>TP2</th><th>TP3</th><th>Alcanzado</th><th>Estado</th><th>Resultado</th></tr></thead><tbody>` +
    (JOURNAL.length ? JOURNAL.map(x => `<tr><td>${when(x.at)}</td><td class="sym">${esc(x.symbol)}</td><td>${sc(x.score)}</td><td>${esc(cap(x.phase))}</td><td>${esc(cap(x.regime))}</td>
      <td>${px(x.entry)}</td><td class="neg">${px(x.stop)}</td><td>${px(x.tp1)}</td><td>${px(x.tp2)}</td><td>${px(x.tp3)}</td><td>${(x.hits || []).join(", ").toUpperCase() || "—"}</td>
      <td>${x.status === "OPEN" ? '<span class="badge b-watch">En curso</span>' : '<span class="badge b-wait">Terminada</span>'}</td>
      <td class="${(x.r_multiple || 0) >= 0 ? "pos" : "neg"}" title="Veces lo arriesgado">${x.r_multiple != null ? rTxt(x.r_multiple) : "—"}</td></tr>`).join("")
      : emptyRow(13, "Aún no hay señales registradas. Aparecerán aquí desde el primer escaneo con oportunidades.")) + "</tbody>";
}

/* ---------- Exportar (CSV) ---------- */
$("#exportBtn").onclick = () => {
  const rep = STATE?.report || {}; let rows = [];
  if (VIEW === "radar") rows = [["#", "Token", "Puntaje", "Fase", "Entrada desde", "Entrada hasta", "Stop", "TP1", "TP2", "TP3", "R/B", "Acción"],
    ...(rep.ranking || []).map(r => [r.rank, r.symbol, Math.round(r.score), r.phase, r.plan.entry_ideal, r.plan.entry_zone_high, r.plan.stop, r.plan.tp1, r.plan.tp2, r.plan.tp3, r.plan.rr?.toFixed(2), r.action])];
  else if (VIEW === "assets") rows = [["Token", "Precio", "24h %", "Capitalización", "Puntaje", "Fase", "Acción"], ...(rep.assets || []).map(a => [a.symbol, a.price, a.chg_24h, a.market_cap, Math.round(a.score), a.phase, a.action])];
  else if (VIEW === "journal") rows = [["Fecha", "Token", "Puntaje", "Fase", "Entrada", "Stop", "TP1", "TP2", "TP3", "Estado", "Resultado (veces el riesgo)"], ...JOURNAL.map(x => [x.at, x.symbol, Math.round(x.score), x.phase, x.entry, x.stop, x.tp1, x.tp2, x.tp3, x.status, x.r_multiple ?? ""])];
  if (rows.length < 2) return toast("No hay datos para exportar");
  const csv = rows.map(r => r.map(v => `"${String(v ?? "").replace(/"/g, '""')}"`).join(";")).join("\n");
  const a = Object.assign(document.createElement("a"), {href: URL.createObjectURL(new Blob(["﻿" + csv], {type: "text/csv"})), download: `crypto-radar-${VIEW}-${new Date().toISOString().slice(0, 10)}.csv`});
  document.body.append(a); a.click(); a.remove();
};

/* ---------- Ajustes ---------- */
async function loadSettings(){
  let s; try { s = await api("/api/settings"); } catch (e) { $("#setMsg").textContent = "No se pudieron cargar los ajustes"; return; }
  const f = $("#setForm");
  for (const [k, v] of Object.entries(s)) {
    const el = f.elements[k]; if (!el) continue;
    if (el.type === "checkbox") el.checked = !!v;
    else if (Array.isArray(v)) el.value = v.join(", ");
    else if (v && typeof v === "object") el.value = Object.entries(v).map(([a, b]) => `${a}: ${b}`).join("\n");
    else el.value = v ?? "";
  }
}
$("#setForm").onsubmit = async e => {
  e.preventDefault(); const f = e.target, b = {};
  for (const el of f.elements) { if (!el.name) continue; b[el.name] = el.type === "checkbox" ? el.checked : el.value; }
  const cat = {}; (b.catalysts || "").split("\n").forEach(l => { const i = l.indexOf(":"); if (i > 0) cat[l.slice(0, i).trim().toUpperCase()] = l.slice(i + 1).trim(); }); b.catalysts = cat;
  try { await post("/api/settings", b); $("#setMsg").textContent = "Guardado. Se aplica en el próximo escaneo."; }
  catch (err) { $("#setMsg").textContent = "No se pudo guardar"; }
  setTimeout(() => $("#setMsg").textContent = "", 5000);
};
$("#tgTest").onclick = async ev => {
  const b = ev.currentTarget; if (b.disabled) return; b.disabled = true; $("#setMsg").textContent = "Enviando…";
  try { const r = await post("/api/telegram/test"); $("#setMsg").textContent = r.ok ? "Mensaje enviado a Telegram." : "Telegram: " + r.msg; }
  catch (e) { $("#setMsg").textContent = "No se pudo contactar el servidor"; }
  finally { setTimeout(() => b.disabled = false, 5000); }
};

/* ---------- Inicio ---------- */
paintIcons();
const start = (location.hash || "").slice(1);
show(TITLES[start] ? start : "radar");
refresh(); setInterval(refresh, 15000);
