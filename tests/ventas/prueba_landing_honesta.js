// Prueba de contenido, precios, accesibilidad y responsive de la landing del piloto.
// Uso: node tests/ventas/prueba_landing_honesta.js <raíz del repo> <carpeta de capturas>
// Bloquea toda red salvo Google Fonts. Sale con código 1 si alguna comprobación falla.
const {chromium, devices}=require('playwright');
const path=require('path'); const fs=require('fs');
const W=process.argv[2], OUT=process.argv[3]||'/tmp';
const file='file://'+path.resolve(W,'ventas/index.html');
const html=fs.readFileSync(path.resolve(W,'ventas/index.html'),'utf8');
const text=html.replace(/<style[\s\S]*?<\/style>/g,'').replace(/<script[\s\S]*?<\/script>/g,'').replace(/<[^>]+>/g,' ').replace(/\s+/g,' ');
const res=[]; const ok=(n,c,d='')=>res.push({prueba:n,ok:!!c,detalle:String(d)});

// 1. Contenido prohibido mientras el piloto siga cerrado y sin edge demostrado
const prohibido=[[/cupos?/i,'cupos'],[/fundador/i,'fundador'],[/d[ií]as de prueba|prueba gratis|sin tarjeta/i,'prueba gratuita'],
 [/(?<!no )aceptamos tarjetas|paga desde cualquier pa[ií]s|tarjeta de cualquier pa[ií]s/i,'medio de pago activo'],
 [/\+\s?\d+[.,]\d+\s?%/,'retorno positivo destacado'],[/garantizamos|ganancias aseguradas|sin riesgo/i,'promesa'],
 [/backtest de cualquier token/i,'función inexistente'],[/soporte por chat/i,'función inexistente'],[/historial p[uú]blico/i,'función inexistente'],
 [/68[.,]200/,'precio fijo de BTC'],[/<form|<input/i,'formulario que recoge datos']];
for(const [re,n] of prohibido) ok('no contiene: '+n,!re.test(n.startsWith('formulario')?html:text),(text.match(re)||html.match(re)||[''])[0]);
// 2. Contenido obligatorio
const obligatorio=['ANTICÍPATE AL MERCADO. ANALIZA CON INTELIGENCIA.',
 'Una plataforma de monitoreo y análisis de criptomonedas que integra automatización, datos de mercado y herramientas cuantitativas para ayudarte a interpretar oportunidades potenciales.',
 'Los modelos de análisis se encuentran en evaluación. Hasta la fecha no se ha demostrado una ventaja estadística consistente fuera de muestra. La información proporcionada tiene fines informativos y no garantiza resultados financieros.',
 'Propuesta pendiente de aprobación','Los pagos están desactivados','Early Entry','Explosive Momentum','Exit Intelligence','Escáner de mercado','Seguimiento de activos','Herramientas analíticas'];
for(const s of obligatorio) ok('contiene: '+s.slice(0,48),text.includes(s));

