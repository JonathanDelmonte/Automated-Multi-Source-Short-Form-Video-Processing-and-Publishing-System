"""Pega o refresh token do seu canal, uma vez -- Fase 3, bloco 3.4.

    python youtube_oauth.py

Sem isto o driver `youtube-api` nao tem como funcionar: a API exige um token de
renovacao que so nasce de um consentimento no navegador, e nao ha jeito de
obte-lo por variavel de ambiente. Escrever o driver e deixar a pessoa
descobrindo sozinha como emitir o token seria entregar metade.

**Fluxo de loopback**, e nao o antigo `urn:ietf:wg:oauth:2.0:oob`: o Google
desativou o modo de copiar-e-colar o codigo. Este script sobe um servidor em
`localhost` por alguns segundos, so para receber o `?code=` de volta, e desliga.

**O escopo e `youtube.upload`, e so ele.** O `youtube` completo daria a este
token o poder de apagar videos do canal; para subir corte, upload basta. Se o
token vazar, a diferenca entre os dois escopos e a diferenca entre um video
indesejado e um canal vazio.

O que voce precisa antes (uma vez, no console do Google Cloud):

1. criar um projeto e habilitar a **YouTube Data API v3**;
2. em "Credenciais", criar um **ID do cliente OAuth** do tipo
   **Aplicativo de computador** (Desktop app);
3. copiar o Client ID e o Client Secret.

O script grava em `vault://local/youtube/<handle>` com permissao 0600. Para usar
variaveis de ambiente em vez de arquivo, ele imprime as tres linhas prontas.
"""
from __future__ import annotations

import argparse
import http.server
import json
import os
import socket
import sys
import threading
import urllib.parse

import vault

AUTORIZACAO = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN = "https://oauth2.googleapis.com/token"
ESCOPO = "https://www.googleapis.com/auth/youtube.upload"


class _Receptor(http.server.BaseHTTPRequestHandler):
    """Recebe o `?code=` e some. Nao serve mais nada."""

    codigo = None
    erro = None

    def do_GET(self):  # noqa: N802  (assinatura do http.server)
        consulta = urllib.parse.urlparse(self.path).query
        campos = urllib.parse.parse_qs(consulta)
        _Receptor.codigo = (campos.get("code") or [None])[0]
        _Receptor.erro = (campos.get("error") or [None])[0]
        corpo = ("Pode fechar esta aba e voltar ao terminal."
                 if _Receptor.codigo else
                 f"Nao deu certo: {_Receptor.erro or 'sem codigo'}")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(corpo.encode("utf-8"))

    def log_message(self, *a):
        pass                      # o log do http.server aqui so polui o terminal


def _porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _esperar_codigo(porta: int, segundos: int = 300):
    servidor = http.server.HTTPServer(("127.0.0.1", porta), _Receptor)
    servidor.timeout = segundos
    thread = threading.Thread(target=servidor.handle_request, daemon=True)
    thread.start()
    thread.join(segundos)
    servidor.server_close()
    return _Receptor.codigo, _Receptor.erro


def _trocar_por_token(client_id: str, client_secret: str, codigo: str,
                      redirect_uri: str) -> dict:
    import httpx

    resposta = httpx.post(TOKEN, timeout=60.0, data={
        "client_id": client_id,
        "client_secret": client_secret,
        "code": codigo,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
    })
    if resposta.status_code != 200:
        raise SystemExit(f"O Google recusou a troca ({resposta.status_code}): "
                         f"{resposta.text}")
    return resposta.json() or {}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Autoriza este projeto a subir video no seu canal.")
    parser.add_argument("--handle", default="canal",
                        help="apelido da conta no cofre (padrao: canal)")
    parser.add_argument("--client-id", default=os.environ.get("YOUTUBE_CLIENT_ID"))
    parser.add_argument("--client-secret",
                        default=os.environ.get("YOUTUBE_CLIENT_SECRET"))
    args = parser.parse_args(argv)

    client_id = args.client_id or input("Client ID: ").strip()
    client_secret = args.client_secret or input("Client Secret: ").strip()
    if not client_id or not client_secret:
        print("Faltou o Client ID ou o Client Secret. Ver o cabecalho deste "
              "arquivo para como emiti-los.", file=sys.stderr)
        return 2

    porta = _porta_livre()
    redirect_uri = f"http://localhost:{porta}"
    url = AUTORIZACAO + "?" + urllib.parse.urlencode({
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": ESCOPO,
        # `offline` e o que faz o Google devolver refresh_token; `consent`
        # forca a tela mesmo se voce ja autorizou antes -- sem ele, a segunda
        # execucao volta SEM refresh_token e o erro nao diz por que.
        "access_type": "offline",
        "prompt": "consent",
    })

    print("\nAbra este endereco no navegador (ou ele abre sozinho):\n")
    print(f"  {url}\n")
    try:
        import webbrowser
        webbrowser.open(url)
    except Exception:
        pass
    print(f"Esperando o retorno em {redirect_uri} ...")

    codigo, erro = _esperar_codigo(porta)
    if not codigo:
        print(f"Nao veio codigo nenhum ({erro or 'tempo esgotado'}).",
              file=sys.stderr)
        return 1

    dados = _trocar_por_token(client_id, client_secret, codigo, redirect_uri)
    refresh = dados.get("refresh_token")
    if not refresh:
        print("O Google respondeu sem refresh_token. Isso acontece quando a "
              "conta ja tinha autorizado antes; revogue o acesso em "
              "https://myaccount.google.com/permissions e rode de novo.",
              file=sys.stderr)
        return 1

    ref = f"vault://local/youtube/{args.handle}"
    caminho = vault.gravar(ref, {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh,
    })
    print(f"\n✅ Guardado em {caminho} (permissao 0600).")
    print(f"   Aponte a conta para: {ref}")
    print("\nSe preferir variaveis de ambiente em vez de arquivo, use estas "
          "tres no .env e apague o arquivo acima:\n")
    print(f"   YOUTUBE_CLIENT_ID={client_id}")
    print(f"   YOUTUBE_CLIENT_SECRET={client_secret}")
    print(f"   YOUTUBE_REFRESH_TOKEN={refresh}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
