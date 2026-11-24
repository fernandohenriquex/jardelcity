"""Regras de classificação. Valem igual para todos os vereadores.

Nada aqui interpreta o sentido de um texto. Só olha o tipo da proposta
e palavras escritas nela. Se uma regra estiver ruim, mude AQUI e rode de novo.
"""
import re
import unicodedata


def norm(s):
    """Minúsculas e sem acento, para buscar e comparar."""
    s = unicodedata.normalize("NFD", str(s))
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()


# ---------------------------------------------------------------- grupos
GRUPOS = [
    ("melhoria", "Pedidos de melhoria nos bairros", "Pedem à Prefeitura uma obra, um conserto ou um serviço."),
    ("pergunta", "Perguntas e cobranças", "Pedem à Prefeitura informações, documentos ou explicações."),
    ("homenagem", "Homenagens e datas", "Aplausos, parabéns, pesar, título de cidadão, nome de rua, semana ou dia comemorativo."),
    ("lei", "Propostas de lei", "Projetos de lei e mudanças (emendas) em projetos."),
    ("outros", "Outros", "O que não coube nos grupos acima."),
    ("rotina", "Papéis de rotina da sessão", "Dispensa de leitura, dispensa de parecer e inversão de pauta."),
]
NOME_GRUPO = {g[0]: g[1] for g in GRUPOS}

_HOMENAGEM = re.compile(
    r"aplausos|congratula|parabeniz|\bpesar\b|louvor|homenage|t[ií]tulo de cidad[ãa]o|"
    r"cidad[ãa]o honor[áa]rio|denomina|semana municipal|dia municipal|data comemorativa",
    re.I,
)
_ROTINA_TEXTO = re.compile(r"dispensa|invers[ãa]o", re.I)
_PEDE_INFO = re.compile(r"informaç|document|cópia|copia|explicaç|pergunta|esclarec", re.I)


def classificar(tipo, ementa):
    """Devolve a chave do grupo. A primeira regra que servir decide."""
    t, x = str(tipo).lower(), str(ementa).lower()
    if t.startswith("dispensa") or ("verbal" in t and _ROTINA_TEXTO.search(x)):
        return "rotina"
    if _HOMENAGEM.search(x):
        return "homenagem"
    if t.startswith(("projeto de lei", "projeto de resolu", "projeto de decreto", "emenda")):
        return "lei"
    if "indicaç" in t or "indicac" in t or "providências urgentes" in x:
        return "melhoria"
    if t == "requerimento" and _PEDE_INFO.search(x):
        return "pergunta"
    return "outros"


def so_pedido(tipo):
    """Só indicações e requerimentos escritos entram no cruzamento de repetidos."""
    t = str(tipo).lower()
    return "indicaç" in t or "indicac" in t or t == "requerimento"


# ---------------------------------------------------------- tipo de assunto
TIPOS = [
    ("Asfalto e pavimentação", r"asfalt|pavimenta|recapea|tapa-buraco|buraco"),
    ("Iluminação pública", r"ilumina|l[âa]mpada|poste"),
    ("Água, esgoto e drenagem", r"vazamento|esgoto|drenagem|galeria|bueiro|enchente"),
    ("Trânsito e sinalização", r"lombada|redutor|sinaliza|faixa de pedestre|sem[áa]foro"),
    ("Conservação, limpeza e reforma", r"conserva[çc]|limpeza|manuten|reforma|bancos quebrados|capina|mato alto|entulho"),
    ("Meio ambiente", r"ambiental|preserva|[áa]rvore|poda"),
]
_TIPOS_RX = [(n, re.compile(rx, re.I)) for n, rx in TIPOS]


def tipos_do_pedido(ementa):
    return [n for n, rx in _TIPOS_RX if rx.search(ementa)]


# --------------------------------------------------------------- lugares
_LOG = r"(?:Rua|Avenida|Av\.?|Alameda|Travessa|Pra[çc]a|Estrada|Rodovia|Viela|Largo|Beco)"
_BAIRRO = (r"(?:Jardim|Vila|Parque|Loteamento|Residencial|Conjunto Habitacional|"
           r"N[úu]cleo|Condom[ií]nio|Ch[áa]caras|Recanto)")
