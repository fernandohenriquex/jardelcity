#!/usr/bin/env python3
"""Gera o site (saida/index.html) a partir dos arquivos da pasta dados/.

Uso:  python3 gerar.py [pasta_dados] [pasta_saida]
"""
import collections
import datetime
import html
import json
import re
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from regras import (GRUPOS, NOME_GRUPO, classificar, extrair_lugares, norm,  # noqa: E402
                    repeticoes, so_pedido)

AQUI = pathlib.Path(__file__).resolve().parent
PASTA_DADOS = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else AQUI / "dados"
PASTA_SAIDA = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else AQUI / "saida"
CFG = json.loads((AQUI / "config.json").read_text(encoding="utf-8"))
SAPL = CFG["sapl_url"].rstrip("/")
CIDADE = CFG["cidade"]
e = html.escape


def ler(nome):
    arq = PASTA_DADOS / nome
    if not arq.exists():
        print(f"aviso: {arq} não existe; seguindo sem esses dados")
        return []
    return json.loads(arq.read_text(encoding="utf-8"))


def br(iso):
    a, m, d = iso.split("-")
    return f"{d}/{m}/{a}"


def link(url, texto):
    return f'<a href="{e(url)}">{texto}</a>'


resumo = lambda i: f"{SAPL}/sessao/{i}/resumo"
materia_url = lambda i: f"{SAPL}/materia/{i}"
URL_PRESENCA = f"{SAPL}/sistema/relatorios/presenca"
URL_SESSOES = f"{SAPL}/sessao/pesquisar-sessao"

# ------------------------------------------------------------------ dados
PARL = {p["id"]: p for p in ler("parlamentares.json")}
desde = CFG.get("desde", "0000-00-00")
SESSOES = sorted((s for s in ler("sessoes.json") if s["data"] >= desde), key=lambda s: s["data"], reverse=True)
SESS = {s["id"]: s for s in SESSOES}
PRES = collections.defaultdict(set)  # sessão -> {parlamentares presentes}
for r in ler("presencas.json"):
    if r["sessao"] in SESS:
        PRES[r["sessao"]].add(r["parlamentar"])
SESSOES_COM_PRESENCA = [s for s in SESSOES if PRES.get(s["id"])]
VOTACOES = [v for v in ler("votacoes.json") if v["sessao"] in SESS and v.get("votos")]
for _v in VOTACOES:  # chaves de objeto JSON são texto; os ids dos vereadores são números
    _v["votos"] = {(int(k) if str(k).isdigit() else k): x for k, x in _v["votos"].items()}
PRES_LISTA = {s: set(v) for s, v in PRES.items()}  # só o que as listas de presença da Câmara registram
for _v in VOTACOES:  # quem votou na sessão estava na sessão
    for _k in _v["votos"]:
        PRES[_v["sessao"]].add(_k)
MATERIAS = ler("materias.json")

# quem aparece no site: tem presença no período ou está ativo
presentes_alguma_vez = set().union(*PRES.values()) if PRES else set()
VER = sorted((p for p in PARL.values() if p["id"] in presentes_alguma_vez or p.get("ativo")),
             key=lambda p: norm(p["nome"]))
NOME = {p["id"]: p["nome"] for p in PARL.values()}

# ------------------------------------------------------------- propostas
PROPS = []  # só as que têm vereador como autor
for m in MATERIAS:
    if m.get("data", "") < desde:
        continue
    autores = [a for a in m.get("autores", []) if a in PARL]
    if not autores:
        continue
    grupo = classificar(m["tipo"], m["ementa"])
    PROPS.append(dict(id=m["id"], tipo=m["tipo"], numero=m.get("numero"), ano=m.get("ano"),
                      ementa=m["ementa"], data=m["data"], autores=autores, grupo=grupo,
                      lugares=extrair_lugares(m["ementa"], CFG.get("lugares_extras", []))))


def rotulo(p):
    num = f" nº {p['numero']}/{p['ano']}" if p.get("numero") else ""
    return f"{p['tipo']}{num}"


# ----------------------------------------------------------------- votos
def divisao(v):
    return len({x for x in v["votos"].values() if x in ("Sim", "Não", "Abstenção")}) > 1


def contagem(v):
    c = collections.Counter(v["votos"].values())
    return c.get("Sim", 0), c.get("Não", 0), c.get("Abstenção", 0)


