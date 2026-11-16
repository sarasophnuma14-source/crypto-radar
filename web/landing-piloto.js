// Script de web/landing.html (copia de ventas/index.html, PR #11). Externo porque la CSP de la 2.1 no admite scripts en línea.
(function(){
  document.body.classList.remove("no-js");
  // Selector mensual / anual: solo cambia lo que se muestra; no hay checkout.
  var fmt=function(n){return "US$"+String(n).replace(".",",")};
  var plans=[].slice.call(document.querySelectorAll(".plan[data-month]"));
  function show(period){
    [].forEach.call(document.querySelectorAll(".billing button"),function(b){b.setAttribute("aria-pressed",String(b.dataset.period===period))});
    plans.forEach(function(p){
      var m=+p.dataset.month,y=+p.dataset.year;
      var amt=p.querySelector("[data-amt]"),per=p.querySelector("[data-per]"),sub=p.querySelector("[data-sub]");
      if(period==="year"){
        var eq=(Math.round(y/12*100)/100).toFixed(2),pct=((1-y/(m*12))*100).toFixed(1).replace(".",",");
        amt.textContent=fmt(y); per.textContent="al año";
        sub.innerHTML="Equivale a <b>"+fmt(eq)+" al mes</b>, un "+pct+" % menos que 12 pagos de "+fmt(m)+". Propuesta: no se puede contratar.";
      }else{
        amt.textContent=fmt(m); per.textContent="al mes";
        sub.textContent="Propuesta pendiente de aprobación. No se puede contratar.";
      }
    });
  }
  [].forEach.call(document.querySelectorAll(".billing button"),function(b){b.addEventListener("click",function(){show(b.dataset.period)})});
  // Aparición al desplazarse
  var els=document.querySelectorAll(".reveal");
  if(!("IntersectionObserver" in window)){[].forEach.call(els,function(e){e.classList.add("in")});return}
  var io=new IntersectionObserver(function(es){es.forEach(function(e){if(e.isIntersecting){e.target.classList.add("in");io.unobserve(e.target)}})},{rootMargin:"0px 0px -8% 0px"});
  [].forEach.call(els,function(e){io.observe(e)});
})();