_EQUIP = r"(?:E\.M\.E\.F\.?|EMEF|UBS|CEMEI|CRAS|Creche|Escola|Hospital|Posto de Sa[úu]de)"
_GEN = r"(?:Bairro|Distrito|Setor)"
_W = r"(?:[A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-Za-zÀ-ÿ0-9'’-]*|\d+[ºª]?)"
_C = r"(?:de|da|do|dos|das|e)"
_NOME = rf"{_W}(?:\s+(?:{_C}\s+)?{_W}){{0,5}}"
_Q = r"[\"“‘']?"
# O começo ("rua", "loteamento", "UBS") pode estar em minúscula; o nome precisa começar com maiúscula.
_PADRAO = re.compile(
    rf"\b(?i:({_LOG}|{_BAIRRO}|{_EQUIP}))\s+{_Q}\s*(?:{_C}\s+)?({_NOME})"
    rf"|\b(?i:({_GEN}))\s+(?!(?i:{_BAIRRO}|{_LOG})\b){_Q}\s*({_NOME})"
)
_ABREV = {"av": "avenida", "av.": "avenida"}


_REFERENCIA = re.compile(r"\b(entre|esquina|pr[óo]xim[oa]|em frente|ao lado|altura|divisa|at[ée])\b", re.I)


def _e_referencia(ementa, inicio):
    """O lugar aparece só como ponto de referência? Ex.: "na Rua A, entre a Rua B e a Rua C"."""
    antes = ementa[max(0, inicio - 70):inicio]
    antes = antes.split(".")[-1].split(";")[-1]
    return bool(_REFERENCIA.search(antes))


def extrair_lugares(ementa, extras=()):
    """Acha nomes de rua, bairro e lugares citados. Devolve [(nome, chave, referencia)].

    Só pega nomes escritos com iniciais maiúsculas depois de Rua, Avenida,
    Jardim, Vila etc. Lugares sem essa palavra (como "Estação Rodoviária")
    só são achados se estiverem na lista `lugares_extras` do config.json.
    `referencia` é True quando o lugar aparece só como ponto de referência
    ("entre", "esquina", "próximo", "em frente"). Esses lugares servem para a
    busca, mas não entram na conta de pedidos repetidos.
    """
    achados, vistos = [], set()
    for m in _PADRAO.finditer(ementa):
        tipo = m.group(1) or m.group(3)
        nome = (m.group(2) or m.group(4)).strip()
        chave_tipo = _ABREV.get(norm(tipo).rstrip("."), norm(tipo).rstrip("."))
        chave = f"{chave_tipo} {norm(nome)}"
        if chave not in vistos:
            vistos.add(chave)
            achados.append((f"{tipo} {nome}", chave, _e_referencia(ementa, m.start())))
    xn = norm(ementa)
    for extra in extras:
        pos = xn.find(norm(extra))
        if pos >= 0 and norm(extra) not in vistos:
            vistos.add(norm(extra))
            achados.append((extra, norm(extra), _e_referencia(ementa, pos)))
    return achados


def repeticoes(pedidos):
    """pedidos: [{id, tipo, ementa, lugares:[(nome,chave)], data, autores}].

    Devolve (repetidos, mesmo_lugar). repetidos: mesmo lugar E mesmo tipo de
    assunto, 2 pedidos ou mais. mesmo_lugar: lugar com 2+ pedidos de assuntos
    diferentes (não é repetição).
    """
    por_tipo, por_lugar = {}, {}
    for p in pedidos:
        tp = tipos_do_pedido(p["ementa"])
        for nome, chave in p["lugares"]:
            por_lugar.setdefault(chave, {"nome": nome, "itens": {}})["itens"][p["id"]] = p
            for t in tp:
                por_tipo.setdefault((chave, t), {"nome": nome, "itens": {}})["itens"][p["id"]] = p
    rep = [(k, v) for k, v in por_tipo.items() if len(v["itens"]) >= 2]
    ids_rep = {}
    for (chave, _), v in rep:
        ids_rep.setdefault(chave, set()).update(v["itens"])
    mesmo = []
    for chave, v in por_lugar.items():
        if len(v["itens"]) >= 2 and set(v["itens"]) - ids_rep.get(chave, set()):
            mesmo.append((chave, v))
    return rep, mesmo