def aviso_resultado(v):
    s, n, _ = contagem(v)
    r = (v.get("resultado") or "").lower()
    if (r.startswith("aprov") and n > s) or (r.startswith("rejeit") and s > n):
        return (' <span class="meta">Confira na Câmara: o resultado registrado não segue a contagem '
                'de maioria simples. Algumas votações exigem mais que maioria simples.</span>')
    return ""


DIVIDIDAS = sorted((v for v in VOTACOES if divisao(v)), key=lambda v: SESS[v["sessao"]]["data"], reverse=True)

# ---------------------------------------------------------------- blocos
def bloco_votacao(v, com_nomes=True):
    s, n, a = contagem(v)
    url = resumo(v["sessao"])
    cont = f'{link(url, str(s))} Sim e {link(url, str(n))} Não' + (f' e {link(url, str(a))} abstenção' if a else "")
    res = f' Resultado registrado: {e(v["resultado"])}.' if v.get("resultado") else ""
    quem = ""
    if com_nomes:
        lado = {k: [NOME.get(pid, str(pid)) for pid, x in v["votos"].items() if x == k] for k in ("Sim", "Não", "Abstenção")}
        partes = []
        for k in ("Sim", "Não", "Abstenção"):
            if lado[k] and len(lado[k]) <= 7:
                partes.append(f'Votaram {k}: {e(", ".join(sorted(lado[k])))}.')
        quem = "<p>" + " ".join(partes) + "</p>" if partes else ""
    return (f'<li><h3>{e(v["titulo"])}</h3><p class="meta">{link(url, br(SESS[v["sessao"]]["data"]))} · {cont}</p>'
            f'<p>{res.strip()}{aviso_resultado(v)}</p>{quem}</li>')


def bloco_proposta(p):
    outros = ""
    if len(p["autores"]) > 1:
        outros = f'<span class="meta">Autores: {e(", ".join(NOME[a] for a in p["autores"]))}</span>'
    return (f'<li><b>{e(rotulo(p))}</b> <span class="meta">· {br(p["data"])}</span>'
            f'<span class="tx">{e(p["ementa"])}</span>{outros}'
            f'<span class="meta">{link(materia_url(p["id"]), "Ler na Câmara")}</span></li>')


GRUPOS_TAB = [x for x in GRUPOS if x[0] != "rotina"]


def avatar(pid, nome):
    """Foto do vereador só se o arquivo fotos/<id>.jpg (ou .png/.webp) existir no repositório; senão, iniciais."""
    for ext in ("jpg", "jpeg", "png", "webp"):
        if (AQUI / "fotos" / f"{pid}.{ext}").exists():
            return f'<img class="av" src="fotos/{pid}.{ext}" alt="" width="64" height="64" loading="lazy">'
    return f'<span class="av" aria-hidden="true">{e(iniciais(nome))}</span>'


def iniciais(nome):
    base = re.sub(r"\(.*?\)", "", nome).split()
    base = [w for w in base if w.lower() not in ("de", "da", "do", "dos", "das", "e")]
    if not base:
        return "?"
    return (base[0][0] + (base[-1][0] if len(base) > 1 else "")).upper()


