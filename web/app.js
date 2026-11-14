const $ = s => document.querySelector(s);
const api = (p, o) => fetch(p, o).then(r => r.json());
const post = (p, b) => api(p, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(b || {})});
let STATE = null, SORT = {key: "score", dir: -1}, lastAlertSeen = localStorageGet("seenAlert") || "";

function localStorageGet(k){try{return localStorage.getItem(k)}catch(e){return null}}
function localStorageSet(k,v){try{localStorage.setItem(k,v)}catch(e){}}
function px(v){if(v==null||isNaN(v))return "N/D";const a=Math.abs(v);return "$"+(a>=1000?v.toLocaleString("en-US",{maximumFractionDigits:0}):a>=1?v.toLocaleString("en-US",{maximumFractionDigits:3}):Number(v.toPrecision(4)).toString())}
function big(v){if(v==null)return "N/D";const a=Math.abs(v);return a>=1e12?"$"+(v/1e12).toFixed(2)+"T":a>=1e9?"$"+(v/1e9).toFixed(2)+"B":a>=1e6?"$"+(v/1e6).toFixed(1)+"M":"$"+Math.round(v).toLocaleString()}
function pct(v,d=1){if(v==null||isNaN(v))return "N/D";return `<span class="${v>=0?"pos":"neg"}">${v>=0?"+":""}${v.toFixed(d)}%</span>`}
function sc(v){const c=v>=90?"s90":v>=80?"s80":v>=70?"s70":v>=60?"s60":"s0";return `<span class="score ${c}">${Math.round(v)}</span>`}
function act(a){const c=a.startsWith("COMPRAR")?"a-buy":a.startsWith("ESPERAR")?"a-wait":a.startsWith("EVITAR")||a.startsWith("RECHAZAR")?"a-avoid":"a-watch";return `<span class="act ${c}">${a}</span>`}
function ago(iso){if(!iso)return "nunca";const m=Math.round((Date.now()-new Date(iso))/60000);return m<1?"ahora":m<60?`hace ${m} min`:m<1440?`hace ${Math.round(m/60)} h`:`hace ${Math.round(m/1440)} d`}
function when(iso){return iso?new Date(iso).toLocaleString("es-CO",{dateStyle:"short",timeStyle:"short"}):"—"}
function esc(s){return String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]))}

document.querySelectorAll("#tabs button").forEach(b=>b.onclick=()=>show(b.dataset.tab));
function show(t){document.querySelectorAll("#tabs button").forEach(b=>b.classList.toggle("on",b.dataset.tab===t));document.querySelectorAll(".tab").forEach(s=>s.classList.toggle("on",s.id==="tab-"+t));
 ({alerts:loadAlerts,positions:loadPositions,journal:loadJournal,settings:loadSettings})[t]?.();
 if(t==="alerts"){localStorageSet("seenAlert",new Date().toISOString());lastAlertSeen=new Date().toISOString();$("#alertCount").classList.add("hidden")}}

$("#scanBtn").onclick=async()=>{const r=await post("/api/scan");if(!r.ok)alert(r.msg);refresh()};

async function refresh(){
  STATE = await api("/api/state");
  const st=STATE.status, rep=STATE.report||{};
  $("#scanBtn").disabled=st.scanning; $("#scanBtn").textContent=st.scanning?"Escaneando…":"Escanear ahora";
  $("#scanInfo").innerHTML = st.scanning ? esc(st.progress||"Escaneando…") :
    `Último: ${rep.at?ago(rep.at):"nunca"} · Próximo: ${when(STATE.next_scan)}${st.last_error?` · <span class="neg">⚠ ${esc(st.last_error)}</span>`:""}`;
  $("#empty").classList.toggle("hidden",!!rep.at);
  if(rep.at) renderRadar(rep), renderAssets(rep);
  const al=await api("/api/alerts"); const n=al.filter(a=>a.at>lastAlertSeen).length;
  $("#alertCount").textContent=n; $("#alertCount").classList.toggle("hidden",!n||$("#tab-alerts").classList.contains("on"));
}

