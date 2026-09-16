"""Cruzar a rubrica do LLM com o resultado medido -- Fase 5.

O proposito declarado da fase, na secao 9: *"Coletar retencao e views de cada
publicacao, cruzar com a rubrica que o LLM deu, ajustar os pesos. Aqui e onde o
projeto deixa de ser um clone e vira algo que so voce tem."*

As duas pontas ja existem. O `predicted_score` que o modelo deu a cada corte
esta em `clips.score` desde o bloco 3.3, com a rubrica inteira em `rubric_json`;
as views e a retencao entram em `metrics` desde o bloco 5.1. Falta a subtracao.

### A regra que este modulo existe para respeitar

**Com poucos cortes, nao ha correlacao -- ha ruido com um numero em cima.**

E a tentacao obvia: somar cinco clipes, calcular um coeficiente, e anunciar que
a rubrica funciona (ou nao). Um rho de 0,7 com n=5 acontece por acaso com
frequencia alta, e uma vez escrito num relatorio ele vira a razao de alguem
mexer nos pesos. O projeto inteiro vem recusando esse movimento -- o ADR-006 se
recusou a virar um numero nao sabido em constante, o pre-filtro corta por
orcamento e nao por qualidade, o `layout_picker` pede decisao entre opcoes
fechadas em vez de medida continua.

Entao: abaixo de `MINIMO_PARA_CORRELACAO` o relatorio **nao devolve
coeficiente**. Devolve os dados crus, a contagem, e a frase dizendo quantos
faltam. Isso e util (da para olhar), e um numero seria pior que nada.

### Spearman, e nao Pearson

A pergunta da fase e "o corte que o modelo achou melhor rendeu mais?" -- ou
seja, sobre ORDEM. Pearson mediria se a relacao e uma reta, o que ninguem
afirmou e nao interessa: um modelo que acerta o ranking inteiro mas comprime os
scores entre 70 e 85 teria Pearson baixo e seria exatamente o que queremos.

Stdlib pura: ranquear e somar quadrados. O CI roda a conta inteira.
"""
from __future__ import annotations

from typing import Iterable, Optional

#: Abaixo disto o relatorio nao publica coeficiente. Dez nao e um limiar
#: estatistico consagrado -- e o ponto em que olhar o numero deixa de ser
#: obviamente irresponsavel. A faixa entre 10 e 30 continua ganhando ressalva.
MINIMO_PARA_CORRELACAO = 10

#: Abaixo disto o coeficiente sai com aviso de amostra pequena junto.
AMOSTRA_CONFORTAVEL = 30

#: As faixas de `predicted_score` usadas para agrupar. Tres, e nao dez: com
#: dezenas de cortes, dez faixas teriam dois clipes cada e nenhuma diria nada.
FAIXAS = ((0, 60, "baixo"), (60, 80, "medio"), (80, 101, "alto"))


def _postos(valores: list) -> list:
    """Postos 1..n, com media nos empates -- que e o que Spearman pede.

    Sem tratar empate, tres cortes com score 80 receberiam postos 1, 2 e 3 numa
    ordem arbitraria, e o coeficiente passaria a medir a ordem de insercao no
    banco.
    """
    indexados = sorted(range(len(valores)), key=lambda i: valores[i])
    postos = [0.0] * len(valores)
    i = 0
    while i < len(indexados):
        j = i
        while j + 1 < len(indexados) and \
                valores[indexados[j + 1]] == valores[indexados[i]]:
            j += 1
        media = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            postos[indexados[k]] = media
        i = j + 1
    return postos


def spearman(pares: Iterable) -> Optional[float]:
    """Correlacao de posto entre dois conjuntos. None se nao der para calcular.

    Devolve None -- e nao zero -- quando a amostra e pequena demais ou quando
    um dos lados nao varia. Zero significaria "medimos e nao ha relacao", que e
    uma afirmacao; None significa "nao da para afirmar".
    """
    pares = [(a, b) for a, b in pares
             if a is not None and b is not None]
    n = len(pares)
    if n < MINIMO_PARA_CORRELACAO:
        return None
    xs = _postos([p[0] for p in pares])
    ys = _postos([p[1] for p in pares])
    mx = sum(xs) / n
    my = sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx == 0 or vy == 0:
        # Todo mundo com o mesmo score, ou com a mesma retencao. Nao ha ordem
        # para correlacionar, e devolver zero fingiria que ha.
        return None
    return round(cov / ((vx * vy) ** 0.5), 3)