(async()=>{
 const b=await chromium.launch();
 const cfgs=[['escritorio',{viewport:{width:1440,height:900},deviceScaleFactor:2}],['tablet',{viewport:{width:768,height:1024},deviceScaleFactor:2}],
  ['movil_iphone',devices['iPhone 13']],['movil_android',devices['Pixel 7']],['movil_320',{viewport:{width:320,height:640},deviceScaleFactor:2,isMobile:true,hasTouch:true}]];
 for(const [n,c] of cfgs){
  const ctx=await b.newContext(c); const p=await ctx.newPage(); const errs=[]; p.on('pageerror',e=>errs.push(e.message));
  const salientes=[]; await p.route(/^https?:\/\//,r=>{const u=r.request().url(); if(u.includes('fonts.'))return r.continue(); salientes.push(u); r.abort();});
  await p.goto(file); await p.waitForTimeout(900);
  const m=await p.evaluate(()=>({sw:document.documentElement.scrollWidth,iw:innerWidth}));
  ok(n+': sin scroll horizontal',m.sw<=m.iw,`${m.sw}/${m.iw}`);
  ok(n+': sin errores JS',errs.length===0,errs.join('|'));
  ok(n+': sin peticiones a terceros (solo fuentes)',salientes.length===0,salientes.join(','));
  const small=await p.$$eval('a.btn,button',els=>els.filter(e=>e.offsetParent).map(e=>[e.innerText.trim().slice(0,20),e.getBoundingClientRect().height]).filter(x=>x[1]<36));
  ok(n+': objetivos táctiles >= 36px',small.length===0,JSON.stringify(small));
  await p.screenshot({path:`${OUT}/${n}_hero.png`});
  await p.evaluate(()=>document.querySelectorAll('.reveal').forEach(e=>e.classList.add('in')));
  await p.locator('#planes').screenshot({path:`${OUT}/${n}_planes.png`});
  if(n==='escritorio'){
   await p.screenshot({path:`${OUT}/escritorio_completa.png`,fullPage:true});
   // precios mensuales y anuales
   const leer=()=>p.$$eval('.plan',ps=>ps.map(x=>x.querySelector('[data-amt]').textContent+' | '+x.querySelector('[data-sub]').textContent));
   const mes=await leer(); ok('mensual Pro US$15 / ref 19',mes[0].startsWith('US$15 |')&&mes[0].includes('US$19'),mes[0]); ok('mensual Élite US$29 / ref 39',mes[1].startsWith('US$29 |')&&mes[1].includes('US$39'),mes[1]);
   await p.click('.billing button[data-period="year"]'); await p.waitForTimeout(150);
   const an=await leer();
   ok('anual Pro 149, 12,42/mes, ahorro 31 (17 %)',an[0].startsWith('US$149 |')&&an[0].includes('US$12,42')&&an[0].includes('US$31')&&an[0].includes('17 %'),an[0]);
   ok('anual Élite 299, 24,92/mes, ahorro 49 (14 %)',an[1].startsWith('US$299 |')&&an[1].includes('US$24,92')&&an[1].includes('US$49')&&an[1].includes('14 %'),an[1]);
   ok('selector anuncia estado (aria-pressed)',await p.getAttribute('.billing button[data-period="year"]','aria-pressed')==='true');
   await p.locator('#planes').screenshot({path:`${OUT}/escritorio_planes_anual.png`});
   await p.click('.billing button[data-period="month"]');
   // todos los CTA de compra/interés van al acceso 2.1, ninguno a un checkout
   const hrefs=await p.$$eval('a',as=>as.map(a=>a.getAttribute('href')));
   const ext=hrefs.filter(h=>!h.startsWith('#'));
   ok('enlaces externos solo a la 2.1 (entrar, privacidad, aviso)',ext.every(h=>/^https:\/\/crypto-radar-2-1\.onrender\.com\/(entrar(#solicitar)?|privacidad|aviso-de-riesgo)$/.test(h)),ext.join(' '));
   ok('ENTRAR exacto',hrefs.includes('https://crypto-radar-2-1.onrender.com/entrar'));
   const broken=[]; for(const h of hrefs){if(h.startsWith('#')&&h.length>1&&!(await p.$(h)))broken.push(h)} ok('anclas internas existen',broken.length===0,broken.join(','));
   // accesibilidad básica
   ok('un solo h1',(await p.$$('h1')).length===1);
   ok('html lang=es',await p.getAttribute('html','lang')==='es');
   ok('enlace para saltar al contenido',!!(await p.$('a.skip[href="#contenido"]')));
   await p.reload(); await p.waitForTimeout(300); await p.keyboard.press('Tab'); ok('primer Tab enfoca "Saltar al contenido"',(await p.evaluate(()=>document.activeElement.className))==='skip');
   const faq=p.locator('details').first(); await faq.locator('summary').focus(); await p.keyboard.press('Enter'); ok('preguntas abren con teclado',await faq.evaluate(d=>d.open));
  }
  await ctx.close();
 }
 // movimiento reducido: sin animaciones del radar
 const ctx=await b.newContext({reducedMotion:'reduce'}); const p=await ctx.newPage(); await p.route(/^https?:\/\//,r=>r.request().url().includes('fonts.')?r.continue():r.abort());
 await p.goto(file); const an=await p.$eval('.sweep',e=>getComputedStyle(e).animationName); ok('prefers-reduced-motion detiene el barrido',an==='none',an); await ctx.close();
 await b.close();
 // contraste WCAG AA
 const L=h=>{const c=[1,3,5].map(i=>parseInt(h.substr(i,2),16)/255).map(v=>v<=.03928?v/12.92:((v+.055)/1.055)**2.4);return .2126*c[0]+.7152*c[1]+.0722*c[2]};
 const cr=(a,b2)=>{const x=[L(a),L(b2)].sort((m,n)=>n-m);return (x[0]+.05)/(x[1]+.05)};
 for(const [f,g,n] of [['#E6F0EC','#060D10','texto'],['#8FA6A0','#060D10','texto secundario'],['#8FA6A0','#0E1D23','secundario en tarjeta'],['#6C827C','#060D10','texto tenue'],['#03140D','#34D399','botón principal'],['#F2B35B','#060D10','aviso'],['#34D399','#060D10','acento']])
  ok(`contraste ${n} ${f}/${g} >= 4.5`,cr(f,g)>=4.5,cr(f,g).toFixed(2)+':1');
 fs.writeFileSync(`${OUT}/resultados_landing.json`,JSON.stringify(res,null,1));
 let fail=0; for(const r of res){console.log((r.ok?'OK  ':'FAIL'),r.prueba,r.detalle); if(!r.ok)fail++}
 console.log(`\n${res.length-fail}/${res.length} comprobaciones OK`); process.exit(fail?1:0);
})();