function renderRadar(rep){
  const m=rep.market, v=rep.verdict;
  $("#verdict").className="verdict "+(v==="OPORTUNIDADES ACTIVAS"?"v-ok":v==="ESPERAR ENTRADA"?"v-wait":"v-cash");
  $("#verdict").innerHTML=`<b>${esc(v)}</b>${esc(rep.verdict_text)} <span class="muted small">· Escaneo ${when(rep.at)} · ${rep.analyzed} activos en ${rep.duration_s}s</span>`;
  const fg=m.fear_greed;
  $("#market").innerHTML=[
    ["Régimen",m.regime,m.alt_bias],["Bitcoin",px(m.btc_price),`RSI ${m.btc_rsi?.toFixed(0)??"N/D"} · 30d ${m.btc_chg_30d!=null?m.btc_chg_30d.toFixed(1)+"%":"N/D"}`],
    ["Dominancia BTC",m.btc_dominance!=null?m.btc_dominance.toFixed(1)+"%":"N/D",`ETH ${m.eth_dominance?.toFixed(1)??"N/D"}%`],
    ["Cap. total",big(m.total_mcap),`24h ${m.mcap_chg_24h!=null?m.mcap_chg_24h.toFixed(1)+"%":"N/D"}`],
    ["Fear & Greed",fg?fg.value:"N/D",fg?({"Extreme Fear":"Miedo extremo","Fear":"Miedo","Neutral":"Neutral","Greed":"Codicia","Extreme Greed":"Codicia extrema"}[fg.label]||fg.label):""],["Amplitud alts",m.breadth.toFixed(0)+"%","sobre su EMA50"],
    ["Exposición máx. alts",m.max_alt_exposure+"%",`score mínimo de compra ${m.min_buy_score}`]
  ].map(([l,v,s])=>`<div class="kpi"><div class="l">${l}</div><div class="v">${v}</div><div class="s">${esc(s)}</div></div>`).join("");
  $("#outlook").textContent=rep.outlook;
  const cols=["#","Token","Precio","Market cap","Score","Fase","Entrada","Stop","TP1","TP2","TP3","Retorno","Riesgo","R:R","Confianza","Acción"];
  $("#rankTable").innerHTML=`<thead><tr>${cols.map(c=>`<th>${c}</th>`).join("")}</tr></thead><tbody>`+
   (rep.ranking.length?rep.ranking.map(r=>{const p=r.plan;return `<tr data-s="${r.symbol}"><td>${r.rank}</td><td class="sym">${r.symbol}<small>${esc(r.name||"")}</small></td>
   <td>${px(r.price)}</td><td>${big(r.market_cap)}</td><td>${sc(r.score)}</td><td>${r.phase}</td><td>${px(p.entry_ideal)}–${px(p.entry_zone_high)}</td>
   <td class="neg">${px(p.stop)}</td><td>${px(p.tp1)}</td><td>${px(p.tp2)}</td><td>${px(p.tp3)}</td><td class="pos">+${p.return_tp2_pct.toFixed(0)}%</td>
   <td class="neg">-${p.risk_pct.toFixed(1)}%</td><td>${p.rr.toFixed(1)}</td><td>${r.confidence}</td><td>${act(r.action)}</td></tr>`}).join("")
   :`<tr><td colspan="16" class="muted">Ningún activo califica. Mantener liquidez.</td></tr>`)+"</tbody>";
  $("#rankTable").querySelectorAll("tr[data-s]").forEach(tr=>tr.onclick=()=>detail(tr.dataset.s));
  const x=rep.extra, A=s=>s?`<a href="#" data-s="${s}" class="sym">${s}</a>`:`<span class="muted">Ninguno califica</span>`;
  $("#extra").innerHTML=[
    ["Top 3",x.top3.length?x.top3.map(A).join(" · "):A(null)],["Mejor entrada temprana",A(x.best_early_entry)],
    ["Mejor riesgo/beneficio",A(x.best_risk_reward)],["Mayor potencial de crecimiento",A(x.highest_growth)],
    ["Operación corto plazo más atractiva",A(x.short_term_trade)],
    ["Activos a evitar",x.avoid.length?x.avoid.map(a=>`<div>${A(a.symbol)} <span class="muted small">${esc(a.why)}</span></div>`).join(""):"—"]
  ].map(([h,b])=>`<div class="card"><h3>${h}</h3><div>${b}</div></div>`).join("");
  $("#extra").querySelectorAll("a[data-s]").forEach(a=>a.onclick=e=>{e.preventDefault();detail(a.dataset.s)});
}

