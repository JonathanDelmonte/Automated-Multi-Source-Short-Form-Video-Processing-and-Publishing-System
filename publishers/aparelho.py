"""Os drivers da frota: o aparelho entrega, ou o aparelho publica -- etapa 7.9
(ADR-016).

Dois drivers, separados pelo RISCO, porque e o risco que a cascata le
(ADR-010):

- `aparelho` (risco zero) **entrega**: o video vai para a galeria do celular, o
  app abre com ele -- como pelo "compartilhar" da galeria -- e a legenda fica
  num `.txt` no aparelho. Quem toca em publicar e a pessoa, e a linha termina
  em `scheduled`, como a do `manual`.
- `aparelho-auto` (risco 0,5) **publica**: repete o roteiro que a pessoa
  ensinou e ensaiou (`frota_roteiro`), digita a legenda e toca no botao de
  publicar. So entra na cascata com o consentimento da conta
  (`aceita_consentimento`, `publishers.consentiu`), e so com o ensaio
  passando.

**Tudo o que nao e o esperado vira entrega, nunca palpite**: o app noutra
versao, o ADBKeyBoard ausente, um botao que nao aparece. O video fica no app e
o corte espera a pessoa -- a mesma espera da fila manual. E o aparelho fora do
ar ou ocupado devolve o limite do dia: nada aconteceu nele.

Os dois rodam numa thread do executor (`publish()` e sincrono, ADR-010) e nao
falam com o banco: o que sabem da conta veio no `Account.aparelho`.
"""
from __future__ import annotations

import plataformas

from .base import Account, Cost, PublishResult, Publisher, PublisherError

#: "Pode custar a conta, menos que o navegador": o app oficial, num celular de
#: verdade, sem disfarce -- mas tocado por um programa. Qualquer valor acima de
#: zero tira o driver da cascata; e o consentimento da conta que o devolve.
RISCO_AUTOMATICO = 0.5

#: Quanto um post espera o aparelho largar outra tarefa (um ensino, um ensaio)
#: antes de desistir e cair na fila manual.
ESPERA_PELO_APARELHO_S = 120.0


def _cabe(account: Account) -> bool:
    import frota_limite
    a = account.aparelho
    return bool(a and a.frota_ligada and a.serial
                and account.platform in plataformas.NO_APARELHO
                and frota_limite.cabe(account.id, a.hoje, a.limite))


def roteiro_pronto(account: Account) -> bool:
    """O automatico tem com o que rodar: um roteiro ensinado, com o ensaio
    passando e a tela de compartilhar do app conhecida."""
    roteiro = (account.aparelho.roteiro if account.aparelho else None) or {}
    return bool(roteiro.get("ensaio_ok") and roteiro.get("passos") and roteiro.get("componente"))


class AparelhoPublisher(Publisher):
    id = "aparelho"
    label = "aparelho: você publica"
    platforms = plataformas.NO_APARELHO

    def disponivel(self, account: Account) -> bool:
        return _cabe(account)

    def capability(self, account: Account) -> str:
        return "public" if self.disponivel(account) else "none"

    def cost(self, n: int) -> Cost:
        return Cost(risk_score=0.0)

    def publish(self, clip, meta, opts, account):
        return _publicar(self.id, clip, meta, opts, account, automatico=False)


class AparelhoAutoPublisher(Publisher):
    id = "aparelho-auto"
    label = "aparelho: o motor publica"
    platforms = plataformas.NO_APARELHO
    #: A unica coisa que o traz de volta para a cascata (ADR-016).
    aceita_consentimento = True

    def disponivel(self, account: Account) -> bool:
        return (_cabe(account) and account.aparelho.modo == "automatico"
                and roteiro_pronto(account))

    def capability(self, account: Account) -> str:
        return "public" if self.disponivel(account) else "none"

    def cost(self, n: int) -> Cost:
        return Cost(risk_score=RISCO_AUTOMATICO)

    def publish(self, clip, meta, opts, account):
        return _publicar(self.id, clip, meta, opts, account, automatico=True)


# --------------------------------------------------------------------------- #
# O post
# --------------------------------------------------------------------------- #

def _espera(driver: str, detalhe: str, ok: bool = True, artefatos=()) -> PublishResult:
    """O corte esperando a pessoa: `scheduled` sem hora, como o do `manual`."""
    return PublishResult(ok=ok, driver=driver, status="scheduled", detail=detalhe,
                         artifacts=tuple(artefatos))


def _conectar(cliente, a) -> None:
    """Um aparelho de rede (ou em nuvem) que caiu e reconectado antes do post."""
    if not a.endereco:
        return
    no_ar = {x["serial"] for x in cliente.aparelhos() if x["no_ar"]}
    if a.serial not in no_ar:
        cliente.conectar(a.endereco)