def bloco_vereador(pid):
    p = PARL[pid]
    # presença
    total = len(SESSOES_COM_PRESENCA)
    faltas = [s for s in SESSOES_COM_PRESENCA if pid not in PRES[s["id"]]]
    estev = total - len(faltas)
    if faltas:
        lf = " ".join(link(resumo(s["id"]), br(s["data"])[:5]) for s in faltas[:40])
        mais = f" e mais {len(faltas) - 40}" if len(faltas) > 40 else ""
        faltou = (f'<p class="meta">Sessões sem presença nem voto registrados para {e(p["nome"])}: {lf}{mais}.</p>')
    else:
        faltou = '<p class="meta">Nenhuma sessão sem presença registrada no período.</p>'
    so_voto = sum(1 for s in SESSOES_COM_PRESENCA if pid in PRES[s["id"]] and pid not in PRES_LISTA.get(s["id"], ()))
    nota_voto = (f" Em {so_voto} delas a lista de presença não traz o nome, mas há voto registrado na sessão, então contamos como presente."
                 if so_voto else "")
    pres = (f'<p>Esteve presente em {link(URL_PRESENCA, str(estev))} de {link(URL_SESSOES, str(total))} sessões. '
            f'Conta como presente quem aparece na lista de presença da sessão (expediente ou Ordem do Dia) ou votou nela.{nota_voto}</p>{faltou}')
    # votos
    meus = [v for v in VOTACOES if pid in v["votos"]]
    cnt = collections.Counter(v["votos"][pid] for v in meus)
    meus_div = [v for v in DIVIDIDAS if pid in v["votos"]]
    div_html = ""
    if meus_div:
        itens = "".join(
            f'<li>{link(resumo(v["sessao"]), br(SESS[v["sessao"]]["data"])[:5])} · {e(v["titulo"])}: '
            f'votou <b>{e(v["votos"][pid])}</b></li>' for v in meus_div)
        div_html = (f'<details class="g"><summary><span>Votações em que houve divisão</span>'
                    f'<span class="cnt">{len(meus_div)}</span></summary><ul class="votes props">{itens}</ul></details>')
    votos = (f'<p>Votou em {len(meus)} votações nominais: {cnt.get("Sim", 0)} Sim, {cnt.get("Não", 0)} Não, '
             f'{cnt.get("Abstenção", 0)} abstenção. Nas votações em que os vereadores votaram igual, o voto não é listado aqui.</p>{div_html}')
    # propostas
    minhas = [x for x in PROPS if pid in x["autores"]]
    por = {g[0]: sorted((x for x in minhas if x["grupo"] == g[0]), key=lambda x: x["data"], reverse=True) for g in GRUPOS}
    n = sum(len(v) for g, v in por.items() if g != "rotina")
    props = f"<p>{n} propostas no período. A contagem é feita por este site; cada proposta tem o seu link.</p>"
    for gid, nome, desc in GRUPOS:
        lst = por[gid]
        if not lst:
            props += f'<p class="g0">{e(nome)}: nenhuma no período.</p>'
            continue
        props += (f'<details class="g g-{gid}"><summary><span>{e(nome)}</span><span class="cnt">{len(lst)}</span></summary>'
                  f'<p class="small gd">{e(desc)}</p><ul class="props">{"".join(bloco_proposta(x) for x in lst)}</ul></details>')
    partido = f'<span class="pt">{e(p["partido"])}</span>' if p.get("partido") else ""
    status = "" if p.get("ativo") else '<span class="pt">não está no cargo</span>'
    atrib = (f'data-nome="{e(norm(p["nome"]))}" data-partido="{e(p.get("partido") or "")}" data-faltas="{len(faltas)}" '
             f'data-lei="{len(por["lei"])}" data-homenagem="{len(por["homenagem"])}" '
             f'data-melhoria="{len(por["melhoria"])}" data-nao="{cnt.get("Não", 0)}"')
    pct = round(100 * estev / total) if total else 0
    pastel = ["#fde7e3", "#fdf6d9", "#e6f7e1", "#e3eefc", "#efe6fb", "#fde6f1"][pid % 6]
    soma = sum(len(por[gid]) for gid, _, _ in GRUPOS_TAB)
    linhas = "".join(f'<li><i class="dot d-{gid}"></i><span>{e(nome)}</span><b>{len(por[gid])}</b></li>' for gid, nome, _ in GRUPOS_TAB)
    segs = "".join(f'<i class="s-{gid}" style="flex:{len(por[gid])}"></i>' for gid, _, _ in GRUPOS_TAB if por[gid])
    seg = f'<div class="seg" aria-hidden="true">{segs}</div>' if soma else ""
    ver_div = (f'<a class="abrir mais-l" href="#v{pid}">Ver quando votou diferente ({len(meus_div)}) →</a>' if meus_div else "")
    return (f'<article class="v cr" id="v{pid}" {atrib}>'
            f'<div class="cr-top" style="background:{pastel}">{avatar(pid, p["nome"])}'
            f'<div><h3 class="nm">{e(p["nome"])}</h3><p class="tags">{partido}{status}</p></div></div>'
            f'<div class="cr-pres"><span class="donut" style="--p:{pct}" role="img" aria-label="{pct}% das sessões"><b>{pct}%</b></span>'
            f'<p><b>{link(URL_PRESENCA, str(estev))} de {link(URL_SESSOES, str(total))}</b> sessões até agora<br>'
            f'<span class="meta">{len(faltas)} sem presença nem voto registrados</span></p></div>'
            f'<p class="mini"><b>{len(meus)}</b> votações nominais: {cnt.get("Sim", 0)} Sim · {cnt.get("Não", 0)} Não · {cnt.get("Abstenção", 0)} abstenção</p>'
            f'<h4>O que propôs até agora</h4>{seg}<ul class="gl">{linhas}</ul>{ver_div}'
            f'<details class="mais"><summary>Ver presença, votos e propostas, uma por uma</summary>'
            f'<div class="body"><h3>Presença</h3>{pres}<h3>Votos</h3>{votos}<h3>Propostas apresentadas</h3>{props}</div></details>'
            f'<a class="oficial" href="{e(SAPL)}/parlamentar/{pid}">Ficha oficial na Câmara ↗</a></article>')




