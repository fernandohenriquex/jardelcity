#!/usr/bin/env python3
"""Baixa os dados da Câmara pela API do SAPL e salva em dados/*.json.

Uso:
  python3 coletar.py --explorar   mostra os campos reais da API e salva explorar.txt
  python3 coletar.py              baixa tudo e salva em dados/

Só usa a biblioteca padrão do Python. Precisa de internet.

Os blocos marcados [A CONFIRMAR] usam nomes de campo que ainda não foram vistos
numa resposta real da API. Rode --explorar e confira antes de confiar neles.
"""
import json
import os
import pathlib
import sys
import time
import unicodedata
import urllib.parse
import urllib.request

AQUI = pathlib.Path(__file__).resolve().parent
CFG = json.loads((AQUI / "config.json").read_text(encoding="utf-8"))
BASE = os.environ.get("RADAR_SAPL_URL", CFG["sapl_url"]).rstrip("/")
DESDE = CFG.get("desde", "0000-00-00")
SAIDA = pathlib.Path(os.environ.get("RADAR_DADOS", AQUI / "dados"))
PAUSA = float(os.environ.get("RADAR_PAUSA", "0.4"))  # segundos entre pedidos, para não sobrecarregar o servidor

# Endereços. Os três primeiros foram vistos numa resposta real; os demais [A CONFIRMAR].
EP = {
    "parlamentar": "/api/parlamentares/parlamentar/",
    "sessao": "/api/sessao/sessaoplenaria/",
    "materia": "/api/materia/materialegislativa/",
    "autor": "/api/base/autor/",                                  # [A CONFIRMAR]
    "presenca": "/api/sessao/sessaoplenariapresenca/",            # [A CONFIRMAR]
    "votacao": "/api/sessao/registrovotacao/",                    # [A CONFIRMAR]
    "voto": "/api/sessao/votoparlamentar/",                       # [A CONFIRMAR]
    "ordemdia": "/api/sessao/ordemdia/",                          # [A CONFIRMAR]
    "expediente": "/api/sessao/expedientemateria/",               # [A CONFIRMAR]
    "resultado": "/api/sessao/tiporesultadovotacao/",             # [A CONFIRMAR]
    "filiacao": "/api/parlamentares/filiacao/",                   # [A CONFIRMAR]
    "partido": "/api/parlamentares/partido/",                     # [A CONFIRMAR]
}


def norm(s):
    s = unicodedata.normalize("NFD", str(s))
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower().strip()


def https(u):
    """A API devolve endereços com http://. Se o site é https, usa https."""
    if BASE.startswith("https://") and isinstance(u, str) and u.startswith("http://"):
        return "https://" + u[len("http://"):]
    return u


def get(url, tentativas=4):
    ultimo = None
    for i in range(tentativas):
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "radar-camara/1.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except Exception as ex:  # noqa: BLE001
            ultimo = ex
            time.sleep(2 ** i)
    raise RuntimeError(f"falhou: {url} ({ultimo})")


def baixar(chave, **filtros):
    """Baixa todas as páginas de um endereço. A API devolve {pagination:{links:{next}}, results:[...]}."""
    q = {"page_size": 100, **filtros}
    url = f"{BASE}{EP[chave]}?{urllib.parse.urlencode(q)}"
    itens, pag = [], 0
    while url:
        d = get(url)
        if isinstance(d, list):  # endereço sem paginação
            return d
        itens += d["results"]
        pag += 1
        url = https(d["pagination"]["links"]["next"])
        if pag % 10 == 0:
            print(f"   {chave}: {len(itens)} de {d['pagination'].get('total_entries', '?')}", flush=True)
        time.sleep(PAUSA)
    return itens


CAMPOS_PESSOAIS = {"ip", "user", "email", "telefone", "telefone_celular", "fotografia", "cropping", "endereco_web", "numero_gab_parlamentar"}


def sem_dados_pessoais(rec):
    return {k: v for k, v in rec.items() if k not in CAMPOS_PESSOAIS} if isinstance(rec, dict) else rec


def pegar(rec, *nomes, padrao=None):
    """Primeiro campo que existir no registro."""
    for n in nomes:
        if n in rec and rec[n] is not None:
            return rec[n]
    return padrao


