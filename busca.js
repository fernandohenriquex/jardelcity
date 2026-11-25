function norm(s){return String(s).normalize('NFD').replace(/[̀-ͯ]/g,'').toLowerCase()}
var STOP={rua:1,avenida:1,av:1,bairro:1,loteamento:1,de:1,da:1,do:1,dos:1,das:1,e:1,o:1,a:1};
function tokens(q){return norm(q).split(/[^a-z0-9]+/).filter(function(t){return t&&!STOP[t]})}
function buscar(D,q){var t=tokens(q);if(!t.length)return null;
  return D.filter(function(d){var h=d._h||(d._h=norm(d.texto+' '+d.lugares.join(' ')));
    return t.every(function(x){return h.indexOf(x)>-1})})}
function fmt(n){return Number(n).toLocaleString('pt-BR')}
function el(tag,cls,txt){var n=document.createElement(tag);if(cls)n.className=cls;if(txt!=null)n.textContent=txt;return n}
function topo(itens,chave,n){var c={};itens.forEach(function(d){chave(d).forEach(function(k){c[k]=(c[k]||0)+1})});
  return Object.keys(c).map(function(k){return[k,c[k]]}).sort(function(a,b){return b[1]-a[1]||(a[0]<b[0]?-1:1)}).slice(0,n)}
var ICO='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 21s7-6.2 7-11.5A7 7 0 0 0 5 9.5C5 14.8 12 21 12 21z" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="12" cy="9.5" r="2.5" fill="currentColor"/></svg>';
function icone(){var s=el('span','ic');s.innerHTML=ICO;return s}

(function(){
  var raw={itens:[],partidos:{}};try{raw=JSON.parse(document.getElementById('dados').textContent)}catch(e){}
  var D=raw.itens,PT=raw.partidos;

  // lista de propostas com "mostrar mais"
  function lista(container,itens,passo){
    var vistos=0,ul=el('div','pl');container.appendChild(ul);
    var mais=el('button','botao');mais.type='button';container.appendChild(mais);
    function card(d){
      var c=el('article','pc');c.appendChild(icone());
      var b=el('div','pc-b');b.appendChild(el('p','pc-t',d.texto));
      var m=el('p','pc-m');m.appendChild(el('span','tag',d.ass&&d.ass[0]?d.ass[0]:d.gn));
      m.appendChild(el('span','meta',d.data+' · '+d.tipo));b.appendChild(m);
      var f=el('p','pc-f');f.appendChild(el('span','meta','Pedido por: '+d.autores.join(', ')));
      var a=el('a',null,'Abrir na Câmara ↗');a.href=d.url;f.appendChild(a);
      b.appendChild(f);c.appendChild(b);return c}
    function mostrar(){
      itens.slice(vistos,vistos+passo).forEach(function(d){ul.appendChild(card(d))});
      vistos=Math.min(itens.length,vistos+passo);
      mais.hidden=vistos>=itens.length;
      mais.textContent='Mostrar mais '+Math.min(passo,itens.length-vistos)+' de '+fmt(itens.length-vistos)}
    mais.addEventListener('click',mostrar);mostrar()}

  // painel da busca
  var q=document.getElementById('busca'),out=document.getElementById('painel');
  function coluna(titulo,linhas){var c=el('div','col');c.appendChild(el('h3',null,titulo));linhas.forEach(function(x){c.appendChild(x)});return c}
  function painel(){
    var txt=q.value.trim(),r=txt?buscar(D,txt):D;out.textContent='';
    if(r===null){out.appendChild(el('p','vazio','Digite o nome da rua ou do bairro, por exemplo um dos lugares acima. Palavras como "rua" e "avenida" sozinhas não bastam.'));return}
    if(!r.length){out.appendChild(el('p','vazio','Nenhum pedido encontrado no período lido. Isso não quer dizer que nunca pediram: o site só lê propostas de vereadores desde a data inicial.'));return}
    var t1=el('div','p-topo');t1.appendChild(el('p','p-n',fmt(r.length)));
    var t=el('p','p-t');
    if(txt){t.appendChild(document.createTextNode(r.length===1?'proposta para ':'propostas para '));t.appendChild(el('b',null,txt))}
    else{t.appendChild(document.createTextNode('propostas para '));t.appendChild(el('b',null,'a cidade inteira'));t.appendChild(document.createTextNode(' até agora'))}
    t1.appendChild(t);out.appendChild(t1);
    var cols=el('div','cols');
    var autores=topo(r,function(d){return d.autores},5),max=autores.length?autores[0][1]:1;
    cols.appendChild(coluna('Quem mais propôs',autores.map(function(a){
      var l=el('div','rk'),h=el('p','rk-n');h.appendChild(el('span',null,a[0]));
      if(PT[a[0]])h.appendChild(el('small',null,' · '+PT[a[0]]));h.appendChild(el('b',null,fmt(a[1])));l.appendChild(h);
      var b=el('span','rk-b'),i=el('i');i.style.width=Math.round(100*a[1]/max)+'%';b.appendChild(i);l.appendChild(b);return l})));
    var ass=topo(r,function(d){return d.ass||[]},5);
    cols.appendChild(coluna('O que mais pedem',ass.length?ass.map(function(a){
      var l=el('p','li-r');l.appendChild(icone());l.appendChild(el('span','li-n',a[0]));l.appendChild(el('b',null,fmt(a[1])));return l}):[el('p','small','Sem pedidos desse tipo.')]));
    var lug=topo(r,function(d){return d.lugares},5);
    cols.appendChild(coluna('Lugares mais citados',lug.length?lug.map(function(a){
      var l=el('p','li-r');l.appendChild(icone());
      var b=el('button','lk',a[0]);b.type='button';b.addEventListener('click',function(){q.value=a[0];painel();q.focus()});
      l.appendChild(b);l.appendChild(el('b',null,fmt(a[1])));return l}):[el('p','small','Nenhum lugar achado.')]));
    out.appendChild(cols);
    out.appendChild(el('h3','rec',txt?'As propostas mais recentes para esse lugar':'As propostas mais recentes da cidade'));
    lista(out,r,4)}
  if(q&&out){q.addEventListener('input',painel);painel();
    Array.prototype.forEach.call(document.querySelectorAll('.chip'),function(c){c.addEventListener('click',function(){q.value=c.getAttribute('data-q');painel();q.focus()})})}

  // ver todas de um grupo
  var lg=document.getElementById('lista-grupo');
  Array.prototype.forEach.call(document.querySelectorAll('.ver-todas'),function(b){
    b.addEventListener('click',function(){
      var g=b.getAttribute('data-g'),itens=D.filter(function(d){return d.g===g});
      lg.hidden=false;lg.textContent='';
      lg.appendChild(el('h3','rec',b.parentNode.querySelector('h3').firstChild.textContent.trim()+': '+fmt(itens.length)+' propostas, da mais recente para a mais antiga'));
      lista(lg,itens,10);lg.scrollIntoView({behavior:'smooth',block:'start'})})});

  // repetidos: mostrar mais ruas
  var rm=document.getElementById('rep-mais');
  if(rm){rm.addEventListener('click',function(){
    var passo=+rm.getAttribute('data-passo'),ocultos=document.querySelectorAll('.rc.extra[hidden]');
    Array.prototype.slice.call(ocultos,0,passo).forEach(function(c){c.hidden=false});
    var resta=document.querySelectorAll('.rc.extra[hidden]').length;
    if(resta)rm.textContent='Mostrar mais ruas ('+resta+' na fila)';else rm.hidden=true})}
})();