def _publicar(driver: str, clip, meta, opts, account: Account, automatico: bool) -> PublishResult:
    import adb_cliente
    import frota_aparelho
    import frota_limite
    import frota_registro
    import frota_roteiro
    from .manual import render_caption

    a = account.aparelho
    if a is None:
        raise PublisherError("esta conta não mora em nenhum aparelho da frota")
    nome = plataformas.nome(account.platform)
    if opts.dry_run:
        return _espera(driver, f"ensaio a seco: iria para {a.nome}")
    if not frota_limite.debitar(account.id, a.hoje, a.limite):
        return _espera(driver, f"a conta @{account.handle} já postou {a.limite} hoje pelo "
                               "aparelho, o limite dela: o corte ficou na fila manual", ok=False)

    legenda = render_caption(meta, account.platform)
    registro = frota_registro.Execucao(a.device_id, "automatico" if automatico else "entrega",
                                       account.platform, conta=account.handle,
                                       corte=clip.clip_id or "")
    cliente = adb_cliente.Cliente()
    aparelho = frota_aparelho.Aparelho(a.serial, cliente)
    chegou = False
    try:
        with frota_aparelho.ocupar(a.serial, f"publicando na conta @{account.handle}",
                                   espera_s=ESPERA_PELO_APARELHO_S):
            _conectar(cliente, a)
            if aparelho.acordar():
                raise frota_aparelho.AparelhoErro(
                    "a tela de bloqueio está na frente: para a frota, deixe o aparelho "
                    "sem senha de tela, ou desbloqueado")
            roteiro = a.roteiro or {}
            pacote = roteiro.get("pacote") or _app_instalado(aparelho, account.platform)
            if not pacote:
                raise frota_aparelho.AparelhoErro(f"o {nome} não está instalado no aparelho")
            aparelho.limpar_pasta()
            base = frota_aparelho.nome_no_aparelho(clip.clip_id or f"{clip.job_id}-{clip.index}", "")
            uri = aparelho.por_na_galeria(clip.path, base + ".mp4")
            chegou = True
            componente = roteiro.get("componente") or frota_aparelho.escolher_tela(
                aparelho.telas_de_compartilhar(pacote), account.platform)
            texto = aparelho.escrever_texto(base + ".txt", legenda)
            aparelho.abrir_no_app(uri, pacote, componente)

            motivo = _por_que_nao_automatico(aparelho, roteiro, pacote) if automatico else None
            if not automatico or motivo:
                registro.guardar("entregue", aparelho.tela_png())
                detalhe = (f"o vídeo está aberto no {nome} de {a.nome}; a legenda está em "
                           f"{texto}. Toque em publicar e marque “já publiquei”")
                if motivo:
                    detalhe = f"{motivo}. {detalhe}"
                registro.fechar("entregue", detalhe)
                return _espera(driver, detalhe)

            with frota_aparelho.com_adbkeyboard(aparelho):
                resultado = frota_roteiro.Executor(
                    aparelho, roteiro["passos"], legenda=legenda,
                    guardar=registro.guardar, log=print).rodar()
            if resultado.publicado:
                registro.fechar("publicado", f"publicado pelo {a.nome}")
                return PublishResult(
                    ok=True, driver=driver, status="published",
                    detail=(f"publicado pelo {a.nome}. Cole o link no “já publiquei” "
                            "para o post ser medido"))
            detalhe = (f"o automático parou ({resultado.motivo}); o vídeo está no {nome} "
                       f"de {a.nome}: termine por lá e marque “já publiquei”")
            registro.fechar("duvida" if resultado.duvida else "parou", detalhe,
                            passo=resultado.parou_em)
            return _espera(driver, detalhe, ok=False)
    except frota_aparelho.Ocupado as e:
        frota_limite.devolver(account.id, a.hoje)
        registro.fechar("nao-saiu", str(e))
        return _espera(driver, f"{a.nome}: {e}; o corte ficou na fila manual", ok=False)
    except adb_cliente.AdbErro as e:
        if not chegou:
            frota_limite.devolver(account.id, a.hoje)
        registro.fechar("nao-saiu" if not chegou else "parou", str(e))
        onde = "o vídeo não chegou ao aparelho" if not chegou else "o vídeo chegou, mas o app não"
        return _espera(driver, f"{a.nome}: {e} -- {onde}; o corte ficou na fila manual", ok=False)


def _app_instalado(aparelho, plataforma: str):
    import frota_aparelho
    regra = plataformas.de(plataforma)
    instalados = frota_aparelho.ler_pacotes(aparelho.sh("pm list packages 2>/dev/null"))
    return next((app for app in (regra.apps if regra else ()) if app in instalados), None)


def _por_que_nao_automatico(aparelho, roteiro: dict, pacote: str):
    """Por que o automatico nao roda AGORA, ou None. Cada motivo vira entrega:
    o video ja esta no app, e a pessoa termina."""
    versao = aparelho.versao_do_app(pacote)
    if roteiro.get("versao") and versao and versao != roteiro.get("versao"):
        return (f"o app mudou de versão ({roteiro.get('versao')} para {versao}): o automático "
                "volta depois de ensinar e ensaiar de novo")
    if not aparelho.tem_adbkeyboard():
        return "o ADBKeyBoard não está instalado no aparelho: sem ele o motor não digita a legenda"
    return None