# ------------------------------------------------------------- explorar
def explorar():
    linhas = [f"Endereço base: {BASE}", ""]
    for caminho in ("/api/schema/?format=json", "/api/schema/"):
        try:
            req = urllib.request.Request(BASE + caminho, headers={"Accept": "application/vnd.oai.openapi+json, application/json"})
            with urllib.request.urlopen(req, timeout=60) as r:
                corpo = r.read().decode("utf-8", "replace")
            try:
                caminhos = sorted(json.loads(corpo).get("paths", {}))
                linhas.append(f"Esquema OpenAPI em {caminho}: {len(caminhos)} caminhos")
                linhas += [f"  {c}" for c in caminhos if c.startswith("/api/") and ("{" not in c)]
            except ValueError:
                linhas.append(f"Esquema em {caminho} não é JSON. Início: {corpo[:300]!r}")
            break
        except Exception as ex:  # noqa: BLE001
            linhas.append(f"{caminho}: {ex}")
    linhas.append("")
    for chave, caminho in EP.items():
        try:
            d = get(f"{BASE}{caminho}?page_size=2")
            regs = d["results"] if isinstance(d, dict) and "results" in d else d
            total = d.get("pagination", {}).get("total_entries", "?") if isinstance(d, dict) else len(regs)
            linhas.append(f"== {chave}  {caminho}  (total: {total})")
            if regs:
                linhas.append(json.dumps(sem_dados_pessoais(regs[0]), ensure_ascii=False)[:1500])
        except Exception as ex:  # noqa: BLE001
            linhas.append(f"== {chave}  {caminho}  ERRO: {ex}")
        linhas.append("")
        time.sleep(PAUSA)
    texto = "\n".join(linhas)
    (AQUI / "explorar.txt").write_text(texto, encoding="utf-8")
    print(texto)
    print("\nSalvo em explorar.txt. Se algo deu ERRO ou faltou campo, mande este arquivo para ajustar.")


# ---------------------------------------------------------------- coletar
def tentar(chave, **filtros):
    try:
        return baixar(chave, **filtros)
    except Exception as ex:  # noqa: BLE001
        print(f"   AVISO: não consegui baixar '{chave}' ({EP[chave]}): {ex}")
        return None


