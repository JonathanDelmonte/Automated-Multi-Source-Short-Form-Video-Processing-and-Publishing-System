"""yt-dlp client selection for YouTube, shared by the download (``main.py``)
and the duration probe (``quality_probe.py``) so the two cannot drift.

Why the AUTHENTICATED list is explicit. With account cookies yt-dlp's defaults
are ``tv_downgraded`` + ``web``, and for a share of videos both come back
UNPLAYABLE / SABR-only, which surfaces as "Video unavailable" with no
formats. That looked like an IP ban (it also happened on every static ISP IP)
and for a week sent ~26 downloads a week to the per-GB proxy, which then
downloaded 360p through the same dead client list. Measured on 6-sep-2026
inside the prod container, same static proxy, same video:

    cookies + default clients            -> Video unavailable
    cookies + mweb (+ PO token)          -> 1080p
    no cookies + default clients         -> 1080p
    cookies + default,mweb (+ PO token)  -> 1080p (also on a video that worked)

``mweb`` needs a GVS PO token for its https formats, which the bgutil
provider mints as long as the webpage is NOT skipped (``player_skip:
webpage`` drops the account's Data Sync ID and the token request fails).
The old fallback list (``tv_embed``, ``android``) is gone from yt-dlp: the
first is "unsupported", the second is skipped whenever cookies are present.

Por que existe uma lista ANONIMA, separada (22-set-2026). A linha
"no cookies + default clients -> 1080p" acima expirou, e o dia em que ela
expirou o download parou de funcionar sem cookies -- em casa, num IP
residencial, num link colado no painel. O log diz o que aconteceu:

    visionos player response playability status: LOGIN_REQUIRED
    web      player response playability status: LOGIN_REQUIRED
    mweb     player response playability status: LOGIN_REQUIRED
    ERROR: Sign in to confirm you're not a bot.

Os tres sao a lista de cima aplicada sem cookies: `default` hoje e
``('visionos', 'web')`` (yt-dlp ``_DEFAULT_CLIENTS``) e o ``mweb`` e nosso.
Ou seja, a lista medida PARA A CONTA estava sendo imposta ao caso sem conta,
e nela nao sobrou nenhum cliente que o YouTube ainda sirva anonimamente.

``tv`` (TVHTML5, o cliente do Cobalt) e o que sobra: na tabela do proprio
yt-dlp ele e o unico que nao exige autenticacao NEM PO token -- nem GVS nem
player -- e ainda aceita cookies caso um dia existam. Ele pede o player JS,
que o Deno da imagem resolve. Por isso a lista anonima comeca nele e so
depois cai no ``default``.

**O PO token nao era a causa, e vale registrar para nao gastar um rebuild
com isso.** No mesmo log o provedor ``bgutil:script-node`` aparece como
indisponivel (o Node do Debian e 20.19.2 e o bgutil 2.0.0 pede >= 22), mas o
``bgutil:script-deno`` aparece DISPONIVEL e tem preferencia maior -- e mesmo
assim nenhum token foi pedido, porque o LOGIN_REQUIRED acontece antes de
existir formato para assinar. Subir o Node arrumaria um aviso, nao o
download.

As duas listas sao sobrescreviveis por ambiente (``YT_CLIENTS_AUTH`` e
``YT_CLIENTS_ANON``, separadas por virgula) de proposito: quem decide qual
cliente o YouTube ainda serve e o YouTube, e a resposta muda sem aviso. Com
o repositorio montado em ``/app``, trocar a lista e editar o ``.env`` e
reiniciar o backend -- segundos --, em vez de reconstruir a imagem.
``python diagnostico_youtube.py <url>`` mede qual lista passa hoje.
"""
import os

# Com cookies de conta (medido 6-set-2026, ver acima).
HD_CLIENTS = ["default", "mweb"]

# Sem cookies. O `tv` primeiro por ser o unico sem exigencia de PO token nem
# de autenticacao; o `default` atras dele para herdar a escolha do yt-dlp
# quando ela voltar a passar.
ANON_CLIENTS = ["tv", "default"]


def _do_ambiente(nome):
    """A lista posta em ``nome``, ou None. Item vazio e descartado."""
    bruto = os.environ.get(nome, "")
    itens = [p.strip() for p in bruto.split(",") if p.strip()]
    return itens or None


def clients_for(cookies):
    """A lista de ``player_client`` para uma tentativa que leva (ou nao) cookies.

    Sempre uma copia: a lista vai dentro de um dict de ``extractor_args`` que
    o yt-dlp pode consumir, e um `append` do chamador nao pode contaminar a
    proxima tentativa (ha teste)."""
    if cookies:
        return _do_ambiente("YT_CLIENTS_AUTH") or list(HD_CLIENTS)
    return _do_ambiente("YT_CLIENTS_ANON") or list(ANON_CLIENTS)


def pot_provider_args(bgutil_http, bgutil_script):
    """Extractor args selecting the PO token provider (bgutil http or script)."""
    if bgutil_http:
        return {"youtubepot-bgutilhttp": {"base_url": [bgutil_http]}}
    if bgutil_script:
        return {"youtubepot-bgutilscript": {"script_path": [bgutil_script]}}
    return {}


def hd_extractor_args(bgutil_http, bgutil_script, cookies=True):
    """Extractor args for the HD attempt, or None when the attempt cannot work.

    Com cookies a lista e a do ``mweb``, que exige PO token: sem provedor
    configurado nao ha caminho HD e o plano pula a tentativa. **Sem cookies
    nao ha essa exigencia** -- o ``tv`` nao pede token nenhum --, entao a
    tentativa existe mesmo numa instalacao sem bgutil."""
    provider = pot_provider_args(bgutil_http, bgutil_script)
    if not provider and cookies:
        return None
    return {**provider, "youtube": {"player_client": clients_for(cookies)}}


def fallback_extractor_args(bgutil_http, bgutil_script, cookies=True):
    """Extractor args for the conservative attempt: the client list for this
    attempt's cookie state, the provider when there is one, and never
    ``player_skip`` (see module docstring). Without a provider mweb still
    serves the progressive 360p format, which is enough for a probe and
    better than no download."""
    return {**pot_provider_args(bgutil_http, bgutil_script),
            "youtube": {"player_client": clients_for(cookies)}}


def args_da_tentativa(label, envia_cookies, tem_jar, bgutil_http, bgutil_script):
    """Os extractor args de UMA tentativa do plano de download.

    Mora aqui, e nao no `main.py`, porque e a regra e nao o encanamento: o
    `main.py` precisa de torch e do resto da pilha para ser importado, e esta
    decisao tem de ser exercitavel no CI, que de proposito nao os instala.

    `envia_cookies` e a INTENCAO da tentativa (o plano manda a fallback sair
    anonima quando houve uma HD antes); `tem_jar` e se existe jar em disco.
    Sem jar a tentativa sai anonima de qualquer jeito, e e o que de fato
    acontece -- nao o que se pretendia -- que escolhe a lista de clientes.
    """
    com_cookies = bool(envia_cookies and tem_jar)
    monta = (fallback_extractor_args if str(label).startswith("fallback")
             else hd_extractor_args)
    return monta(bgutil_http, bgutil_script, cookies=com_cookies)
