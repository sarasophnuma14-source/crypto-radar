(function(){
  var reduce=window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // Cinta de tokens (duplicada para el bucle)
  var toks=[['BTC',64],['ETH',58],['SOL',78],['LINK',71],['ONDO',69],['RNDR',66],['PEPE',61],['ARB',52],['TAO',47],['SUI',63],['INJ',55],['WIF',49]];
  var html=toks.map(function(t){return '<span><b>'+t[0]+'</b><i class="'+(t[1]>=65?'hi':'')+'">'+t[1]+'/100</i></span>';}).join('');
  document.getElementById('track').innerHTML=html+html;

  // Planes mensual / anual con perilla deslizante
  var bm=document.getElementById('bill-m'), by=document.getElementById('bill-y'), knob=document.getElementById('knob');
  function place(btn){knob.style.width=btn.offsetWidth+'px';knob.style.transform='translateX('+(btn.offsetLeft-4)+'px)';}
  function setBill(y){
    bm.setAttribute('aria-pressed',String(!y)); by.setAttribute('aria-pressed',String(y)); place(y?by:bm);
    document.querySelectorAll('[data-m]').forEach(function(el){el.textContent=el.getAttribute(y?'data-y':'data-m');});
  }
  bm.addEventListener('click',function(){setBill(false)}); by.addEventListener('click',function(){setBill(true)});
  window.addEventListener('resize',function(){place(by.getAttribute('aria-pressed')==='true'?by:bm)});
  place(bm);

  // Luz que sigue al cursor en los planes
  document.querySelectorAll('.plan').forEach(function(p){
    p.addEventListener('pointermove',function(e){var r=p.getBoundingClientRect();p.style.setProperty('--mx',(e.clientX-r.left)+'px');p.style.setProperty('--my',(e.clientY-r.top)+'px');});
  });

  // Preguntas
  document.querySelectorAll('.qa button').forEach(function(b){
    b.addEventListener('click',function(){var q=b.parentNode, o=q.getAttribute('data-open')!=='true'; q.setAttribute('data-open',String(o)); b.setAttribute('aria-expanded',String(o));});
  });

  // Radar
  var cv=document.getElementById('radar'), ctx=cv.getContext('2d');
  var blips=[{t:'SOL',s:78,a:.6},{t:'LINK',s:71,a:1.7},{t:'RNDR',s:66,a:2.6},{t:'ARB',s:52,a:3.5},{t:'PEPE',s:61,a:4.3},{t:'ONDO',s:69,a:5.2},{t:'TAO',s:47,a:5.85}];
  var W=0, ang=-.4, last=0;
  function size(){var d=window.devicePixelRatio||1,w=cv.clientWidth;if(!w)return;cv.width=w*d;cv.height=w*d;ctx.setTransform(d,0,0,d,0,0);W=w;}
  function draw(){
    if(!W)return; var c=W/2,R=W/2-4;
    ctx.clearRect(0,0,W,W); ctx.strokeStyle='rgba(191,211,214,.14)'; ctx.lineWidth=1;
    for(var i=1;i<=4;i++){ctx.beginPath();ctx.arc(c,c,R*i/4,0,Math.PI*2);ctx.stroke();}
    ctx.beginPath();ctx.moveTo(c-R,c);ctx.lineTo(c+R,c);ctx.moveTo(c,c-R);ctx.lineTo(c,c+R);ctx.stroke();
    ctx.fillStyle='rgba(143,166,173,.6)'; ctx.font='500 '+Math.max(10,W/42)+'px Inter, sans-serif';
    ['85','70','55','40'].forEach(function(v,i){ctx.fillText(v,c+5,c-R*(i+1)/4-5);});
    for(var k=0;k<48;k++){var a0=ang-1.2*(k+1)/48,a1=ang-1.2*k/48;ctx.beginPath();ctx.moveTo(c,c);ctx.arc(c,c,R,a0,a1);ctx.closePath();ctx.fillStyle='rgba(240,174,69,'+(.2*(1-k/48))+')';ctx.fill();}
    ctx.strokeStyle='#F0AE45';ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(c,c);ctx.lineTo(c+R*Math.cos(ang),c+R*Math.sin(ang));ctx.stroke();
    blips.forEach(function(b){
      var rr=Math.min((100-b.s)/60*R,R*.92), x=c+rr*Math.cos(b.a), y=c+rr*Math.sin(b.a);
      var d=((ang-b.a)%(Math.PI*2)+Math.PI*2)%(Math.PI*2), g=reduce?.9:Math.max(.3,1-d/(Math.PI*1.4)), hot=b.s>=65;
      ctx.globalAlpha=g; ctx.fillStyle=hot?'#F0AE45':'#BFD3D6';
      if(hot){ctx.shadowColor='#F0AE45';ctx.shadowBlur=14*g;}
      ctx.beginPath();ctx.arc(x,y,hot?Math.max(4,W/80):Math.max(3,W/110),0,Math.PI*2);ctx.fill(); ctx.shadowBlur=0;
      ctx.font='600 '+Math.max(11,W/36)+'px Inter, sans-serif'; var lab=b.t+' '+b.s, lw=ctx.measureText(lab).width;
      ctx.fillText(lab,x>c?x-10-lw:x+10,y+4); ctx.globalAlpha=1;
    });
  }
  size(); draw(); window.addEventListener('resize',function(){size();draw();});
  if(!reduce){(function loop(ts){if(!last)last=ts;var dt=Math.min(64,ts-last);last=ts;ang+=dt*.0011;draw();requestAnimationFrame(loop);})(performance.now());}

  // Animaciones estilo Framer (GSAP + ScrollTrigger + Lenis)
  if(reduce||!window.gsap) return;
  gsap.registerPlugin(ScrollTrigger);
  if(window.Lenis && !matchMedia('(pointer: coarse)').matches){
    var lenis=new Lenis({lerp:.1});
    lenis.on('scroll',ScrollTrigger.update);
    gsap.ticker.add(function(t){lenis.raf(t*1000)}); gsap.ticker.lagSmoothing(0);
    document.querySelectorAll('a[href^="#"]').forEach(function(a){a.addEventListener('click',function(e){var t=document.querySelector(a.getAttribute('href'));if(t){e.preventDefault();lenis.scrollTo(t,{offset:-80});}});});
  }
  // Titular palabra por palabra con desenfoque
  var h1=document.getElementById('h1');
  h1.innerHTML=h1.textContent.split(' ').map(function(w){return '<span class="w">'+w+'</span>';}).join(' ');
  var tl=gsap.timeline({defaults:{ease:'power3.out'}});
  tl.from('.hero .w',{y:40,opacity:0,filter:'blur(12px)',duration:.9,stagger:.07})
    .from('[data-hero]',{y:24,opacity:0,filter:'blur(6px)',duration:.8,stagger:.08},'-=.55');
  // Revelado al hacer scroll (parte visible para que nada quede oculto)
  gsap.utils.toArray('.reveal').forEach(function(el){
    gsap.from(el,{y:36,opacity:.25,filter:'blur(6px)',duration:.9,ease:'power3.out',scrollTrigger:{trigger:el,start:'top 88%',once:true}});
  });
  // Tarjetas apiladas: la de atrás se encoge
  var cards=gsap.utils.toArray('.eng');
  cards.forEach(function(card,i){
    var next=cards[i+1]; if(!next) return;
    gsap.to(card,{scale:.94,opacity:.55,ease:'none',scrollTrigger:{trigger:next,start:'top 85%',end:'top 140px',scrub:true}});
  });
  // Trazos que se dibujan
  gsap.utils.toArray('.draw').forEach(function(p){
    var L=p.getTotalLength(); gsap.set(p,{strokeDasharray:L,strokeDashoffset:L});
    gsap.to(p,{strokeDashoffset:0,duration:1.6,ease:'power2.out',scrollTrigger:{trigger:p,start:'top 85%',once:true}});
  });
  // Teléfono: entra, llena la barra y aparece la segunda alerta
  var ph=gsap.timeline({scrollTrigger:{trigger:'.phone',start:'top 80%',once:true}});
  ph.from('.phone',{y:80,rotate:-4,opacity:.3,duration:1,ease:'power3.out'})
    .from('.m1',{y:20,opacity:0,duration:.6},'-=.4')
    .from('.bar i',{scaleX:0,duration:.8,ease:'power2.out'},'-=.2')
    .from('.m2',{y:20,opacity:0,duration:.5},'+=.4');
})();
