"""Qual lista de clientes o YouTube ainda serve HOJE, nesta maquina.

`python diagnostico_youtube.py <url-do-youtube>`

### Por que existe

A lista de `player_client` do `yt_clients.py` e a unica coisa do pipeline cuja
resposta certa muda sem ninguem mexer no codigo: quem decide e o YouTube. Em
6-set-2026 a medicao dizia "sem cookies, o padrao do yt-dlp devolve 1080p"; em
22-set-2026 o mesmo padrao devolveu LOGIN_REQUIRED e um job morreu com "sign in
to confirm you're not a bot" -- com o mesmo codigo, na mesma casa.

Quando isso acontecer de novo, a pergunta nao e "o que mudou no repositorio", e
sim "qual cliente passa agora". Este modulo responde por medicao, em um minuto,
sem reconstruir imagem: ele tenta cada lista candidata contra a URL que voce
der e diz a altura maxima que cada uma ofereceu.

### O que ele NAO faz

Nao baixa o video: so extrai a lista de formatos (`download=False`). E nao
muda nada sozinho -- imprime a linha de `.env` a por, porque trocar a lista
que todo download usa e decisao de quem esta olhando, nao efeito colateral de
um diagnostico.

### Separado de proposito

`conclusoes()` e funcao pura sobre a lista de resultados, entao o CI exercita
a leitura sem rede e sem yt-dlp. A rede mora em `medir()`, e so nela.
"""
import argparse
import os
import sys

# Candidatos em ordem de leitura, nao de preferencia. Sao os clientes que hoje
# nao exigem conta (`REQUIRE_AUTH` falso na tabela do yt-dlp); os que exigem
# ficam de fora porque sem cookies a resposta deles nao informa nada.
#
# `default` entra como candidato explicito porque e o que o yt-dlp escolheria
# sozinho -- quando ele voltar a passar, a lista anonima do `yt_clients` pode
# voltar a ser so ele.
CANDIDATOS = [
    ("tv", ["tv"]),
    ("default", ["default"]),
    ("tv+default", ["tv", "default"]),
    ("web_embedded", ["web_embedded"]),
    ("android_vr", ["android_vr"]),
    ("ios", ["ios"]),
    ("tv_simply", ["tv_simply"]),
    ("mweb", ["mweb"]),
]

# Um candidato que responde isto nao esta dizendo "cliente errado", esta
# dizendo "este IP/este cliente caiu no anti-bot". Vale separar no relatorio:
# a correcao de um e trocar de cliente, a do outro nao.
MARCAS_DE_BLOQUEIO = (
    "not a bot",
    "sign in to confirm",
    "login_required",
    "login required",
)


def _resumo_do_erro(err, limite=110):
    """Uma linha do erro, sem o rodape de "reporte este problema" do yt-dlp."""
    texto_err = str(err).replace("\n", " ").strip()
    for corte in (" Use --cookies-from-browser",
                  "; please report this issue",
                  " Please report this issue"):
        if corte in texto_err:
            texto_err = texto_err.split(corte)[0]
    texto_err = texto_err.removeprefix("ERROR: ").strip()
    if len(texto_err) > limite:
        texto_err = texto_err[:limite - 1] + "…"
    return texto_err


def e_bloqueio(mensagem):
    """O erro e o anti-bot do YouTube (e nao um problema do cliente pedido)?"""
    baixa = (mensagem or "").lower()
    return any(m in baixa for m in MARCAS_DE_BLOQUEIO)