// vereadores: filtrar, ordenar, abrir ficha
(function(){
  var f=document.getElementById('filtro'),l=document.getElementById('lista'),p=document.getElementById('partido'),
      o=document.getElementById('ordem'),m=document.getElementById('mostrando');
  if(!f||!l)return;
  var fichas=Array.prototype.slice.call(l.querySelectorAll('.v'));
  function aplicar(){
    var t=norm(f.value).trim(),pt=p?p.value:'',campo=o?o.value:'nome',n=0;
    fichas.sort(function(a,b){
      if(campo==='nome')return a.getAttribute('data-nome')<b.getAttribute('data-nome')?-1:1;
      var d=(+b.getAttribute('data-'+campo))-(+a.getAttribute('data-'+campo));
      return d||(a.getAttribute('data-nome')<b.getAttribute('data-nome')?-1:1)});
    fichas.forEach(function(d){
      var ok=(!t||(d.getAttribute('data-nome')||'').indexOf(t)>-1)&&(!pt||d.getAttribute('data-partido')===pt);
      d.hidden=!ok;if(ok)n++;l.appendChild(d)});
    if(m)m.textContent='Mostrando '+(n===fichas.length?'os '+n:n+' de '+fichas.length)+' vereadores.';
  }
  [f,p,o].forEach(function(x){if(x)x.addEventListener(x===f?'input':'change',aplicar)});
  aplicar();
  Array.prototype.forEach.call(document.querySelectorAll('a.abrir'),function(a){
    a.addEventListener('click',function(){
      var c=document.querySelector(a.getAttribute('href'));if(!c)return;
      c.hidden=false;var d=c.querySelector('details.mais');if(d)d.open=true})});
})();

// "dados conferidos há X"
(function(){
  var s=document.getElementById('conf');if(!s)return;
  var t=Date.parse(s.getAttribute('data-t'));if(isNaN(t))return;
  var min=Math.max(0,Math.round((Date.now()-t)/60000)),txt;
  if(min<60)txt=min+(min===1?' minuto':' minutos');
  else if(min<48*60){var h=Math.round(min/60);txt=h+(h===1?' hora':' horas')}
  else txt=Math.round(min/1440)+' dias';
  s.textContent='Dados conferidos na Câmara há '+txt;
})();
