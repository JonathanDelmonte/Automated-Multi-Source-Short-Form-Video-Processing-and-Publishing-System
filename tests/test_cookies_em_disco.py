"""O jar de cookies pode ser um ARQUIVO na pasta, nao so a variavel (22-set-2026).

O download de YouTube falhava com "sign in to confirm you're not a bot" numa
maquina onde o `quality_probe.py` achava os cookies sem problema. Os dois
procuravam em lugares diferentes:

- o `quality_probe` sempre olhou o ARQUIVO, em tres caminhos, e o comentario
  dele dizia "mirrors main.py's cookie discovery";
- o `main.py` **nao tinha** descoberta nenhuma: lia a variavel de ambiente
  `YOUTUBE_COOKIES` e, sem ela, desistia.

E a variavel sozinha nao serve a quem roda em casa: ela guarda o CONTEUDO
INTEIRO do `cookies.txt` -- dezenas de linhas -- dentro do `.env`. Isso e o
mecanismo certo para um deploy em nuvem, onde segredo se entrega por ambiente.
Num `docker compose` com o repositorio montado em `/app`, o arquivo na pasta e
o mecanismo natural, e ja era metade do que existia.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

sources = pytest.importorskip("sources")

YOUTUBE = "https://youtu.be/abc123"


@pytest.fixture
def raiz_falsa(tmp_path, monkeypatch):
    """Aponta a busca para uma pasta de teste, sem tocar na do repositorio."""
    falso = tmp_path / "sources"
    falso.mkdir()
    monkeypatch.setattr(sources, "__file__", str(falso / "__init__.py"))
    return tmp_path


class TestOndeOJarPodeEstar:

    def test_sem_arquivo_nenhum_devolve_none(self, raiz_falsa):
        assert sources.jar_em_disco(YOUTUBE) is None

    def test_acha_cookies_txt_na_raiz(self, raiz_falsa):
        (raiz_falsa / "cookies.txt").write_text("# Netscape HTTP Cookie File\n")
        assert sources.jar_em_disco(YOUTUBE) == str(raiz_falsa / "cookies.txt")

    def test_acha_o_nome_que_a_extensao_salva(self, raiz_falsa):
        """`www.youtube.com_cookies.txt` e como as extensoes de exportar
        salvam. Obrigar a renomear e um passo a mais para errar."""
        alvo = raiz_falsa / "www.youtube.com_cookies.txt"
        alvo.write_text("# Netscape HTTP Cookie File\n")
        assert sources.jar_em_disco(YOUTUBE) == str(alvo)

    def test_arquivo_vazio_conta_como_ausente(self, raiz_falsa):
        """Um `cookies.txt` de zero byte e o que sobra de uma exportacao que
        falhou. Passa-lo ao yt-dlp devolve o MESMO erro de bot, sem dizer que o
        jar e que estava vazio."""
        (raiz_falsa / "cookies.txt").write_text("")
        assert sources.jar_em_disco(YOUTUBE) is None

    def test_o_nome_da_extensao_vem_do_ADAPTER(self):
        """Propriedade da fonte mora no adapter, como o `cookie_env` e o
        `cookie_file` -- nao numa lista dentro do `main.py`."""
        from sources.youtube import YouTubeAdapter
        assert "www.youtube.com_cookies.txt" in YouTubeAdapter.cookie_file_alt

    def test_fonte_sem_nome_alternativo_nao_inventa(self, raiz_falsa):
        """Só o YouTube tem nome de extensão. Um `www.youtube.com_cookies.txt`
        não pode virar o jar da Twitch."""
        (raiz_falsa / "www.youtube.com_cookies.txt").write_text("x")
        assert sources.jar_em_disco("https://www.twitch.tv/videos/123") is None

    def test_url_irreconhecivel_nao_levanta(self, raiz_falsa):
        assert sources.jar_em_disco("nao e url nenhuma") is None


class TestAsDuasMetadesConcordam:
    """O defeito era discordancia, entao o teste e sobre ela."""

    def test_o_probe_usa_a_mesma_definicao_do_download(self):
        import ast
        raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        def chama_jar_em_disco(caminho, dentro_de=None):
            with open(os.path.join(raiz, caminho), encoding="utf-8") as fh:
                arvore = ast.parse(fh.read())
            for no in ast.walk(arvore):
                if (isinstance(no, ast.Call)
                        and isinstance(no.func, ast.Attribute)
                        and no.func.attr == "jar_em_disco"):
                    return True
            return False

        assert chama_jar_em_disco("main.py"), \
            "o main.py deixou de procurar o arquivo de cookies"
        assert chama_jar_em_disco("quality_probe.py"), \
            "o quality_probe voltou a ter busca propria: as duas metades vao divergir"

    def test_nenhum_dos_dois_tem_lista_de_caminhos_propria(self):
        """Foi assim que divergiram: o `quality_probe` tinha a lista embutida."""
        raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for arquivo in ("main.py", "quality_probe.py"):
            with open(os.path.join(raiz, arquivo), encoding="utf-8") as fh:
                corpo = "\n".join(l for l in fh.read().splitlines()
                                  if not l.strip().startswith("#"))
            assert "www.youtube.com_cookies.txt" not in corpo, (
                f"{arquivo} voltou a listar caminhos de cookie por conta propria")


class TestOJarNaoVaiParaOGit:
    """Cookie de sessao e credencial viva: quem tem o arquivo entra na conta
    sem senha e sem 2FA. Ate 22-set-2026 nada no `.gitignore` os cobria, e o
    conserto acima fez o arquivo passar a existir na pasta de trabalho."""

    @pytest.mark.parametrize("nome", [
        "cookies.txt", "cookies-gdrive.txt", "www.youtube.com_cookies.txt",
    ])
    def test_gitignore_cobre(self, nome):
        import subprocess
        raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        r = subprocess.run(["git", "check-ignore", nome],
                           cwd=raiz, capture_output=True, text=True)
        assert r.returncode == 0, f"{nome} NAO esta no .gitignore"