def medir(url, clients, cookies_path=None, timeout=25):
    """Extrai os formatos de `url` com esta lista de clientes. So aqui ha rede.

    Devolve `{"altura": int, "erro": str|None}`. Nunca levanta: um candidato
    que falha e um resultado, nao uma interrupcao -- e o proximo candidato e
    justamente o que pode passar.
    """
    resultado = {"altura": 0, "erro": None}
    try:
        import yt_dlp
    except ImportError:
        resultado["erro"] = "yt-dlp nao esta instalado neste ambiente"
        return resultado

    class _Mudo:
        def debug(self, msg):
            pass

        def info(self, msg):
            pass

        def warning(self, msg):
            pass

        def error(self, msg):
            pass

    opts = {
        "quiet": True,
        "no_warnings": True,
        "logger": _Mudo(),
        "socket_timeout": timeout,
        "retries": 1,
        "nocheckcertificate": True,
        "cachedir": False,
        "cookiefile": cookies_path or None,
        "extractor_args": {"youtube": {"player_client": list(clients)}},
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as err:  # noqa: BLE001 - um candidato que falha e um dado
        resultado["erro"] = _resumo_do_erro(err)
        return resultado

    alturas = [
        f.get("height") or 0
        for f in (info.get("formats") or [])
        if f.get("vcodec", "none") != "none"
        and f.get("protocol") != "mhtml"
        and f.get("ext") != "mhtml"
    ]
    resultado["altura"] = max(alturas, default=0)
    if not resultado["altura"]:
        resultado["erro"] = "extraiu, mas sem nenhum formato de video"
    return resultado


def levantamento(url, cookies_path=None, candidatos=None):
    """Roda todos os candidatos. Lista de `(rotulo, clients, resultado)`."""
    saida = []
    for rotulo, clients in (candidatos or CANDIDATOS):
        saida.append((rotulo, clients, medir(url, clients, cookies_path)))
    return saida


def conclusoes(resultados, tem_cookies=False):
    """As frases que a medicao sustenta. Funcao pura -- o CI roda esta parte.

    A regra e a mesma do `diagnostico.py`: nao afirmar o que nao foi medido.
    Nenhum candidato passar NAO vira "o YouTube bloqueou voce" quando todos
    falharam por motivos diferentes; vira "nenhum passou, e aqui esta o que
    cada um respondeu".
    """
    passaram = [(r, c, res) for r, c, res in resultados if res["altura"] > 0]
    bloqueados = [r for r, _, res in resultados if e_bloqueio(res.get("erro"))]
    linhas = []

    if not resultados:
        return ["Nada foi medido."]

    if not passaram:
        if len(bloqueados) == len(resultados):
            linhas.append(
                "NENHUM candidato passou, e todos cairam no anti-bot do "
                "YouTube. "
                "Isso e sobre o IP desta maquina, nao sobre a lista de "
                "clientes: trocar a lista nao resolve. Os caminhos sao "
                "esperar, sair por outra rede, ou dar cookies de uma conta "
                "(YOUTUBE_COOKIES no .env, ou um cookies.txt na pasta).")
        else:
            linhas.append(
                "Nenhum candidato devolveu formato, e por motivos diferentes "
                "-- a tabela acima e a resposta de cada um. Sem um padrao "
                "comum nao da para dizer que a causa e o cliente escolhido.")
        return linhas

    melhor = max(passaram, key=lambda item: item[2]["altura"])
    rotulo, clients, res = melhor
    alvo = "YT_CLIENTS_AUTH" if tem_cookies else "YT_CLIENTS_ANON"
    linhas.append(
        f"Passaram {len(passaram)} de {len(resultados)}. A maior altura veio de "
        f"`{rotulo}` ({res['altura']}p).")

    import yt_clients
    em_uso = yt_clients.clients_for(bool(tem_cookies))
    if em_uso == list(clients):
        linhas.append(
            "E e exatamente a lista que o pipeline ja usa. Nao ha nada a "
            "mudar no .env.")
    elif em_uso and em_uso[0] == clients[0]:
        # A lista em uso tem mais nomes, mas o vencedor e o PRIMEIRO dela --
        # os outros so entram se ele falhar. Mandar encurtar a lista aqui
        # seria trocar uma reserva que nao custa nada por uma linha no .env.
        linhas.append(
            f"O pipeline ja tenta `{em_uso[0]}` primeiro (lista em uso: "
            f"`{','.join(em_uso)}`). Nao ha nada a mudar no .env.")
    else:
        linhas.append(
            f"O pipeline usa hoje `{','.join(em_uso)}`. Para trocar sem "
            f"reconstruir a imagem, ponha no .env e reinicie o backend:")
        linhas.append(f"    {alvo}={','.join(clients)}")

    if bloqueados:
        linhas.append(
            f"Caiu no anti-bot: {', '.join(bloqueados)}. Esperado -- sao os "
            f"clientes que o YouTube esta recusando sem conta agora.")
    return linhas


def texto(url, resultados, cookies_path=None):
    linhas = ["", "=" * 72, "  QUAL CLIENTE DO YOUTUBE AINDA PASSA", "=" * 72, ""]
    linhas.append(f"URL       {url}")
    linhas.append(f"cookies   {os.path.basename(cookies_path) if cookies_path else 'nenhum (anonimo)'}")
    try:
        import yt_dlp
        linhas.append(f"yt-dlp    {yt_dlp.version.__version__}")
    except ImportError:
        linhas.append("yt-dlp    nao instalado")
    linhas.append("")

    largura = max([len("candidato")] + [len(r) for r, _, _ in resultados])
    linhas.append(f"  {'candidato'.ljust(largura)}  altura  observacao")
    linhas.append(f"  {'-' * largura}  ------  {'-' * 44}")
    for rotulo, _clients, res in resultados:
        altura = f"{res['altura']}p" if res["altura"] else "-"
        linhas.append(f"  {rotulo.ljust(largura)}  {altura:<6}  {res['erro'] or 'ok'}")

    linhas.append("")
    linhas.append("CONCLUSAO")
    for frase in conclusoes(resultados, tem_cookies=bool(cookies_path)):
        linhas.append(f"  {frase}")
    linhas.append("")
    return "\n".join(linhas)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Mede qual lista de player_client do yt-dlp o YouTube "
                    "ainda serve nesta maquina.")
    parser.add_argument("url", help="uma URL de video do YouTube")
    parser.add_argument("--sem-cookies", action="store_true",
                        help="ignora o jar em disco e mede so o caminho anonimo")
    args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))

    cookies_path = None
    if not args.sem_cookies:
        try:
            import sources
            cookies_path = sources.jar_em_disco(args.url)
        except Exception:
            cookies_path = None

    print(texto(args.url, levantamento(args.url, cookies_path), cookies_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