def coletar():
    SAIDA.mkdir(parents=True, exist_ok=True)
    salvar = lambda nome, dados: (SAIDA / nome).write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    relatorio = []

    # 1) parlamentares (campos vistos numa resposta real)
    print("Parlamentares...")
    brutos = baixar("parlamentar")
    parl = {r["id"]: dict(id=r["id"], nome=r["nome_parlamentar"], ativo=bool(r.get("ativo")), partido=None) for r in brutos}
    # partido [A CONFIRMAR]: a lista de parlamentares não traz o partido
    filiacoes, partidos = tentar("filiacao"), tentar("partido")
    if filiacoes and partidos:
        sigla = {p["id"]: pegar(p, "sigla", "nome", padrao=str(p["id"])) for p in partidos}
        # filiação mais recente de cada parlamentar que ainda não terminou
        for f in sorted(filiacoes, key=lambda f: pegar(f, "data", padrao="")):
            pid = pegar(f, "parlamentar")
            if pid in parl and not pegar(f, "data_desfiliacao"):
                parl[pid]["partido"] = sigla.get(pegar(f, "partido"))
    salvar("parlamentares.json", list(parl.values()))
    relatorio.append(f"parlamentares: {len(parl)} ({sum(p['ativo'] for p in parl.values())} ativos, "
                     f"{sum(bool(p['partido']) for p in parl.values())} com partido)")

    # 2) sessões (campos vistos numa resposta real)
    print("Sessões...")
    sess_brutas = baixar("sessao")
    sessoes = [dict(id=r["id"], data=r["data_inicio"], titulo=r["__str__"], tipo=r.get("tipo"), url_ata=https(r.get("upload_ata")))
               for r in sess_brutas if r["data_inicio"] >= DESDE]
    ids_sessao = {s["id"] for s in sessoes}
    salvar("sessoes.json", sessoes)
    relatorio.append(f"sessões desde {DESDE}: {len(sessoes)} (de {len(sess_brutas)} no total)")

    # 3) autores [A CONFIRMAR] e matérias (campos de matéria vistos numa resposta real)
    print("Autores...")
    autores = tentar("autor") or []
    por_nome = {norm(p["nome"]): p["id"] for p in parl.values()}
    autor_para_parl = {}
    # 1) mesmo nome do vereador. 2) o tipo de autor desses é o "tipo vereador"; os demais autores
    # desse tipo são ligados pelo object_id. (object_id sozinho engana: comissões usam o mesmo campo.)
    tipos_vereador = set()
    for a in autores:
        alvo = por_nome.get(norm(pegar(a, "nome", padrao="")))
        if alvo is not None:
            autor_para_parl[a["id"]] = alvo
            tipos_vereador.add(pegar(a, "content_type"))
    for a in autores:
        if a["id"] not in autor_para_parl and pegar(a, "content_type") in tipos_vereador and pegar(a, "object_id") in parl:
            autor_para_parl[a["id"]] = a["object_id"]
    relatorio.append(f"autores ligados a vereadores: {len(autor_para_parl)} de {len(autores)}")

    print("Matérias (pode demorar alguns minutos)...")
    mats = baixar("materia")
    materias, sem_autor = [], 0
    for r in mats:
        data = r.get("data_apresentacao") or ""
        if data < DESDE:
            continue
        titulo = r["__str__"]
        tipo = titulo.split(" nº ")[0].strip()
        ids = [autor_para_parl[a] for a in r.get("autores", []) if a in autor_para_parl]
        sem_autor += not ids
        materias.append(dict(id=r["id"], tipo=tipo, numero=r.get("numero"), ano=r.get("ano"),
                             ementa=(r.get("ementa") or "").strip().strip('"“”'), data=data, autores=ids))
    salvar("materias.json", materias)
    relatorio.append(f"matérias desde {DESDE}: {len(materias)} ({sem_autor} sem vereador como autor)")

    # 4) presença [A CONFIRMAR]
    print("Presenças...")
    pres_brutas = tentar("presenca") or []
    presencas = []
    for r in pres_brutas:
        s = pegar(r, "sessao_plenaria", "sessao")
        p = pegar(r, "parlamentar")
        if s in ids_sessao and p in parl:
            presencas.append(dict(sessao=s, parlamentar=p))
    salvar("presencas.json", presencas)
    relatorio.append(f"presenças: {len(presencas)} registros em {len({x['sessao'] for x in presencas})} sessões")

    # 5) votações [A CONFIRMAR]
    print("Votações...")
    regs, votos_brutos = tentar("votacao") or [], tentar("voto") or []
    ordem = {r["id"]: pegar(r, "sessao_plenaria", "sessao") for r in (tentar("ordemdia") or [])}
    exped = {r["id"]: pegar(r, "sessao_plenaria", "sessao") for r in (tentar("expediente") or [])}
    res_nome = {r["id"]: pegar(r, "nome", padrao="") for r in (tentar("resultado") or [])}
    titulo_materia = {m["id"]: m["__str__"] for m in mats}
    votos_por = {}
    for v in votos_brutos:
        voto = norm(pegar(v, "voto", padrao=""))
        rotulo = {"sim": "Sim", "nao": "Não", "abstencao": "Abstenção"}.get(voto)
        if rotulo and pegar(v, "parlamentar") in parl:
            votos_por.setdefault(pegar(v, "votacao"), {})[pegar(v, "parlamentar")] = rotulo
    votacoes = []
    for r in regs:
        sessao = ordem.get(pegar(r, "ordem")) or exped.get(pegar(r, "expediente"))
        if sessao not in ids_sessao or r["id"] not in votos_por:
            continue
        res = pegar(r, "tipo_resultado_votacao")
        votacoes.append(dict(id=r["id"], sessao=sessao,
                             titulo=titulo_materia.get(pegar(r, "materia"), f"Votação nº {r['id']}"),
                             resultado=res_nome.get(res, str(res) if res else None),
                             votos={str(k): x for k, x in votos_por[r["id"]].items()}))
    salvar("votacoes.json", votacoes)
    relatorio.append(f"votações nominais: {len(votacoes)} (de {len(regs)} registros de votação)")

    print("\nResumo:")
    for linha in relatorio:
        print("  -", linha)
    print(f"\nArquivos em {SAIDA}. Agora rode:  python3 gerar.py")


if __name__ == "__main__":
    explorar() if "--explorar" in sys.argv else coletar()
