#!/usr/bin/env python3
"""Prova que a verificação deixa passar dados bons e bloqueia dados ruins.
Usa dados inventados (nada real). Rode:  python3 testes/teste_validar.py"""
import copy
import json
import pathlib
import shutil
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import validar  # noqa: E402


def base():
    parl = [dict(id=i, nome=f"Vereador {i}", ativo=True, partido=None) for i in range(1, 14)]
    sess = [dict(id=100 + i, data=f"2026-{1 + i // 4:02d}-{1 + (i % 4) * 7:02d}", titulo=f"Sessão {i}", tipo=1, url_ata=None) for i in range(12)]
    pres = [dict(sessao=s["id"], parlamentar=p["id"]) for s in sess for p in parl]
    vots = [dict(id=n, sessao=sess[n]["id"], titulo=f"Votação {n}", resultado="Aprovado",
                 votos={str(p["id"]): "Sim" for p in parl}) for n in range(8)]
    mats = [dict(id=1000 + n, tipo="Requerimento", numero=n, ano=2026, ementa=f"Pede informações número {n}.",
                 data="2026-02-02", autores=[1 + n % 13]) for n in range(60)]
    return dict(parlamentares=parl, sessoes=sess, materias=mats, presencas=pres, votacoes=vots)


def gravar(dados, pasta, omitir=()):
    pasta = pathlib.Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    for nome, conteudo in dados.items():
        if nome not in omitir:
            (pasta / f"{nome}.json").write_text(json.dumps(conteudo), encoding="utf-8")


def rodar(nome, esperado_passa, mudar=None, anterior=True, forcar=False, omitir=(), quebrar=None):
    tmp = pathlib.Path(tempfile.mkdtemp())
    try:
        velho, novo = base(), base()
        if mudar:
            mudar(novo)
        gravar(velho, tmp / "atual")
        gravar(novo, tmp / "novo", omitir)
        if quebrar:
            (tmp / "novo" / f"{quebrar}.json").write_text("{isto não é json", encoding="utf-8")
        try:
            falhas, avisos, _ = validar.validar(tmp / "novo", tmp / "atual" if anterior else None, forcar)
        except Exception as ex:  # noqa: BLE001
            falhas, avisos = [f"quebrou: {ex}"], []
        passou = not falhas
        ok = passou == esperado_passa
        print(f"{'ok ' if ok else 'ERRO'}  {nome}: {'publica' if passou else 'BLOQUEIA'}"
              + (f"  ({falhas[0][:90]})" if falhas else ""))
        return ok
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def esvaziar(chave):
    return lambda d: d.__setitem__(chave, [])


def poucos_vereadores(d):
    for p in d["parlamentares"][3:]:
        p["ativo"] = False


def cortar_materias(d):
    d["materias"] = d["materias"][:20]


def dobrar_materias(d):
    d["materias"] += [dict(m, id=m["id"] + 5000) for m in d["materias"]] * 2


def autores_soltos(d):
    for m in d["materias"]:
        m["autores"] = []


def voto_de_estranho(d):
    d["votacoes"][0]["votos"]["999"] = "Sim"


def sessoes_no_futuro(d):
    d["sessoes"][0]["data"] = "2999-01-01"


def crescer_pouco(d):
    d["materias"] += [dict(id=9000 + n, tipo="Requerimento", numero=n, ano=2026, ementa="Novo.", data="2026-03-03", autores=[1]) for n in range(3)]


def sem_texto(d):
    for m in d["materias"][:30]:
        m["ementa"] = ""


resultados = [
    rodar("dados bons, primeira rodada", True, anterior=False),
    rodar("dados bons, poucos itens novos", True, crescer_pouco),
    rodar("presença veio vazia", False, esvaziar("presencas")),
    rodar("votações vieram vazias", False, esvaziar("votacoes")),
    rodar("só 3 vereadores ativos", False, poucos_vereadores),
    rodar("matérias caíram de 60 para 20", False, cortar_materias),
    rodar("matérias quadruplicaram", False, dobrar_materias),
    rodar("autores não ligados a vereadores", False, autores_soltos, anterior=False),
    rodar("voto de quem não é vereador", False, voto_de_estranho),
    rodar("sessão com data em 2999", False, sessoes_no_futuro),
    rodar("metade das matérias sem texto", False, sem_texto),
    rodar("arquivo de votações ausente", False, omitir=("votacoes",)),
    rodar("arquivo de matérias quebrado", False, quebrar="materias"),
    rodar("--forcar aceita queda grande", True, cortar_materias, forcar=True),
    rodar("--forcar não aceita presença vazia", False, esvaziar("presencas"), forcar=True),
]
print(f"\n{sum(resultados)} de {len(resultados)} testes como esperado")
sys.exit(0 if all(resultados) else 1)
