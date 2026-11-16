// Recorre anchos de 300 a 1500 px y comprueba que el encabezado no desborde.
// Uso: node tests/ventas/prueba_anchos_encabezado.js <ruta absoluta a ventas/index.html>
const {chromium}=require('playwright');(async()=>{const b=await chromium.launch();const p=await b.newPage();
await p.route(/^https?:\/\//,r=>r.request().url().includes('fonts.')?r.continue():r.abort());
await p.goto('file://'+process.argv[2]);await p.waitForTimeout(800);const bad=[];
for(let w=300;w<=1500;w+=10){await p.setViewportSize({width:w,height:800});await p.waitForTimeout(30);
const r=await p.evaluate(()=>{const n=document.querySelector('.nav-in').getBoundingClientRect(),e=document.querySelector('.btn.enter').getBoundingClientRect(),h=document.querySelector('.nav-in').offsetHeight;return {sw:document.documentElement.scrollWidth,iw:innerWidth,in:e.right<=n.right+0.5,h}});
if(r.sw>r.iw||!r.in||r.h>70)bad.push(w+':'+JSON.stringify(r));}
console.log(bad.length?'FALLAS '+bad.join(' '):'OK 300-1500px cada 10px: sin desborde, botón dentro de la barra, barra en una línea');await b.close()})();
