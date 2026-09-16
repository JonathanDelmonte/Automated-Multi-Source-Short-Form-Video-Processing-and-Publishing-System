"""O laco de cortes inteiro fica DENTRO do estagio medido (16-set-2026).

Le a arvore sintatica do `main.py`, como os testes que guardam o import do
`ultralytics` e o `asyncio.run` fora do executor. O motivo e o mesmo: o defeito
nao aparece em teste de comportamento, so numa medicao que ninguem confere.

Ate 16-set-2026 o `with job_metrics.stage("05_06_render")` fechava logo depois
do `render_clip`. Tudo o que vem DEPOIS -- marca d'agua, hook grounding (uma
chamada de LLM por corte), gancho e legenda, cada um um encode inteiro do
clipe -- rodava fora de estagio nenhum. O tempo deles ia para o
`fora_de_estagio_seconds` do relatorio, que ao mesmo tempo estava zerado por um
`max(0, ...)` engolindo a parede inflada do render paralelo: as duas falhas se
cancelavam e o numero saia plausivel e errado.
"""
import ast
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Os passes da cadeia de um corte. Cada um custa um encode inteiro do clipe
#: (menos o hook grounding, que custa uma chamada de LLM), e nenhum pode ficar
#: fora da medicao.
PASSES_DO_CORTE = ("cut_clip", "render_clip", "apply_watermark",
                   "reground", "auto_hook_clip", "auto_caption_clip")


def _arvore():
    """O `main.py` inteiro. O pipeline nao mora numa `def main()`: e o corpo do
    `if __name__ == "__main__"`, que e o que faz dele um subprocesso por job."""
    with open(os.path.join(RAIZ, "main.py"), encoding="utf-8") as fh:
        return ast.parse(fh.read())


def _funcao(nome):
    for no in ast.walk(_arvore()):
        if isinstance(no, ast.FunctionDef) and no.name == nome:
            return no
    raise AssertionError(f"{nome} sumiu do main.py")


def _e_medicao(no):
    """`with job_metrics.stage(...)` ou `job_metrics.substage(...)`."""
    if not isinstance(no, ast.With):
        return False
    for item in no.items:
        texto = ast.unparse(item.context_expr)
        if texto.startswith("job_metrics.stage(") or \
           texto.startswith("job_metrics.substage("):
            return True
    return False


def _chamadas_fora_da_medicao(no, medido=False):
    """Os nomes chamados neste no que NAO estao sob um `with` de medicao."""
    soltas = []
    for filho in ast.iter_child_nodes(no):
        dentro = medido or _e_medicao(filho)
        if isinstance(filho, ast.Call):
            alvo = filho.func
            nome = (alvo.attr if isinstance(alvo, ast.Attribute)
                    else getattr(alvo, "id", None))
            if nome in PASSES_DO_CORTE and not dentro:
                soltas.append(nome)
        soltas += _chamadas_fora_da_medicao(filho, dentro)
    return soltas


def test_todo_passe_do_corte_esta_dentro_de_um_estagio():
    soltas = _chamadas_fora_da_medicao(_funcao("_process_one_clip"))
    assert not soltas, (
        "estes passes do corte rodam fora de qualquer medicao e somem do "
        f"relatorio: {sorted(set(soltas))}")


def test_o_estagio_do_render_usa_o_nome_que_a_barra_conhece():
    """`app._stage_view` devolve `stage_index` 0 para um nome que nao esteja em
    `PIPELINE_STAGES` -- ou seja, a barra volta ao inicio. E por isso que a
    medicao fina usa `substage`, que nao anuncia."""
    import app
    nomes_da_barra = {n for n, _ in app.PIPELINE_STAGES}
    anunciados = set()
    for no in ast.walk(_arvore()):
        if isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute) \
                and no.func.attr == "stage" \
                and ast.unparse(no.func).startswith("job_metrics"):
            if no.args and isinstance(no.args[0], ast.Constant):
                anunciados.add(no.args[0].value)
    assert anunciados, "o main.py deixou de abrir estagio nenhum"
    assert anunciados <= nomes_da_barra, (
        f"estes nomes movem a barra para um estagio que ela nao conhece: "
        f"{sorted(anunciados - nomes_da_barra)}")


def test_os_substages_do_render_sao_os_que_o_relatorio_ordena():
    """Um substage com nome fora de `ORDEM_DOS_SUBESTAGIOS` ainda aparece no
    relatorio, so que jogado para o fim da lista -- deixa de ser lido na ordem
    em que o corte acontece, que e o unico jeito de ver onde ele engasga."""
    import timings_report
    usados = set()
    for no in ast.walk(_arvore()):
        if isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute) \
                and no.func.attr == "substage":
            if no.args and isinstance(no.args[0], ast.Constant):
                usados.add(no.args[0].value)
    assert usados, "o laco de cortes deixou de medir por dentro"
    faltando = usados - set(timings_report.ORDEM_DOS_SUBESTAGIOS)
    assert not faltando, (
        f"substages sem lugar na ordem do relatorio: {sorted(faltando)}")