function renderAssets(rep){
  const ph=$("#fPhase"),ct=$("#fCat");
  if(ph.options.length<2){[...new Set(rep.assets.map(a=>a.phase))].sort().forEach(p=>ph.add(new Option(p,p)));
    [...new Set(rep.assets.flatMap(a=>a.categories||[]))].sort().forEach(p=>ct.add(new Option(p,p)));
    [ph,ct,$("#fSearch")].forEach(e=>e.oninput=()=>renderAssets(STATE.report))}
  const q=$("#fSearch").value.trim().toUpperCase();
  let rows=rep.assets.filter(a=>(!q||a.symbol.includes(q))&&(!ph.value||a.phase===ph.value)&&(!ct.value||(a.categories||[]).includes(ct.value)));
  const get={symbol:a=>a.symbol,score:a=>a.score,price:a=>a.price,market_cap:a=>a.market_cap||0,chg_24h:a=>a.chg_24h??-999,chg_30d:a=>a.tech.chg_30d??-999,
    rsi:a=>a.tech.rsi??0,early:a=>a.early_score,mom:a=>a.momentum_score,exit:a=>a.exit_risk,rr:a=>a.plan.rr,phase:a=>a.phase,action:a=>a.action};
  rows.sort((a,b)=>{const x=get[SORT.key](a),y=get[SORT.key](b);return (x>y?1:x<y?-1:0)*SORT.dir});
  const H=[["symbol","Token"],["price","Precio"],["chg_24h","24h"],["chg_30d","30d"],["market_cap","Market cap"],["score","Score"],["phase","Fase"],
    ["rsi","RSI"],["early","Early"],["mom","Momentum"],["exit","Riesgo salida"],["rr","R:R"],["action","Acción"]];
  $("#assetTable").innerHTML=`<thead><tr>${H.map(([k,l])=>`<th data-k="${k}">${l}${SORT.key===k?(SORT.dir>0?" ▲":" ▼"):""}</th>`).join("")}<th>Categorías</th></tr></thead><tbody>`+
   rows.map(a=>`<tr data-s="${a.symbol}"><td class="sym">${a.symbol}${a.in_watchlist?" ⭐":""}</td><td>${px(a.price)}</td><td>${pct(a.chg_24h)}</td><td>${pct(a.tech.chg_30d)}</td>
   <td>${big(a.market_cap)}</td><td>${sc(a.score)}</td><td>${a.phase}</td><td>${a.tech.rsi?.toFixed(0)??"N/D"}</td><td>${a.early_score}</td><td>${a.momentum_score}</td>
   <td class="${a.exit_risk>=50?"neg":""}">${a.exit_risk}</td><td>${a.plan.rr.toFixed(1)}</td><td>${act(a.action)}</td>
   <td>${(a.categories||[]).map(c=>`<span class="tag">${c}</span>`).join("")}</td></tr>`).join("")+"</tbody>";
  $("#assetTable").querySelectorAll("th[data-k]").forEach(th=>th.onclick=()=>{SORT={key:th.dataset.k,dir:SORT.key===th.dataset.k?-SORT.dir:-1};renderAssets(STATE.report)});
  $("#assetTable").querySelectorAll("tr[data-s]").forEach(tr=>tr.onclick=()=>detail(tr.dataset.s));
  $("#skipped").innerHTML=(rep.skipped||[]).map(s=>`${s.symbol}: ${esc(s.reason)}`).join(" · ");
}

const BK={technical_structure:["Estructura técnica",20],volume_and_liquidity:["Volumen y liquidez",15],on_chain_activity:["Actividad on-chain",15],
 fundamentals_and_tokenomics:["Fundamentales y tokenomics",15],market_catalysts:["Catalizadores",15],risk_reward_ratio:["Riesgo/beneficio",10],market_sentiment:["Sentimiento",10]};