# ------------------------------------------------ números gerais da cidade
MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
MESES_LONGOS = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]


def mes_ano(iso):
    a, m, _ = iso.split("-")
    return f"{MESES[int(m) - 1]} {a}"


CONTA = [x for x in PROPS if x["grupo"] != "rotina"]  # papéis de rotina da sessão ficam fora da conta
TOTAL = len(CONTA)
POR_GRUPO = collections.Counter(x["grupo"] for x in CONTA)
TIPO_ASSUNTO = {}
from regras import tipos_do_pedido  # noqa: E402

# --------------------------------------------- dados para a busca e o painel
indice = []
for p in sorted(CONTA, key=lambda x: (x["data"], x["id"]), reverse=True):
    indice.append(dict(id=p["id"], tipo=rotulo(p), data=br(p["data"]), texto=p["ementa"],
                       autores=[NOME[a] for a in p["autores"]],
                       lugares=sorted({n for n, _, _ in p["lugares"]}),
                       g=p["grupo"], gn=NOME_GRUPO[p["grupo"]],
                       ass=tipos_do_pedido(p["ementa"]) if so_pedido(p["tipo"]) else [],
                       url=materia_url(p["id"])))
PARTIDOS = {p["nome"]: p.get("partido") or "" for p in VER}
DADOS = json.dumps(dict(itens=indice, partidos=PARTIDOS), ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")

# ---------------------------------------------------- pedidos que se repetem
pedidos = []
for p in PROPS:
    principais = [(n, c) for n, c, ref in p["lugares"] if not ref]  # pontos de referência não contam
    if principais and so_pedido(p["tipo"]):
        pedidos.append(dict(id=p["id"], tipo=rotulo(p), ementa=p["ementa"], lugares=principais, data=p["data"],
                            autores=[NOME[a] for a in p["autores"]]))
REP, MESMO = repeticoes(pedidos)


def item_rep(p):
    return (f'<li><span class="meta">{br(p["data"])}</span> <b>{e(p["tipo"])}</b> '
            f'<span class="meta">por {e(", ".join(p["autores"]))}</span><span class="tx">{e(p["ementa"])}</span>'
            f'<span class="meta">{link(materia_url(p["id"]), "Ler na Câmara")}</span></li>')


def lista_rep(grupos):
    saida = ""
    for chave, v in sorted(grupos, key=lambda kv: -len(kv[1]["itens"])):
        itens = sorted(v["itens"].values(), key=lambda p: p["data"])
        datas = ", ".join(br(p["data"]) for p in itens)
        saida += (f'<div class="rep"><h3>{e(v["nome"])}</h3><p class="meta">{len(itens)} pedidos. Datas: {datas}</p>'
                  f'<ul class="props">{"".join(item_rep(p) for p in itens)}</ul></div>')
    return saida


def cartao_rep(chave, v, oculto):
    itens = sorted(v["itens"].values(), key=lambda p: p["data"])
    quem = {a for p in itens for a in p["autores"]}
    datas = [p["data"] for p in itens]
    periodo_rep = f"de {mes_ano(datas[0])} a {mes_ano(datas[-1])}" if mes_ano(datas[0]) != mes_ano(datas[-1]) else mes_ano(datas[0])
    qtd = f"{len(quem)} vereador pediu" if len(quem) == 1 else f"{len(quem)} vereadores pediram"
    return (f'<article class="rc{" extra" if oculto else ""}"{" hidden" if oculto else ""}><div class="rc-n"><b>{len(itens)}</b><span>vezes</span></div>'
            f'<div class="rc-t"><h3>{e(v["nome"])}</h3><p><span class="tag">{e(chave[1])}</span> '
            f'<span class="meta">{qtd} · {periodo_rep}</span></p></div>'
            f'<details class="rc-d"><summary>Ver pedidos e cobrar →</summary>'
            f'<ul class="props">{"".join(item_rep(p) for p in itens)}</ul></details></article>')


rep_ordenado = sorted(REP, key=lambda kv: -len(kv[1]["itens"]))
POR_PAGINA_REP = 9
rep_cards = "".join(cartao_rep(k, v, i >= POR_PAGINA_REP) for i, (k, v) in enumerate(rep_ordenado))
rep_mais = (f'<button type="button" class="botao" id="rep-mais" data-passo="{POR_PAGINA_REP}">Mostrar mais ruas ({len(rep_ordenado) - POR_PAGINA_REP} na fila)</button>'
            if len(rep_ordenado) > POR_PAGINA_REP else "")
rep_html = (f'<div class="rc-grid">{rep_cards}</div>{rep_mais}' if REP else
            '<p class="vazio">Nenhum tipo de pedido apareceu mais de uma vez para o mesmo lugar no período.</p>')
mesmo_html = lista_rep(MESMO) if MESMO else "<p class='vazio'>Nenhum.</p>"

# --------------------------------------------------------- partes da página
agora_utc = datetime.datetime.now(datetime.timezone.utc)
agora_br = agora_utc - datetime.timedelta(hours=3)
agora = agora_br.strftime("%d/%m/%Y")
conferido = f"{agora_br.day} de {MESES_LONGOS[agora_br.month - 1]} às {agora_br:%H:%M}"
periodo = f"{br(SESSOES[-1]['data'])} a {br(SESSOES[0]['data'])}" if SESSOES else ""
desde_txt = f"{MESES_LONGOS[int(desde[5:7]) - 1]} de {desde[:4]}" if len(desde) >= 7 and desde[0] != "0" else "o início do período"
CSS = (AQUI / "estilo.css").read_text(encoding="utf-8")
JS = (AQUI / "busca.js").read_text(encoding="utf-8")
UF = CFG.get("uf", "")
marca = CFG.get("marca") or [CIDADE.upper(), ""]
n = lambda x: f"{x:,}".replace(",", ".")

DESC_GRUPO = {
    "melhoria": "Tapar buraco, podar árvore, trocar lâmpada, pintar lombada. É um pedido: a Prefeitura decide se faz.",
    "pergunta": "Pedidos de explicação, documentos ou informações à Prefeitura e a outros órgãos.",
    "homenagem": "Parabéns, votos de pesar, título de cidadão, nome de rua e datas comemorativas.",
    "lei": "Projetos que criam regra, programa ou obrigação na cidade, e mudanças em projetos.",
    "outros": "O que não coube nos outros grupos.",
}
barra = "".join(f'<i class="s-{gid}" style="flex:{POR_GRUPO[gid]}"></i>' for gid, _, _ in GRUPOS_TAB if POR_GRUPO[gid])
cartoes_grupo = "".join(
    f'<article class="gc gc-{gid}"><p class="gc-n">{n(POR_GRUPO[gid])}</p><h3>{e(nome)} <span>até agora</span></h3>'
    f'<p class="gc-d">{e(DESC_GRUPO[gid])}</p><button type="button" class="ver-todas" data-g="{gid}">Ver todas →</button></article>'
    for gid, nome, _ in GRUPOS_TAB)

votos_iguais = sum(1 for v in VOTACOES if not divisao(v))
pct_iguais = round(100 * votos_iguais / len(VOTACOES)) if VOTACOES else 0
sem_lista = sum(1 for s in SESSOES if not PRES.get(s["id"]))
partidos = sorted({p["partido"] for p in VER if p.get("partido")})
opt_partidos = "".join(f'<option value="{e(x)}">{e(x)}</option>' for x in partidos)
cards = "".join(bloco_vereador(p["id"]) for p in VER)

chips = ""
vistos = {}
for p in CONTA:
    for nome, chave, _ in p["lugares"]:
        vistos.setdefault(chave, [nome, 0])[1] += 1
for chave, (nome, k) in sorted(vistos.items(), key=lambda kv: -kv[1][1])[:10]:
    chips += f'<button type="button" class="chip" data-q="{e(nome)}">{e(nome)}</button>'

sessoes_li = "".join(
    f'<li><span class="when">{link(resumo(s["id"]), br(s["data"]))}</span><span class="what">{e(s["titulo"])}</span>'
    f'<span class="acts">{link(resumo(s["id"]), "Presença e votos")}'
    + (f' · {link(s["url_ata"], "Ata (PDF)")}' if s.get("url_ata") else "") + "</span></li>"
    for s in SESSOES[:15])
div_html = "".join(bloco_votacao(v) for v in DIVIDIDAS[:20]) or "<li>Nenhuma no período.</li>"
GLOSSARIO = [
    ("Sessão ordinária", "Reunião marcada no calendário da Câmara."),
    ("Sessão extraordinária", "Reunião convocada fora do calendário, para tratar de um assunto específico."),
    ("Projeto de lei", "Proposta de uma nova lei. Pode vir do Executivo (prefeito) ou do Legislativo (vereadores)."),
    ("Emenda", "Mudança proposta no texto de um projeto."),
    ("Requerimento", "Pedido formal feito por vereador ao plenário, que vota se aceita."),
    ("Indicação", "Sugestão de um vereador ao prefeito sobre algo que a prefeitura pode fazer."),
    ("Moção", "Posicionamento da Câmara sobre um assunto, como aplauso, apoio ou repúdio."),
    ("Pedido de urgência", "Pedido para um projeto ser votado mais rápido que o normal."),
    ("Parecer", "Opinião escrita de uma comissão da Câmara sobre um projeto."),
    ("Decreto legislativo", "Ato votado só pela Câmara, sem passar pelo prefeito."),
    ("Veto", "Quando o prefeito recusa, no todo ou em parte, uma lei aprovada pela Câmara."),
    ("Voto nominal", "Votação em que o voto de cada vereador fica registrado com o nome."),
]
gloss = "".join(f"<dt>{e(a)}</dt><dd>{e(b)}</dd>" for a, b in GLOSSARIO)
URL_MATERIAS = f"{SAPL}/materia/pesquisar-materia"
RADAR = ('<svg class="radar" viewBox="0 0 64 64" aria-hidden="true"><circle cx="32" cy="32" r="5" fill="currentColor"/>'
         '<path d="M19 19a18 18 0 0 0 0 26M45 19a18 18 0 0 1 0 26" fill="none" stroke="currentColor" stroke-width="5" stroke-linecap="round"/>'
         '<path d="M10 10a31 31 0 0 0 0 44M54 10a31 31 0 0 1 0 44" fill="none" stroke="currentColor" stroke-width="5" stroke-linecap="round"/></svg>')

PAGINA = f"""<title>Radar {e(CIDADE)}</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@500;700;800;900&family=Atkinson+Hyperlegible:wght@400;700&display=swap">
<style>{CSS}</style>
<div class="wrap">
<header class="top">
<p class="pill"><i class="live"></i><span id="conf" data-t="{agora_utc.strftime('%Y-%m-%dT%H:%M:%SZ')}">Dados conferidos na Câmara em {agora}</span></p>
<h1 class="logo" aria-label="Radar {e(CIDADE)}">{RADAR}<span class="l1">RADAR</span><span class="l2"><em>{e(marca[0])}</em>{e(marca[1])}</span></h1>
<p class="sub"><b>Raio-X de {e(CIDADE)}-{e(UF)}.</b> O que cada vereador fez desde {desde_txt}, contado todo dia.</p>
<div class="grande"><p class="gl-t">Propostas apresentadas pelos {len(VER)} vereadores desde {desde_txt}</p>
<p class="gl-n">{link(URL_MATERIAS, n(TOTAL))}</p>
<p class="gl-s">Só conta proposta em que um vereador é autor. Fora: prefeito, Mesa, comissões e papéis de rotina da sessão. {link(URL_SESSOES, n(len(SESSOES)) + " sessões")} e {n(len(VOTACOES))} votações nominais lidas.</p></div>
<ul class="tiles">
<li class="t-melhoria"><b>{n(POR_GRUPO["melhoria"])}</b><span>{link(URL_MATERIAS, "pedidos nos bairros")} até agora</span></li>
<li class="t-pergunta"><b>{n(POR_GRUPO["pergunta"])}</b><span>{link(URL_MATERIAS, "perguntas e cobranças")} até agora</span></li>
<li class="t-homenagem"><b>{n(POR_GRUPO["homenagem"])}</b><span>{link(URL_MATERIAS, "homenagens")} até agora</span></li>
<li class="t-lei"><b>{n(POR_GRUPO["lei"])}</b><span>{link(URL_MATERIAS, "propostas de lei")} até agora</span></li></ul>
<p class="atual">Última conferência na Câmara: {conferido} (horário de Brasília). O robô volta lá todo dia de madrugada.
Este site mostra só dados da Câmara. Não dá nota e não dá opinião.</p>
</header>

<section aria-labelledby="buscaH"><p class="kick">Comece por aqui</p><h2 id="buscaH">O que pediram pelo seu bairro?</h2>
<p class="small">Digite o bairro ou a rua. Sem nada digitado, você vê a cidade inteira. Funciona sem acento.</p>
<div class="campo"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7" fill="none" stroke="currentColor" stroke-width="2"/><path d="M16 16l5 5" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>
<input id="busca" type="search" autocomplete="off" enterkeyhint="search" placeholder="Digite seu bairro ou sua rua" aria-label="Bairro ou rua"></div>
<div class="chips2" aria-label="Lugares citados nos pedidos">{chips}</div>
<div id="painel" class="painel" aria-live="polite"></div>
<p class="small">Pedido repetido não prova que a Prefeitura ignorou. Veja mais em <a href="#repetidos">O problema que não some</a>.</p>
<script type="application/json" id="dados">{DADOS}</script></section>

<section aria-labelledby="repetidos"><p class="kick">Só aqui</p><h2 id="repetidos">O problema que não some</h2>
<p class="small">Quando o mesmo tipo de pedido volta várias vezes para a mesma rua, é sinal de que o assunto continua em pauta. O site da Câmara não mostra isso: nós cruzamos os pedidos um por um.</p>
<div class="aviso2"><p><b>Pedido repetido não prova que a Prefeitura ignorou.</b></p>
<p>O pedido anterior pode ter sido atendido e o problema voltou. A obra pode estar em andamento. A resposta pode estar em outro documento. Dois vereadores podem pedir coisas parecidas sem saber um do outro. Este site não sabe se houve resposta.</p></div>
{rep_html}
<details class="como"><summary>Como contamos</summary>
<p>Contamos quando <b>o mesmo tipo de pedido</b> (como asfalto, iluminação ou limpeza) foi feito <b>mais de uma vez para o mesmo lugar</b>. Contam só indicações e requerimentos. Os lugares são achados pelo nome de rua, bairro ou prédio escrito em cada pedido. Nomes que aparecem só como referência ("entre a Rua A e a Rua B", "próximo à") não entram na conta, mas o programa pode errar, então confira o texto de cada pedido. Os tipos vêm de palavras do texto.</p></details>
<details class="como"><summary>Mesmo lugar, assuntos diferentes</summary>
<p class="small">Lugares que aparecem em mais de um pedido, com assuntos que não são do mesmo tipo. Não é repetição.</p>{mesmo_html}</details></section>

<section aria-labelledby="trabalho"><p class="kick">O trabalho da Câmara</p><h2 id="trabalho">Homenagem ou trabalho?</h2>
<p class="small">São {n(TOTAL)} propostas até agora, e a conta sobe toda semana. Toque em um grupo para ler cada uma. Um grupo não vale mais que outro: é só contagem.</p>
<div class="seg seg-g" aria-hidden="true">{barra}</div>
<div class="gcs">{cartoes_grupo}</div>
<div id="lista-grupo" class="painel" hidden></div></section>

<section aria-labelledby="vereadores"><p class="kick">Um por um</p><h2 id="vereadores">Os {len(VER)} vereadores</h2>
<p class="small">Até agora, em {pct_iguais} de cada 100 votações todos votaram igual. Toque nos números do crachá para ver os detalhes.</p>
<div class="ctrl"><div><label for="filtro" class="lbl">Buscar por nome</label><input id="filtro" type="search" autocomplete="off" placeholder="Nome do vereador"></div>
<div><label for="partido" class="lbl">Partido</label><select id="partido"><option value="">Todos</option>{opt_partidos}</select></div>
<div><label for="ordem" class="lbl">Ordenar por</label><select id="ordem"><option value="nome">Nome (A a Z)</option>
<option value="faltas">Mais sessões sem presença</option><option value="lei">Mais propostas de lei</option>
<option value="homenagem">Mais homenagens</option><option value="melhoria">Mais pedidos para os bairros</option>
<option value="nao">Mais votos "Não"</option></select></div></div>
<p class="small" id="mostrando" aria-live="polite"></p>
<div id="lista">{cards}</div></section>

<section aria-labelledby="divisao"><p class="kick">Votos</p><h2 id="divisao">Votações em que os vereadores votaram diferente</h2>
<p class="small">As 20 mais recentes. As demais aparecem na ficha de cada vereador.</p>
<ul class="splits">{div_html}</ul></section>

<section aria-labelledby="sessoes"><p class="kick">Calendário</p><h2 id="sessoes">Sessões</h2>
<ul class="sessions">{sessoes_li}</ul>
<p class="small" style="margin-top:.75rem">Lista completa em {link(URL_SESSOES, "a pesquisa de sessões da Câmara")}.</p></section>

<section aria-labelledby="fontes"><p class="kick">Transparência</p><h2 id="fontes">De onde vêm os números</h2>
<p class="small">Tudo sai do sistema da própria Câmara Municipal ({link(SAPL + "/", "SAPL")}). Nada é digitado à mão: um programa baixa os dados todos os dias de madrugada.</p>
<div class="fc">
<article><h3>Presença</h3><p>Conta como presente quem aparece na lista de presença da sessão (expediente ou Ordem do Dia) ou votou nela, porque as listas às vezes deixam nomes de fora. São {len(SESSOES)} sessões desde {desde_txt}{f", e {sem_lista} ficaram de fora porque o sistema não registrou a presença de ninguém nelas" if sem_lista else ""}. "Sem presença" não diz o motivo da ausência.</p></article>
<article><h3>Homenagem ou trabalho</h3><p>O site separa cada proposta pelo tipo e pelas palavras do texto oficial, com a mesma regra para todos. Abra qualquer grupo, leia uma por uma e tire a sua conclusão.</p></article>
<article><h3>Pedido não é obra feita</h3><p>Um pedido de melhoria é só um pedido. O sistema da Câmara não informa se a Prefeitura atendeu.</p></article>
<article><h3>Votos</h3><p>Só entram as votações em que o sistema registra o voto de cada vereador: {n(len(VOTACOES))} desde {desde_txt}. Em {n(votos_iguais)} delas, todos votaram igual.</p></article>
<article><h3>Atualização</h3><p>O robô confere a Câmara todo dia de madrugada. Se a coleta vier incompleta ou estranha, o site não é trocado e continua com a última versão boa.</p></article>
<article><h3>Achou um erro?</h3><p>Abra a ficha oficial pelo link do crachá e compare. Se a Câmara corrigir o registro, o número daqui muda na atualização seguinte. Se a diferença continuar, o erro pode estar em como este site agrupa os dados.</p></article></div></section>

<section aria-labelledby="regra"><h2 id="regra">Como agrupamos as propostas</h2>
<p>A regra é a mesma para todos os vereadores. O site olha cada proposta na ordem abaixo, e a primeira regra que servir decide o grupo.</p>
<ol class="rule">
<li><b>Só entram propostas com vereador como autor.</b> Ficam de fora as do prefeito, da Mesa Diretora, das comissões e as atas.</li>
<li><b>Papéis de rotina:</b> dispensa de leitura, dispensa de parecer e inversão de pauta. Não entram na conta.</li>
<li><b>Homenagens e datas:</b> textos com aplausos, congratulações, parabéns, pesar, louvor, título de cidadão, nome de rua, semana ou dia municipal.</li>
<li><b>Propostas de lei:</b> projetos de lei, de resolução e de decreto legislativo, e emendas.</li>
<li><b>Pedidos de melhoria nos bairros:</b> indicações, e requerimentos que pedem "providências urgentes".</li>
<li><b>Perguntas e cobranças:</b> requerimentos que pedem informações, documentos, cópias ou explicações.</li>
<li><b>Outros:</b> tudo que sobrou.</li></ol>
<p class="small">O site não interpreta o sentido do texto. Só usa o tipo da proposta e as palavras acima. Uma proposta com mais de um autor aparece na lista de cada autor. Quem discordar de um grupo pode ler o texto oficial pelo link da proposta.</p></section>

<section aria-labelledby="palavras"><h2 id="palavras">Palavras que aparecem</h2>
<p class="small">Explicações gerais, escritas por este site. Não vêm da Câmara.</p><dl>{gloss}</dl></section>

<footer><p>Radar {e(CIDADE)} é um projeto independente, feito por morador, sem vínculo com a Câmara, com a Prefeitura ou com partido.</p>
<p>Fonte: Câmara Municipal de {e(CIDADE)}, sistema {link(SAPL + "/", "SAPL")}. Coleta de {conferido}.</p>
<p>Os dados da Câmara estão sob licença {link("https://creativecommons.org/licenses/by/4.0/", "Creative Commons BY 4.0")}.</p>
<p>Se um número aqui for diferente do site da Câmara, vale o da Câmara.</p></footer>
</div>
<script>{JS}</script>
"""
PASTA_SAIDA.mkdir(parents=True, exist_ok=True)
if (AQUI / "fotos").is_dir():
    import shutil
    shutil.copytree(AQUI / "fotos", PASTA_SAIDA / "fotos", dirs_exist_ok=True)
(PASTA_SAIDA / "index.html").write_text(PAGINA, encoding="utf-8")
print(f"ok: {len(SESSOES)} sessões, {len(VER)} vereadores, {len(VOTACOES)} votações ({len(DIVIDIDAS)} divididas), "
      f"{TOTAL} propostas, {len(REP)} grupos repetidos -> {PASTA_SAIDA / 'index.html'}")
