#!/usr/bin/env python3
"""Confere se a coleta veio completa e coerente. Se não, o robô não publica.

Uso:  python3 validar.py <dados_novos> [<dados_da_ultima_versao_boa>] [--forcar]

Sai com código 0 se pode publicar e 1 se não pode. Escreve o relatório na tela e,
no GitHub, no resumo da execução.

--forcar pula só a comparação com a versão anterior (queda ou salto grande nos
números). Os testes de coerência dos dados nunca são pulados.
"""
import datetime
import json
import os
import pathlib
import sys

AQUI = pathlib.Path(__file__).resolve().parent
CFG = json.loads((AQUI / "config.json").read_text(encoding="utf-8"))
LIMITES = {
    "vereadores_ativos_min": 5,
    "vereadores_ativos_max": 40,
    "propostas_vereador_min": 10,   # propostas com vereador como autor desde a data inicial
    "cobertura_presenca_min": 0.6,  # parte das sessões que precisa ter lista de presença
    "ementa_vazia_max": 0.2,        # parte das matérias que pode vir sem texto
    "queda_maxima": 0.02,           # quanto pode sumir em relação à versão anterior
    "crescimento_maximo": 0.25,     # quanto pode crescer de um dia para o outro (mais 30 itens)
}
LIMITES.update(CFG.get("validacao", {}))
ARQUIVOS = ["parlamentares", "sessoes", "materias", "presencas", "votacoes"]


def ler(pasta, nome):
    arq = pathlib.Path(pasta) / f"{nome}.json"
    if not arq.exists():
        raise ValueError(f"arquivo {nome}.json não existe")
    d = json.loads(arq.read_text(encoding="utf-8"))
    if not isinstance(d, list):
        raise ValueError(f"{nome}.json não é uma lista")
    return d