async function detail(sym){
  const a=STATE.report.assets.find(x=>x.symbol===sym); if(!a) return;
  const p=a.plan, t=a.tech;
  const lv=(l,v,c="")=>`<div class="lv"><div class="l">${l}</div><div class="v ${c}">${v}</div></div>`;
  const list=(h,arr)=>`<h3>${h}</h3>${arr.length?`<ul class="sig">${arr.map(s=>`<li>${esc(s)}</li>`).join("")}</ul>`:`<p class="muted small">Ninguna</p>`}`;
  $("#modalContent").innerHTML=`<h2>${a.symbol} <span class="muted">${esc(a.name||"")}</span> ${sc(a.score)} ${act(a.action)}</h2>
   <div class="muted">${a.class} · Fase <b>${a.phase}</b> · Confianza ${a.confidence} · Cobertura de datos ${a.coverage}% · ${(a.categories||[]).join(" · ")}</div>
   <canvas id="chart" width="1060" height="340"></canvas>
   <div class="grid plan">${lv("Precio",px(a.price))}${lv("Entrada ideal",px(p.entry_ideal))}${lv("Zona hasta",px(p.entry_zone_high))}${lv("Entrada agresiva",px(p.entry_aggressive))}
   ${lv("Entrada confirmación",px(p.entry_confirmation))}${lv("Stop loss",px(p.stop),"neg")}${lv("TP1",px(p.tp1),"pos")}${lv("TP2",px(p.tp2),"pos")}${lv("TP3",px(p.tp3),"pos")}
   ${lv("R:R (a TP2)",p.rr.toFixed(2))}${lv("Retorno TP2 / TP3",`+${p.return_tp2_pct.toFixed(0)}% / +${p.return_tp3_pct.toFixed(0)}%`)}${lv("Riesgo",`-${p.risk_pct.toFixed(1)}%`,"neg")}
   ${lv("Tamaño sugerido",`${px(p.position_usd)} <span class='muted small'>(riesgo ${px(p.risk_usd)})</span>`)}</div>
   <p class="small"><b>Salida final:</b> ${esc(p.final_exit)}. ${esc(p.plan_note)}</p>
   <div class="grid cards3">
     <div>${list("🟢 Early Entry ("+a.early_score+")",a.signals_early)}${list("🚀 Momentum ("+a.momentum_score+")",a.signals_momentum)}</div>
     <div>${list("🔻 Exit Intelligence ("+a.exit_risk+")",a.signals_exit)}${list("Notas de riesgo",a.notes)}${a.catalyst?`<h3>Catalizador</h3><p>${esc(a.catalyst)}</p>`:""}</div>
     <div><h3>Puntuación por bloque</h3>${Object.entries(BK).map(([k,[l,w]])=>{const v=a.breakdown[k];return `<div class="bk"><span>${l}</span>${v==null?`<span class="nd">N/D · sin datos verificables</span>`:`<div class="bar"><i style="width:${v/w*100}%"></i></div><span>${v}/${w}</span>`}</div>`}).join("")}
     <h3 style="margin-top:12px">Indicadores</h3><div class="small">RSI 1D ${t.rsi?.toFixed(0)??"N/D"} · RSI 4H ${t.h4_rsi?.toFixed(0)??"N/D"} · EMA20 ${px(t.ema20)} · EMA50 ${px(t.ema50)} · EMA200 ${px(t.ema200)} · ATR ${t.atr_pct.toFixed(1)}% · Vol x${t.vol_ratio.toFixed(2)} · OBV ${(t.obv_flow*100).toFixed(0)} · 7d ${pct(t.chg_7d)} · 30d ${pct(t.chg_30d)} · 90d ${pct(t.chg_90d)} · Desde máx. ${pct(t.from_high_pct,0)} · Funding ${a.funding!=null?(a.funding*100).toFixed(4)+"%":"N/D"} · OI 24h ${a.oi_change_24h!=null?a.oi_change_24h.toFixed(0)+"%":"N/D"}</div></div>
   </div>
   <div class="row gap" style="margin-top:12px"><button class="primary" id="addPos">Registrar posición con este plan</button><button id="runBt">Backtest de ${a.symbol}</button></div>
   <h3 style="margin-top:14px">Historial de puntuación</h3><div id="hist" class="small muted">Cargando…</div>`;
  $("#modal").classList.remove("hidden");
  $("#addPos").onclick=()=>{$("#modal").classList.add("hidden");show("positions");const f=$("#posForm");f.symbol.value=a.symbol;f.entry.value=+p.entry_ideal.toPrecision(6);f.stop.value=+p.stop.toPrecision(6);f.tp1.value=+p.tp1.toPrecision(6);f.tp2.value=+p.tp2.toPrecision(6);f.tp3.value=+p.tp3.toPrecision(6)};
  $("#runBt").onclick=()=>{$("#modal").classList.add("hidden");show("backtest");$("#btForm").symbol.value=a.symbol;$("#btForm").requestSubmit()};
  const c=await api("/api/candles?symbol="+sym); if(!c.error) drawChart($("#chart"),c,p);
  else $("#chart").replaceWith(Object.assign(document.createElement("p"),{className:"muted small",textContent:"Gráfico disponible para el top 40 y tus posiciones."}));
  const h=await api("/api/history?symbol="+sym);
  $("#hist").innerHTML=h.length?h.slice(-30).reverse().map(([t,s,ph,pr])=>`${t.replace("T"," ")} · ${Math.round(s)} · ${ph} · ${px(pr)}`).join("<br>"):"Sin historial";
}
$("#modalClose").onclick=()=>$("#modal").classList.add("hidden");
$("#modal").onclick=e=>{if(e.target.id==="modal")$("#modal").classList.add("hidden")};

