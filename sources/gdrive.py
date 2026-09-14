"""Google Drive (Fase 1, bloco 1.6).

**Divergencia deliberada do §4: cookies em vez de OAuth.** O plano previa
"Drive API v3, `files.get?alt=media`, chunks" com "OAuth com refresh token".
Isso e o desenho certo para um SaaS multiusuario, onde cada cliente autoriza a
propria conta -- e e desproporcional para uma ferramenta pessoal self-hosted:
exige criar um projeto no Google Cloud, uma tela de consentimento, credenciais
de cliente e um fluxo de refresh, tudo para o autor ler arquivos da propria
conta.

O yt-dlp ja tem extrator de Google Drive, e ele resolve os dois casos que
existem aqui:

- **arquivo compartilhado por link** ("qualquer pessoa com o link"): baixa sem
  autenticacao nenhuma;
- **arquivo privado**: baixa com `GDRIVE_COOKIES`, o mesmo mecanismo de jar
  Netscape que o YouTube e a Twitch ja usam neste repositorio.

Quando a Fase 4 trouxer multiusuario de verdade, o OAuth volta a ser a resposta
certa -- e ai ele entra como outra implementacao atras desta mesma interface,
que e o motivo de a camada existir.

**Pasta nao e arquivo.** O yt-dlp nao suporta pasta do Drive (e pedido aberto no
projeto deles), e sem a recusa explicita a URL cairia no adapter generico e
falharia com uma mensagem sobre extrator, que nao ajuda ninguem.
"""
from __future__ import annotations

from .base import (Fetched, SourceAdapter, SourceInfo, SourceNotReady,
                   host_of, is_http_url, modulo_main)

HOSTS = ("drive.google.com", "docs.google.com")


def _e_host_do_drive(raw: str) -> bool:
    host = host_of(raw)
    return any(host == h or host.endswith("." + h) for h in HOSTS)


def classify(raw: str) -> str | None:
    """`file` | `folder`, ou None se nao for Drive. Pura, sem rede."""
    if not is_http_url(raw) or not _e_host_do_drive(raw):
        return None
    from urllib.parse import parse_qs, urlparse

    try:
        partes = urlparse(raw)
    except Exception:
        return None
    caminho = [p for p in (partes.path or "").split("/") if p]
    if "folders" in caminho:
        return "folder"
    if "file" in caminho and "d" in caminho:
        return "file"                      # /file/d/<id>/view
    if caminho[:1] == ["open"] or caminho[:1] == ["uc"]:
        # /open?id=<id> e /uc?id=<id>&export=download
        return "file" if parse_qs(partes.query or "").get("id") else None
    return None


class GoogleDriveAdapter(SourceAdapter):
    id = "gdrive"
    label = "Google Drive"

    # Jar proprio, pela mesma razao dos outros: dois jobs simultaneos de
    # plataformas diferentes nao podem se sobrescrever.
    cookie_env = "GDRIVE_COOKIES"
    cookie_file = "/app/cookies-gdrive.txt"

    @classmethod
    def matches(cls, raw: str) -> bool:
        return classify(raw) in ("file", "folder")

    def probe(self, raw: str) -> SourceInfo:
        if classify(raw) == "folder":
            return SourceInfo(kind=self.id, label="Google Drive (pasta)")
        return SourceInfo(
            kind=self.id, label=self.label,
            notes=("arquivo privado precisa de GDRIVE_COOKIES; compartilhado "
                   "por link baixa sem nada",),
        )

    def assert_fetchable(self, raw: str) -> None:
        if classify(raw) == "folder":
            raise SourceNotReady(
                f"{raw} e uma pasta do Drive, nao um arquivo. Abra o video que "
                "voce quer e use a URL dele (tem /file/d/ no meio).")

    def fetch(self, raw: str, output_dir: str = ".") -> Fetched:
        self.assert_fetchable(raw)
        path, title = modulo_main().download_youtube_video(raw, output_dir)
        return Fetched(path=path, title=title, kind=self.id)