def validar(novos, atuais=None, forcar=False):
    """Devolve (falhas, avisos, passou). Cada item é um texto."""
    falhas, avisos, passou = [], [], []
    L = LIMITES

    def teste(cond, ok, erro):
        (passou if cond else falhas).append(ok if cond else erro)
        return cond

    dados = {}
    for nome in ARQUIVOS:
        try:
            dados[nome] = ler(novos, nome)
        except (ValueError, OSError) as ex:
            falhas.append(f"{nome}: {ex}")
    if falhas:
        return falhas, avisos, passou
    for nome in ARQUIVOS:
        teste(len(dados[nome]) > 0, f"{nome}: {len(dados[nome])} registros",
              f"{nome}: veio vazio (a coleta desse dado não funcionou)")
    if falhas:
        return falhas, avisos, passou

    parl, sess, mats, pres, vots = (dados[n] for n in ARQUIVOS)
    desde = CFG.get("desde", "0000-00-00")
    hoje = datetime.date.today().isoformat()
    amanha = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()

    # --- vereadores
    ativos = [p for p in parl if p.get("ativo")]
    teste(L["vereadores_ativos_min"] <= len(ativos) <= L["vereadores_ativos_max"],
          f"vereadores ativos: {len(ativos)}",
          f"vereadores ativos: {len(ativos)} (esperado entre {L['vereadores_ativos_min']} e {L['vereadores_ativos_max']})")
    ids_parl = {p["id"] for p in parl}
    teste(len(ids_parl) == len(parl), "ids de vereadores sem repetição", "há ids de vereadores repetidos")

    # --- sessões
    ids_sess = [s["id"] for s in sess]
    teste(len(set(ids_sess)) == len(ids_sess), f"sessões: {len(sess)}, sem repetição", "há ids de sessões repetidos")
    datas_ruins = [s["id"] for s in sess if not (desde <= s.get("data", "") <= amanha)]
    teste(not datas_ruins, "datas das sessões dentro do período", f"sessões com data fora do período: {datas_ruins[:5]}")

    # --- presença
    sess_com_pres = {r["sessao"] for r in pres}
    cobertura = len(sess_com_pres & set(ids_sess)) / max(1, len(ids_sess))
    teste(cobertura >= L["cobertura_presenca_min"],
          f"presença registrada em {cobertura:.0%} das sessões",
          f"presença registrada em só {cobertura:.0%} das sessões (mínimo {L['cobertura_presenca_min']:.0%})")
    desconhecidos = [r for r in pres if r["parlamentar"] not in ids_parl or r["sessao"] not in set(ids_sess)]
    teste(not desconhecidos, "toda presença aponta para sessão e vereador conhecidos",
          f"{len(desconhecidos)} presenças apontam para sessão ou vereador desconhecido")
    por_sessao = {}
    for r in pres:
        por_sessao.setdefault(r["sessao"], set()).add(r["parlamentar"])
    cheias = [s for s, v in por_sessao.items() if len(v) > L["vereadores_ativos_max"]]
    teste(not cheias, "nenhuma sessão com mais presentes que o possível", f"sessões com presentes demais: {cheias[:5]}")

    # --- votações
    votos_ruins = [v["id"] for v in vots if not (2 <= len(v["votos"]) <= L["vereadores_ativos_max"])]
    teste(not votos_ruins, f"votações nominais: {len(vots)}, cada uma com número de votos possível",
          f"votações com número de votos impossível: {votos_ruins[:5]}")
    votantes_desconhecidos = [v["id"] for v in vots if any(int(k) not in ids_parl for k in v["votos"])]
    teste(not votantes_desconhecidos, "todo voto é de vereador conhecido",
          f"votações com voto de quem não é vereador conhecido: {votantes_desconhecidos[:5]}")
    sem_sessao = [v["id"] for v in vots if v["sessao"] not in set(ids_sess)]
    teste(not sem_sessao, "toda votação aponta para uma sessão conhecida", f"votações sem sessão conhecida: {sem_sessao[:5]}")

    # --- matérias e propostas
    com_vereador = [m for m in mats if any(a in ids_parl for a in m.get("autores", []))]
    teste(len(com_vereador) >= L["propostas_vereador_min"],
          f"matérias: {len(mats)}, das quais {len(com_vereador)} com vereador como autor",
          f"só {len(com_vereador)} matérias têm vereador como autor (mínimo {L['propostas_vereador_min']}). "
          f"A ligação entre autor e vereador provavelmente falhou")
    vazias = sum(1 for m in mats if not (m.get("ementa") or "").strip())
    teste(vazias / len(mats) <= L["ementa_vazia_max"], f"matérias sem texto: {vazias}",
          f"{vazias} de {len(mats)} matérias vieram sem texto")
    teste(len({m["id"] for m in mats}) == len(mats), "ids de matérias sem repetição", "há ids de matérias repetidos")
    datas_futuras = [m["id"] for m in mats if m.get("data", "") > amanha]
    teste(not datas_futuras, "nenhuma matéria com data no futuro", f"matérias com data no futuro: {datas_futuras[:5]}")

    # --- aviso: vereador ativo sem nenhuma presença
    if len(sess_com_pres) >= 5:
        sem_pres = [p["nome"] for p in ativos if not any(p["id"] in v for v in por_sessao.values())]
        if sem_pres:
            avisos.append(f"vereadores ativos sem nenhuma presença no período: {sem_pres}")

    # --- comparação com a última versão boa
    if atuais and pathlib.Path(atuais, "sessoes.json").exists():
        def chave(nome, r):
            return (r["sessao"], r["parlamentar"]) if nome == "presencas" else r["id"]
        for nome in ARQUIVOS:
            try:
                antigo = {chave(nome, r) for r in ler(atuais, nome)}
            except (ValueError, OSError):
                continue
            novo = {chave(nome, r) for r in dados[nome]}
            sumiram = len(antigo - novo)
            queda = sumiram / max(1, len(antigo))
            cresc = len(novo) > len(antigo) * (1 + L["crescimento_maximo"]) + 30
            msg = f"{nome}: {len(antigo)} antes, {len(novo)} agora, {sumiram} sumiram"
            if queda > L["queda_maxima"] or cresc:
                motivo = "sumiu mais do que o permitido" if queda > L["queda_maxima"] else "cresceu mais do que o permitido em um dia"
                if forcar:
                    avisos.append(f"{msg} ({motivo}; aceito por --forcar)")
                else:
                    falhas.append(f"{msg}: {motivo}")
            else:
                passou.append(msg)
    else:
        avisos.append("não há versão anterior para comparar (primeira rodada)")
    return falhas, avisos, passou


def main(argv):
    forcar = "--forcar" in argv
    pos = [a for a in argv if not a.startswith("--")]
    if not pos:
        print(__doc__)
        return 2
    falhas, avisos, passou = validar(pos[0], pos[1] if len(pos) > 1 else None, forcar)
    linhas = ["# Verificação dos dados", ""]
    linhas += [f"✔ {t}" for t in passou] + [f"⚠ {t}" for t in avisos] + [f"✘ {t}" for t in falhas]
    linhas += ["", "RESULTADO: " + ("NÃO PUBLICAR. O site fica com a última versão boa." if falhas else "pode publicar.")]
    texto = "\n".join(linhas)
    print(texto)
    resumo = os.environ.get("GITHUB_STEP_SUMMARY")
    if resumo:
        with open(resumo, "a", encoding="utf-8") as f:
            f.write(texto.replace("\n", "  \n") + "\n")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
