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
    return (f'<details class="v" id="v{pid}" {atrib}><summary><span class="av" aria-hidden="true">{e(iniciais(p["nome"]))}</span>'
            f'<span class="info"><span class="who"><span class="nm">{e(p["nome"])}</span>{partido}{status}</span>'
            f'<span class="sum">{estev} de {total} sessões · {len(meus)} votações · {n} propostas</span>'
            f'<span class="bar" role="img" aria-label="Presença registrada em {estev} de {total} sessões"><i style="width:{pct}%"></i></span></span></summary>'
            f'<div class="body"><h3>Presença</h3>{pres}<h3>Votos</h3>{votos}<h3>Propostas apresentadas</h3>{props}</div></details>')


# --------------------------------------------- busca e problemas repetidos
indice = []
for p in PROPS:
    if p["grupo"] == "rotina":
        continue
    indice.append(dict(id=p["id"], tipo=rotulo(p), data=br(p["data"]), texto=p["ementa"],
                       autores=[NOME[a] for a in p["autores"]], lugares=sorted({n for n, _, _ in p["lugares"]}),
                       grupo=NOME_GRUPO[p["grupo"]], url=materia_url(p["id"])))
DADOS = json.dumps(indice, ensure_ascii=False).replace("</", "<\\/")

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


def lista_rep(grupos, com_tipo):
    saida = ""
    ordem = sorted(grupos, key=lambda kv: -len(kv[1]["itens"]))
    for chave, v in ordem:
        itens = sorted(v["itens"].values(), key=lambda p: p["data"])
        titulo = f'{e(v["nome"])} · {e(chave[1])}' if com_tipo else e(v["nome"])
        datas = ", ".join(br(p["data"]) for p in itens)
        saida += (f'<div class="rep"><h3>{titulo}</h3><p class="meta">{len(itens)} pedidos. Datas: {datas}</p>'
                  f'<ul class="props">{"".join(item_rep(p) for p in itens)}</ul></div>')
    return saida


rep_html = lista_rep(REP, True) if REP else (
    '<p class="vazio">Nenhum tipo de pedido apareceu mais de uma vez para o mesmo lugar no período.</p>')
mesmo_html = lista_rep(MESMO, False) if MESMO else "<p class='vazio'>Nenhum.</p>"

# ------------------------------------------------------------------ página
agora = datetime.date.today().strftime("%d/%m/%Y")
periodo = f"{br(SESSOES[-1]['data'])} a {br(SESSOES[0]['data'])}" if SESSOES else ""
CSS = (AQUI / "estilo.css").read_text(encoding="utf-8")
JS = (AQUI / "busca.js").read_text(encoding="utf-8")
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
chips = ""
vistos = {}
for p in PROPS:
    for nome, chave, _ in p["lugares"]:
        vistos.setdefault(chave, [nome, 0])[1] += 1
for chave, (nome, n) in sorted(vistos.items(), key=lambda kv: -kv[1][1])[:14]:
    chips += f'<button type="button" class="chip" data-q="{e(nome)}">{e(nome)}</button>'
sessoes_li = "".join(
    f'<li><span class="when">{link(resumo(s["id"]), br(s["data"]))}</span><span class="what">{e(s["titulo"])}</span>'
    f'<span class="acts">{link(resumo(s["id"]), "Presença e votos")}'
    + (f' · {link(s["url_ata"], "Ata (PDF)")}' if s.get("url_ata") else "") + "</span></li>"
    for s in SESSOES[:15])
div_html = "".join(bloco_votacao(v) for v in DIVIDIDAS[:20]) or "<li>Nenhuma no período.</li>"

partidos = sorted({p["partido"] for p in VER if p.get("partido")})
opt_partidos = "".join(f'<option value="{e(x)}">{e(x)}</option>' for x in partidos)
GRUPOS_TAB = [g_ for g_ in GRUPOS if g_[0] != "rotina"]
linhas_tab = ""
for p in sorted(VER, key=lambda p: norm(p["nome"])):
    ms = [x for x in PROPS if p["id"] in x["autores"]]
    cel = "".join(f'<td>{sum(1 for x in ms if x["grupo"] == gid)}</td>' for gid, _, _ in GRUPOS_TAB)
    linhas_tab += f'<tr><th scope="row"><a href="#v{p["id"]}" class="abrir">{e(p["nome"])}</a></th>{cel}</tr>'
cab_tab = "".join(f'<th scope="col">{e(n)}</th>' for _, n, _ in GRUPOS_TAB)
tab_html = (f'<div class="rolar"><table class="tab"><thead><tr><th scope="col">Vereador</th>{cab_tab}</tr></thead>'
            f'<tbody>{linhas_tab}</tbody></table></div>')