function emaJS(v,n){const k=2/(n+1);let o=[],p=null;v.forEach((x,i)=>{if(i<n-1){o.push(null);return}if(p===null)p=v.slice(0,n).reduce((a,b)=>a+b)/n;else p=x*k+p*(1-k);o.push(p)});return o}
function drawChart(cv,c,p){
  const dpr=window.devicePixelRatio||1,W=cv.clientWidth,H=cv.clientHeight;cv.width=W*dpr;cv.height=H*dpr;const g=cv.getContext("2d");g.scale(dpr,dpr);
  const N=Math.min(160,c.c.length),off=c.c.length-N,e20=emaJS(c.c,20).slice(off),e50=emaJS(c.c,50).slice(off);
  const hs=c.h.slice(off),ls=c.l.slice(off);let hi=Math.max(...hs,p.tp2),lo=Math.min(...ls,p.stop);const pad=(hi-lo)*.05;hi+=pad;lo-=pad;
  const L=8,R=70,T=10,B=20,w=(W-L-R)/N,y=v=>T+(hi-v)/(hi-lo)*(H-T-B);
  g.font="11px sans-serif";
  const line=(v,col,lab)=>{g.strokeStyle=col;g.setLineDash([4,4]);g.beginPath();g.moveTo(L,y(v));g.lineTo(W-R,y(v));g.stroke();g.setLineDash([]);g.fillStyle=col;g.fillText(lab,W-R+4,y(v)+4)};
  g.fillStyle="#38bdf822";g.fillRect(L,y(p.entry_zone_high),W-L-R,y(p.entry_ideal)-y(p.entry_zone_high));
  for(let i=0;i<N;i++){const j=off+i,up=c.c[j]>=c.o[j];g.strokeStyle=g.fillStyle=up?"#22c55e":"#ef4444";const x=L+i*w+w/2;
    g.beginPath();g.moveTo(x,y(c.h[j]));g.lineTo(x,y(c.l[j]));g.stroke();const yo=y(c.o[j]),yc=y(c.c[j]);g.fillRect(x-w*.35,Math.min(yo,yc),w*.7,Math.max(1,Math.abs(yc-yo)))}
  [[e20,"#f59e0b"],[e50,"#a78bfa"]].forEach(([s,col])=>{g.strokeStyle=col;g.beginPath();let st=false;s.forEach((v,i)=>{if(v==null)return;const x=L+i*w+w/2;st?g.lineTo(x,y(v)):g.moveTo(x,y(v));st=true});g.stroke()});
  line(p.stop,"#ef4444","SL");line(p.entry_ideal,"#38bdf8","Entrada");line(p.tp1,"#22c55e","TP1");line(p.tp2,"#22c55e","TP2");if(p.tp3<=hi)line(p.tp3,"#22c55e","TP3");
  g.fillStyle="#8b98a8";g.fillText("EMA20",L+4,T+12);g.fillStyle="#a78bfa";g.fillText("EMA50",L+50,T+12);
}

async function loadAlerts(){
  const al=await api("/api/alerts");const ic={"NEW EARLY ENTRY":"🟢","BREAKOUT CONFIRMATION":"🚀","ENTRY ZONE REACHED":"🎯","STOP LOSS WARNING":"⚠️","STOP LOSS HIT":"🛑","TAKE PROFIT REACHED":"💰","DISTRIBUTION DETECTED":"🟠","BEARISH REVERSAL":"🔻","MARKET REGIME CHANGE":"🌐","SYSTEM":"ℹ️"};
  $("#alertList").innerHTML=al.length?al.map(a=>`<div class="alert"><div class="ic">${ic[a.kind]||"•"}</div><div><b>${a.symbol}</b> · ${esc(a.label)}<div>${esc(a.message)}</div><div class="t">${when(a.at)}</div></div></div>`).join(""):`<p class="muted">Sin alertas todavía.</p>`;
}

