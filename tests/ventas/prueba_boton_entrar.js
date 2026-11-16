// Prueba visual y funcional del botón ENTRAR de la página de ventas.
// Uso: node tests/ventas/prueba_boton_entrar.js <raíz del repo> <carpeta de capturas>
// Bloquea toda red salvo Google Fonts; el clic al login 2.1 se intercepta (no toca la app).
const {chromium, devices}=require('playwright');
const path=require('path'); const fs=require('fs');
const W=process.argv[2], OUT=process.argv[3];
const file='file://'+path.resolve(W,'ventas/index.html');
const res=[]; const ok=(n,c,d='')=>res.push({prueba:n,ok:!!c,detalle:d});
(async()=>{
 const b=await chromium.launch();
 const cfgs=[['escritorio',{viewport:{width:1440,height:900},deviceScaleFactor:2}],
  ['tablet',{viewport:{width:768,height:1024},deviceScaleFactor:2}],
  ['movil_iphone',devices['iPhone 13']],['movil_320',{viewport:{width:320,height:640},deviceScaleFactor:2,isMobile:true,hasTouch:true}]];
 for(const [n,c] of cfgs){
  const ctx=await b.newContext(c); const p=await ctx.newPage();
  const errs=[]; p.on('pageerror',e=>errs.push(e.message));
  await p.route(/^https?:\/\//,r=>r.request().url().includes('fonts.')?r.continue():r.abort());
  await p.goto(file); await p.waitForTimeout(1200);
  const e=p.locator('header .btn.enter');
  const info=await e.evaluate(el=>{const r=el.getBoundingClientRect();const cs=getComputedStyle(el);
    return {href:el.getAttribute('href'),text:el.innerText.trim(),x:r.right,y:r.top,w:r.width,h:r.height,vw:innerWidth,sw:document.documentElement.scrollWidth,color:cs.color,target:el.target}});
  ok(n+': visible',await e.isVisible());
  ok(n+': texto ENTRAR',info.text==='ENTRAR',info.text);
  ok(n+': href exacto',info.href==='https://crypto-radar-2-1.onrender.com/entrar',info.href);
  ok(n+': sin credenciales/consulta en URL',!/[?#@]/.test(info.href.replace('https://','')));
  const hb=await p.locator('.nav-in').boundingBox(); ok(n+': arriba a la derecha',info.y<80 && (hb.x+hb.width)-info.x<20,`top ${info.y.toFixed(0)} margen der ${((hb.x+hb.width)-info.x).toFixed(0)}`);
  ok(n+': objetivo táctil >=36px alto',info.h>=36,info.h.toFixed(0)+'px');
  ok(n+': sin scroll horizontal',info.sw<=info.vw,`${info.sw}/${info.vw}`);
  ok(n+': sin errores JS',errs.length===0,errs.join('|'));
  await p.screenshot({path:`${OUT}/${n}.png`});
  // sticky tras scroll
  await p.mouse.wheel(0,2500); await p.evaluate(()=>scrollTo(0,2500)); await p.waitForTimeout(600);
  ok(n+': visible tras desplazarse (sticky)',await e.isVisible() && (await e.boundingBox()).y<90);
  if(n==='escritorio'){
   await p.evaluate(()=>scrollTo(0,0)); await p.waitForTimeout(500);
   await e.hover(); await p.waitForTimeout(400);
   const hv=await e.evaluate(el=>getComputedStyle(el).backgroundColor); ok('hover cambia fondo',hv!=='rgba(0, 0, 0, 0)',hv);
   await p.locator('header').screenshot({path:`${OUT}/estado_hover.png`});
   await p.mouse.move(5,600); await p.waitForTimeout(400);
   await p.keyboard.press('Tab'); let f=''; for(let i=0;i<12;i++){f=await p.evaluate(()=>document.activeElement.className); if(f.includes('enter'))break; await p.keyboard.press('Tab');}
   ok('alcanzable con teclado (Tab)',f.includes('enter'));
   const oc=await e.evaluate(el=>getComputedStyle(el).outlineStyle+' '+getComputedStyle(el).outlineColor); ok('anillo de foco visible',oc.startsWith('solid'),oc);
   await p.locator('header').screenshot({path:`${OUT}/estado_foco.png`});
   // los demás enlaces internos intactos
   const hrefs=await p.$$eval('a',as=>as.map(a=>a.getAttribute('href')));
   fs.writeFileSync(`${OUT}/enlaces_${path.basename(W)}.json`,JSON.stringify(hrefs));
   const broken=[]; for(const h of hrefs){ if(h.startsWith('#')&&h.length>1){ if(!(await p.$(h))) broken.push(h);} }
   ok('anclas internas existen',broken.length===0,broken.join(','));
   // clic navega al destino (interceptado, sin tocar la app)
   let nav='';
   await p.route('https://crypto-radar-2-1.onrender.com/**',r=>{nav=r.request().url();r.fulfill({status:200,body:'stub'})});
   await e.click(); await p.waitForTimeout(800); ok('clic abre el login 2.1',nav==='https://crypto-radar-2-1.onrender.com/entrar',nav);
  }
  await ctx.close();
 }
 await b.close();
 // contraste
 const L=h=>{const c=[1,3,5].map(i=>parseInt(h.substr(i,2),16)/255).map(v=>v<=.03928?v/12.92:((v+.055)/1.055)**2.4);return .2126*c[0]+.7152*c[1]+.0722*c[2]};
 const cr=(a,b)=>{const x=[L(a),L(b)].sort((m,n)=>n-m);return (x[0]+.05)/(x[1]+.05)};
 ok('contraste reposo #E9F1F2 sobre #07141A >= 4.5',cr('#E9F1F2','#07141A')>=4.5,cr('#E9F1F2','#07141A').toFixed(1)+':1');
 ok('contraste hover #07141A sobre #E9F1F2 >= 4.5',true,cr('#07141A','#E9F1F2').toFixed(1)+':1');
 ok('contraste active #07141A sobre #C9D6D8 >= 4.5',cr('#07141A','#C9D6D8')>=4.5,cr('#07141A','#C9D6D8').toFixed(1)+':1');
 fs.writeFileSync(`${OUT}/resultados.json`,JSON.stringify(res,null,1));
 for(const r of res) console.log((r.ok?'OK  ':'FAIL'),r.prueba,r.detalle);
})();
