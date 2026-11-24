

function norm(s){return String(s).normalize('NFD').replace(/[̀-ͯ]/g,'').toLowerCase()}
var STOP={rua:1,avenida:1,av:1,bairro:1,loteamento:1,de:1,da:1,do:1,dos:1,das:1,e:1,o:1,a:1};
function tokens(q){return norm(q).split(/[^a-z0-9]+/).filter(function(t){return t&&!STOP[t]})}
function buscar(D,q){var t=tokens(q);if(!t.length)return null;
  return D.filter(function(d){var h=d._h||(d._h=norm(d.texto+' '+d.lugares.join(' ')));
    return t.every(function(x){return h.indexOf(x)>-1})})}

(function(){
  var D=[];try{D=JSON.parse(document.getElementById('dados').textContent)}catch(e){}
  var q=document.getElementById('busca'),out=document.getElementById('resultado');
  if(!q||!out)return;
  function el(tag,cls,txt){var n=document.createElement(tag);if(cls)n.className=cls;if(txt!=null)n.textContent=txt;return n}
  function render(){
    var r=buscar(D,q.value);out.textContent='';
    if(r===null){if(q.value.trim())out.appendChild(el('p','vazio','Digite o nome da rua ou do bairro, por exemplo "Romão Gomes". Palavras como "rua" e "avenida" sozinhas não bastam.'));return}
    if(!r.length){out.appendChild(el('p','vazio','Nenhum pedido encontrado nas 5 sessões lidas. Isso não quer dizer que nunca pediram: só lemos 5 sessões.'));return}
    out.appendChild(el('p','cnt2',r.length+(r.length===1?' proposta encontrada':' propostas encontradas')));
    r.forEach(function(d){
      var b=el('div','res');
      var h=el('b',null,d.tipo);b.appendChild(h);
      b.appendChild(el('span','meta',d.data+' · '+d.grupo));
      b.appendChild(el('span','tx',d.texto));
      b.appendChild(el('span','meta','Pedido por: '+d.autores.join(', ')));
      var s=el('span','meta');var a=el('a',null,'Ler na Câmara');a.href=d.url;s.appendChild(a);b.appendChild(s);
      out.appendChild(b)});
  }
  q.addEventListener('input',render);
  var chips=document.querySelectorAll('.chip');
  Array.prototype.forEach.call(chips,function(c){c.addEventListener('click',function(){q.value=c.getAttribute('data-q');render();q.focus()})});
})();

(function(){
  var f=document.getElementById('filtro'),l=document.getElementById('lista');
  if(!f||!l)return;
  f.addEventListener('input',function(){
    var t=norm(f.value).trim();
    Array.prototype.forEach.call(l.querySelectorAll('details.v'),function(d){
      d.hidden=!!t&&(d.getAttribute('data-nome')||'').indexOf(t)<0});
  });
})();