async function loadPositions(){
  const ps=await api("/api/positions");const open=ps.filter(p=>p.status==="OPEN"),closed=ps.filter(p=>p.status!=="OPEN");
  $("#posTable").innerHTML=`<thead><tr><th>Token</th><th>Tipo</th><th>Entrada</th><th>Precio</th><th>P&L</th><th>Stop</th><th>TP1</th><th>TP2</th><th>TP3</th><th>Alcanzado</th><th>Fase</th><th>Señales de salida</th><th></th></tr></thead><tbody>`+
   (open.length?open.map(p=>`<tr><td class="sym">${p.symbol}</td><td>${p.paper?"Simulada":"Real"}</td><td>${px(p.entry)}</td><td>${px(p.last_price)}</td><td>${pct(p.pnl_pct)}</td><td class="neg">${px(p.stop)}</td>
   <td>${px(p.tp1)}</td><td>${px(p.tp2)}</td><td>${px(p.tp3)}</td><td>${(p.hits||[]).join(", ").toUpperCase()||"—"}</td><td>${p.phase||"—"}</td>
   <td class="${(p.exit_risk||0)>=50?"neg":""}">${(p.exit_signals||[]).slice(0,3).join(", ")||"—"}</td>
   <td><button data-c="${p.id}">Cerrar</button> <button data-d="${p.id}">🗑</button></td></tr>`).join(""):`<tr><td colspan="13" class="muted">Sin posiciones abiertas</td></tr>`)+"</tbody>";
  $("#posClosed").innerHTML=`<thead><tr><th>Token</th><th>Tipo</th><th>Entrada</th><th>Salida</th><th>Resultado</th><th>Abierta</th><th>Cerrada</th></tr></thead><tbody>`+
   (closed.map(p=>`<tr><td class="sym">${p.symbol}</td><td>${p.paper?"Simulada":"Real"}</td><td>${px(p.entry)}</td><td>${px(p.exit_price)}</td><td>${pct(p.pnl_pct)}</td><td>${when(p.opened_at)}</td><td>${when(p.closed_at)}</td></tr>`).join("")||`<tr><td colspan="7" class="muted">—</td></tr>`)+"</tbody>";
  document.querySelectorAll("[data-c]").forEach(b=>b.onclick=async()=>{const v=prompt("Precio de salida (vacío = último precio)");if(v===null)return;await post(`/api/positions/${b.dataset.c}/close`,{price:v});loadPositions()});
  document.querySelectorAll("[data-d]").forEach(b=>b.onclick=async()=>{if(confirm("¿Eliminar esta posición?")){await post(`/api/positions/${b.dataset.d}/delete`);loadPositions()}});
}
$("#posForm").onsubmit=async e=>{e.preventDefault();const f=new FormData(e.target),b=Object.fromEntries(f);b.paper=e.target.paper.checked;
  const r=await post("/api/positions",b);if(r.error)alert(r.error);else{e.target.reset();e.target.paper.checked=true;loadPositions()}};

async function loadJournal(){
  const j=await api("/api/journal"),s=j.stats;
  $("#jStats").innerHTML=[["Señales",s.signals],["Cerradas",s.closed],["Abiertas",s.open],["Acierto",s.win_rate!=null?s.win_rate+"%":"—"],["R medio",s.avg_R??"—"],["R total",s.total_R]]
   .map(([l,v])=>`<div class="kpi"><div class="l">${l}</div><div class="v">${v}</div></div>`).join("");
  $("#jTable").innerHTML=`<thead><tr><th>Fecha</th><th>Token</th><th>Score</th><th>Fase</th><th>Régimen</th><th>Entrada</th><th>Stop</th><th>TP1</th><th>TP2</th><th>TP3</th><th>Alcanzado</th><th>Estado</th><th>Resultado (R)</th></tr></thead><tbody>`+
   (j.items.map(x=>`<tr><td>${when(x.at)}</td><td class="sym">${x.symbol}</td><td>${sc(x.score)}</td><td>${x.phase}</td><td>${x.regime}</td><td>${px(x.entry)}</td><td>${px(x.stop)}</td><td>${px(x.tp1)}</td><td>${px(x.tp2)}</td><td>${px(x.tp3)}</td>
   <td>${(x.hits||[]).join(", ").toUpperCase()||"—"}</td><td>${x.status==="OPEN"?"Abierta":"Cerrada"}</td><td class="${(x.r_multiple||0)>=0?"pos":"neg"}">${x.r_multiple??"—"}</td></tr>`).join("")||`<tr><td colspan="13" class="muted">Aún no hay señales registradas.</td></tr>`)+"</tbody>";
}