def por_faixa(itens: Iterable) -> list:
    """Media de retencao e views por faixa de score previsto."""
    baldes = {rotulo: {"faixa": rotulo, "de": de, "ate": ate, "clipes": 0,
                       "retencao": [], "views": []}
              for de, ate, rotulo in FAIXAS}
    for item in itens:
        score = item.get("score")
        if score is None:
            continue
        for de, ate, rotulo in FAIXAS:
            if de <= score < ate:
                b = baldes[rotulo]
                b["clipes"] += 1
                if item.get("retention_pct") is not None:
                    b["retencao"].append(item["retention_pct"])
                if item.get("views") is not None:
                    b["views"].append(item["views"])
                break
    saida = []
    for _de, _ate, rotulo in FAIXAS:
        b = baldes[rotulo]
        saida.append({
            "faixa": rotulo, "de": b["de"], "ate": b["ate"],
            "clipes": b["clipes"],
            "retencao_media": (round(sum(b["retencao"]) / len(b["retencao"]), 1)
                               if b["retencao"] else None),
            "views_media": (round(sum(b["views"]) / len(b["views"]), 1)
                            if b["views"] else None),
        })
    return saida


def relatorio(itens: list) -> dict:
    """O cruzamento inteiro, com as ressalvas que a amostra exige."""
    medidos = [i for i in itens if i.get("retention_pct") is not None
               or i.get("views") is not None]
    com_retencao = [i for i in medidos if i.get("retention_pct") is not None
                    and i.get("score") is not None]
    com_views = [i for i in medidos if i.get("views") is not None
                 and i.get("score") is not None]

    rho_retencao = spearman((i["score"], i["retention_pct"]) for i in com_retencao)
    rho_views = spearman((i["score"], i["views"]) for i in com_views)

    out = {
        "clipes_publicados": len(itens),
        "clipes_medidos": len(medidos),
        "com_retencao": len(com_retencao),
        "com_views": len(com_views),
        "minimo_para_correlacao": MINIMO_PARA_CORRELACAO,
        "rho_score_retencao": rho_retencao,
        "rho_score_views": rho_views,
        "por_faixa": por_faixa(medidos),
    }
    out["observacoes"] = observacoes(out)
    return out


def observacoes(r: dict) -> list:
    saida = []
    medidos = r.get("clipes_medidos", 0)

    if medidos == 0:
        saida.append(
            "Nenhum corte publicado foi medido ainda. O cruzamento comeca a "
            "existir depois da primeira coleta -- e ela precisa da credencial "
            "de leitura (`python youtube_oauth.py --leitura`).")
        return saida

    if r.get("com_retencao", 0) < MINIMO_PARA_CORRELACAO:
        faltam = MINIMO_PARA_CORRELACAO - r.get("com_retencao", 0)
        saida.append(
            f"{r['com_retencao']} corte(s) com retencao medida. Faltam {faltam} "
            f"para o relatorio publicar um coeficiente. **Nao e teimosia**: com "
            "poucos cortes, um rho alto acontece por acaso com frequencia -- e "
            "uma vez escrito, vira a razao de alguem mexer nos pesos.")
    else:
        rho = r.get("rho_score_retencao")
        if rho is None:
            saida.append(
                "Ha cortes suficientes, mas o score ou a retencao nao variam: "
                "sem ordem nao ha correlacao de posto a calcular.")
        else:
            direcao = ("acompanha" if rho > 0.3 else
                       "contraria" if rho < -0.3 else "nao acompanha")
            saida.append(
                f"rho = {rho:+.2f} entre o score do modelo e a retencao medida: "
                f"a ordem do modelo {direcao} a ordem do resultado.")
            if r.get("com_retencao", 0) < AMOSTRA_CONFORTAVEL:
                saida.append(
                    f"Amostra de {r['com_retencao']} -- suficiente para olhar, "
                    f"apertada para decidir. Com menos de {AMOSTRA_CONFORTAVEL} "
                    "o intervalo em torno desse rho ainda e largo.")

    faixas = [f for f in r.get("por_faixa") or [] if f["clipes"]]
    if len(faixas) >= 2 and all(f["retencao_media"] is not None for f in faixas):
        melhor = max(faixas, key=lambda f: f["retencao_media"])
        pior = min(faixas, key=lambda f: f["retencao_media"])
        if melhor is not pior:
            saida.append(
                f"Faixa '{melhor['faixa']}': {melhor['retencao_media']}% de "
                f"retencao media; faixa '{pior['faixa']}': "
                f"{pior['retencao_media']}%. E o dado que o ADR-006 espera para "
                "fechar o piso de score -- ele so vale quando a amostra por "
                "faixa parar de ser de um punhado de cortes.")
    return saida