PAGINA = f"""<title>Vereadores de {e(CIDADE)}</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible:wght@400;700&family=Bricolage+Grotesque:opsz,wght@12..96,700;12..96,800&display=swap">
<style>{CSS}</style>
<div class="wrap">
<header class="hero"><p class="kicker">Radar da Câmara · dados oficiais</p>
<h1>Vereadores de <span>{e(CIDADE)}</span></h1>
<p class="lead">O que cada vereador fez nas sessões da Câmara: se foi, como votou e o que propôs. Sem nota e sem opinião.</p>
<ul class="stats" aria-label="Números do período">
<li><b>{len(VER)}</b><span>{link(SAPL + "/parlamentar/", "vereadores no cargo")}</span></li>
<li><b>{len(SESSOES)}</b><span>{link(URL_SESSOES, "sessões")}</span></li>
<li><b>{len(VOTACOES)}</b><span>{link(URL_SESSOES, "votações nominais")}</span></li>
<li><b>{len(PROPS)}</b><span>{link(SAPL + "/materia/pesquisar-materia", "propostas de vereadores")}</span></li></ul>
<p class="atual">Período {periodo} · atualizado em {agora}</p></header>

<section class="box" aria-labelledby="aviso"><h2 id="aviso">Antes de ler</h2>
<p>Este site mostra só dados publicados pela Câmara Municipal. Não dá nota e não dá opinião.</p>
<p>Todo número tem um link. Toque nele para ver a página da Câmara de onde veio.</p>
<p>Os textos das propostas são as ementas, os resumos registrados pela própria Câmara.</p>
<p>Este site é independente. Não é da Câmara.</p></section>

<nav aria-labelledby="comece"><h2 id="comece" class="sr">Comece por aqui</h2>
<div class="atalhos">
<a href="#buscaH"><b>Moro numa rua ou bairro</b><span>Veja o que foi pedido para lá e por quem</span></a>
<a href="#vereadores"><b>Quero ver um vereador</b><span>Presença, votos e propostas de cada um</span></a>
<a href="#trabalho"><b>Homenagem ou trabalho?</b><span>Quantas propostas de cada tipo</span></a>
<a href="#repetidos"><b>O problema que não some</b><span>Pedidos que voltam para o mesmo lugar</span></a></div></nav>

<section aria-labelledby="buscaH"><h2 id="buscaH">Busque sua rua ou bairro</h2>
<p class="small">Digite o nome e veja o que os vereadores pediram para lá, e quem pediu. Funciona sem acento.</p>
<label for="busca" class="lbl">Rua, bairro ou lugar</label>
<input id="busca" type="search" autocomplete="off" enterkeyhint="search" placeholder="Ex.: nome de uma rua ou bairro">
<div class="chips2" aria-label="Lugares citados nos pedidos"><span class="small">Lugares mais citados:</span> {chips}</div>
<div id="resultado" aria-live="polite"></div>
<p class="small">Pedido repetido não prova que a Prefeitura ignorou. Veja mais em <a href="#repetidos">Pedidos que se repetem</a>.</p>
<script type="application/json" id="dados">{DADOS}</script></section>

<section aria-labelledby="repetidos"><h2 id="repetidos">Pedidos que se repetem para o mesmo lugar</h2>
<div class="aviso2"><p><b>Pedido repetido não prova que a Prefeitura ignorou.</b></p>
<p>O pedido anterior pode ter sido atendido e o problema voltou. A obra pode estar em andamento. A resposta pode estar em outro documento. Dois vereadores podem pedir coisas parecidas sem saber um do outro. Este site não sabe se houve resposta.</p></div>
<p>Aqui contamos quando <b>o mesmo tipo de pedido</b> (como asfalto, iluminação ou limpeza) foi feito <b>mais de uma vez para o mesmo lugar</b>. Contam só indicações e requerimentos. Os lugares são achados pelo nome de rua, bairro ou prédio escrito em cada pedido. Nomes que aparecem só como referência (\"entre a Rua A e a Rua B\", \"próximo à\") não entram na conta, mas o programa pode errar, então confira o texto de cada pedido. Os tipos vêm de palavras do texto. A contagem é feita por este site, e cada pedido listado tem o seu link.</p>
{rep_html}
<h3 class="sub">Mesmo lugar, assuntos diferentes</h3>
<p class="small">Lugares que aparecem em mais de um pedido, com assuntos que não são do mesmo tipo. Não é repetição.</p>
{mesmo_html}</section>

<section aria-labelledby="vereadores"><h2 id="vereadores">Os vereadores</h2>
<label for="filtro" class="lbl">Procurar pelo nome</label>
<input id="filtro" type="search" autocomplete="off" placeholder="Nome do vereador">
<div class="ctrl"><div><label for="partido" class="lbl">Partido</label>
<select id="partido"><option value="">Todos</option>{opt_partidos}</select></div>
<div><label for="ordem" class="lbl">Ordenar por</label>
<select id="ordem"><option value="nome">Nome (A a Z)</option>
<option value="faltas">Mais sessões sem presença</option>
<option value="lei">Mais propostas de lei</option>
<option value="homenagem">Mais homenagens</option>
<option value="melhoria">Mais pedidos para os bairros</option>
<option value="nao">Mais votos "Não"</option></select></div></div>
<p class="small" id="mostrando" aria-live="polite"></p>
<p class="small">Toque no nome para ver a presença, os votos e as propostas.</p>
<div id="lista">{"".join(bloco_vereador(p["id"]) for p in VER)}</div></section>

<section aria-labelledby="trabalho"><h2 id="trabalho">Homenagem ou trabalho?</h2>
<p class="small">Quantas propostas cada vereador apresentou em cada grupo, pela mesma regra para todos (veja "Como agrupamos as propostas"). É só contagem: um grupo não vale mais que outro. Toque no nome para ler proposta por proposta.</p>
{tab_html}</section>

<section aria-labelledby="divisao"><h2 id="divisao">Votações em que os vereadores votaram diferente</h2>
<p class="small">As 20 mais recentes. As demais aparecem na ficha de cada vereador.</p>
<ul class="splits">{div_html}</ul></section>

<section aria-labelledby="sessoes"><h2 id="sessoes">Sessões</h2>
<ul class="sessions">{sessoes_li}</ul>
<p class="small" style="margin-top:.75rem">Lista completa em {link(URL_SESSOES, "a pesquisa de sessões da Câmara")}.</p></section>

<section aria-labelledby="regra"><h2 id="regra">Como agrupamos as propostas</h2>
<p>A regra é a mesma para todos os vereadores. O site olha cada proposta na ordem abaixo, e a primeira regra que servir decide o grupo.</p>
<ol class="rule">
<li><b>Só entram propostas com vereador como autor.</b> Ficam de fora as do prefeito, da Mesa Diretora, das comissões e as atas.</li>
<li><b>Papéis de rotina:</b> dispensa de leitura, dispensa de parecer e inversão de pauta.</li>
<li><b>Homenagens e datas:</b> textos com aplausos, congratulações, parabéns, pesar, louvor, título de cidadão, nome de rua, semana ou dia municipal.</li>
<li><b>Propostas de lei:</b> projetos de lei, de resolução e de decreto legislativo, e emendas.</li>
<li><b>Pedidos de melhoria nos bairros:</b> indicações, e requerimentos que pedem "providências urgentes".</li>
<li><b>Perguntas e cobranças:</b> requerimentos que pedem informações, documentos, cópias ou explicações.</li>
<li><b>Outros:</b> tudo que sobrou.</li></ol>
<p class="small">O site não interpreta o sentido do texto. Só usa o tipo da proposta e as palavras acima. Uma proposta com mais de um autor aparece na lista de cada autor. Quem discordar de um grupo pode ler o texto oficial pelo link da proposta.</p></section>

<section aria-labelledby="fontes"><h2 id="fontes">De onde vêm os números</h2>
<p>Tudo vem do sistema da própria Câmara ({link(SAPL + "/", "SAPL")}). Ninguém digita nada à mão: um programa baixa os dados todos os dias de madrugada.</p>
<ul class="rule"><li><b>Presença:</b> as listas de presença de cada sessão (expediente e Ordem do Dia) e os votos. Quem votou numa sessão conta como presente nela, porque as listas às vezes deixam nomes de fora. "Sem presença" não diz o motivo da ausência.</li>
<li><b>Votos:</b> votações nominais, com o voto de cada vereador.</li>
<li><b>Propostas e grupos:</b> o tipo e o texto oficial de cada matéria, agrupados pela regra abaixo.</li>
<li><b>Pedidos repetidos e busca por rua:</b> nomes de lugares achados no texto, por um programa que pode errar.</li></ul>
<p class="small">Se a coleta do dia vier incompleta ou estranha, o site não é trocado e continua com a última versão boa. Este site não mostra salários, porque eles não estão nesse sistema.</p></section>

<section aria-labelledby="erro"><h2 id="erro">Achou um erro?</h2>
<p>Toque no link de qualquer número ou proposta e compare com a página da Câmara. Se a Câmara corrigir um registro, o número muda na próxima atualização. Se a diferença continuar, o erro pode estar na forma como este site agrupa ou lê os dados.</p></section>

<section aria-labelledby="palavras"><h2 id="palavras">Palavras que aparecem</h2>
<p class="small">Explicações gerais, escritas por este site. Não vêm da Câmara.</p><dl>{gloss}</dl></section>

<footer><p>Fonte: Câmara Municipal de {e(CIDADE)}, sistema {link(SAPL + "/", "SAPL")}. Dados lidos em {agora}.</p>
<p>Os dados da Câmara estão sob licença {link("https://creativecommons.org/licenses/by/4.0/", "Creative Commons BY 4.0")}.</p>
<p>Se um número aqui for diferente do site da Câmara, vale o da Câmara. Se a Câmara corrigir um registro, o número muda na próxima atualização.</p></footer>
</div>
<script>{JS}</script>
"""
PASTA_SAIDA.mkdir(parents=True, exist_ok=True)
(PASTA_SAIDA / "index.html").write_text(PAGINA, encoding="utf-8")
print(f"ok: {len(SESSOES)} sessões, {len(VER)} vereadores, {len(VOTACOES)} votações ({len(DIVIDIDAS)} divididas), "
      f"{len(PROPS)} propostas, {len(REP)} grupos repetidos -> {PASTA_SAIDA / 'index.html'}")