$("#btForm").onsubmit=async e=>{e.preventDefault();const f=e.target;$("#btOut").innerHTML=`<p class="muted">Calculando… (puede tardar ~20 s)</p>`;
  const r=await api(`/api/backtest?symbol=${encodeURIComponent(f.symbol.value.trim())}&min_score=${f.min_score.value}`);
  if(r.error){$("#btOut").innerHTML=`<p class="neg">${esc(r.error)}</p>`;return}
  $("#btOut").innerHTML=`<div class="grid kpis" style="margin-top:12px">${[["Días simulados",r.days],["Operaciones",r.trades],["Acierto",r.win_rate!=null?r.win_rate+"%":"—"],["R medio",r.avg_R??"—"],["Profit factor",r.profit_factor??"—"],
   ["Retorno (1% riesgo)",pct(r.return_pct_1pct_risk)],["Máx. drawdown",pct(r.max_drawdown_pct)],["Comprar y mantener",pct(r.buy_hold_pct)]].map(([l,v])=>`<div class="kpi"><div class="l">${l}</div><div class="v">${v}</div></div>`).join("")}</div>
   <p class="muted small">${esc(r.note)}</p><div class="tablewrap"><table><thead><tr><th>Fecha</th><th>Fase</th><th>Score</th><th>Entrada</th><th>Stop</th><th>TP1</th><th>TP2</th><th>Alcanzado</th><th>Días</th><th>R</th></tr></thead><tbody>
   ${r.list.slice().reverse().map(t=>`<tr><td>${new Date(t.date).toLocaleDateString("es-CO")}</td><td>${t.phase}</td><td>${sc(t.score)}</td><td>${px(t.entry)}</td><td>${px(t.stop)}</td><td>${px(t.tp1)}</td><td>${px(t.tp2)}</td><td>${t.hits.join(", ").toUpperCase()}</td><td>${t.days}</td><td class="${t.R_real>=0?"pos":"neg"}">${t.R_real}</td></tr>`).join("")}</tbody></table></div>`};

async function loadSettings(){
  const s=await api("/api/settings"),f=$("#setForm");
  for(const [k,v] of Object.entries(s)){const el=f.elements[k];if(!el)continue;
    if(el.type==="checkbox")el.checked=!!v;else if(Array.isArray(v))el.value=v.join(", ");else if(typeof v==="object")el.value=Object.entries(v).map(([a,b])=>`${a}: ${b}`).join("\n");else el.value=v}
}
$("#setForm").onsubmit=async e=>{e.preventDefault();const f=e.target,b={};
  for(const el of f.elements){if(!el.name)continue;b[el.name]=el.type==="checkbox"?el.checked:el.value}
  const cat={};(b.catalysts||"").split("\n").forEach(l=>{const i=l.indexOf(":");if(i>0)cat[l.slice(0,i).trim().toUpperCase()]=l.slice(i+1).trim()});b.catalysts=cat;
  await post("/api/settings",b);$("#setMsg").textContent="Guardado ✓ (se aplica en el próximo escaneo)";setTimeout(()=>$("#setMsg").textContent="",4000)};
$("#tgTest").onclick=async(ev)=>{const b=ev.currentTarget;if(b.disabled)return;b.disabled=true;$("#setMsg").textContent="Enviando…";
  try{const r=await post("/api/telegram/test");$("#setMsg").textContent=r.ok?"Mensaje enviado a Telegram ✓":"Telegram: "+r.msg}
  catch(e){$("#setMsg").textContent="No se pudo contactar el servidor"} finally{setTimeout(()=>b.disabled=false,5000)}};

refresh(); setInterval(refresh, 15000);
