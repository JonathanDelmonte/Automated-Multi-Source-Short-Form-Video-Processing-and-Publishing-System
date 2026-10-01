"""A frota no banco, e as tarefas longas de cada aparelho -- etapa 7.9 (ADR-016).

Junta as pecas: as tabelas da frota (`db_models`, 26 a 29), o aparelho pelo adb
(`frota_aparelho`), o roteiro ensinado (`frota_roteiro`), o limite por conta
(`frota_limite`) e o historico com as fotos (`frota_registro`).

**A frota nasce desligada** (`fleet_settings`): ligar e a pessoa dizer que leu
os limites, e com ela desligada nenhum driver da frota responde.

**O CRUD levanta, como o dos canais**: cadastrar aparelho e ligar conta e acao de
quem esta na tela, e a regra recusada volta com o motivo em frase. O que o
driver le (`aparelhos_das_contas`) e montado aqui, antes de chamar o
resolvedor, porque o driver roda numa thread sem banco.

**Ensinar e ensaiar seguram o aparelho** (`frota_aparelho.reservar`): um post
agendado no meio de um ensino espera, e depois de `ESPERA_PELO_APARELHO_S` cai
na fila manual. O ensino largado e encerrado sozinho depois de
`ENSINO_OCIOSO_S`, devolvendo o teclado da pessoa.
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import adb_cliente
import db
import db_models
import frota_aparelho
import frota_registro
import frota_roteiro
import plataformas
import publishers


class FrotaErro(ValueError):
    """Pedido recusado por uma regra; o texto vai para a tela como esta."""
    status = 400


class FrotaConflito(FrotaErro):
    status = 409


class FrotaNaoAchou(FrotaErro):
    status = 404


NOME_MAX = 80
NOTAS_MAX = 500
#: O ensino largado no meio (a pessoa fechou a aba) e encerrado depois disto,
#: e o aparelho volta a postar.
ENSINO_OCIOSO_S = 600
#: A legenda do ensaio tem acento e emoji de proposito: e o que o `input text`
#: nao digita, e o ensaio existe para provar que o ADBKeyBoard digita.
LEGENDA_DO_ENSAIO = "Ensaio do Virtu Clips: ação, coração e emoji 🎬 #teste"


def _dormir(segundos: float) -> None:
    """As esperas pela tela do aparelho, num nome que o teste troca."""
    time.sleep(segundos)


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _iso(quando: Optional[datetime]) -> Optional[str]:
    if quando is None:
        return None
    return (quando if quando.tzinfo else quando.replace(tzinfo=timezone.utc)).isoformat()


def hoje_de(tenant_id: str) -> str:
    """O dia de quem usa, em que o limite de cada conta e contado."""
    import fuso
    return datetime.now(fuso.tz_do_tenant(tenant_id)).date().isoformat()


# --------------------------------------------------------------------------- #
# Ligar e desligar
# --------------------------------------------------------------------------- #

async def _config(t):
    linhas = await t.all(db_models.FleetSettings)
    return linhas[0] if linhas else None


async def configuracao() -> dict:
    async with db.tenant() as t:
        linha = await _config(t)
        doc = dict(linha.settings_json or {}) if linha else {}
    return {"ligada": bool(doc.get("ligada")), "ligada_em": doc.get("ligada_em"),
            "desligada_em": doc.get("desligada_em")}


async def ligar(valor: bool, entendi: bool = False) -> dict:
    """Liga ou desliga a frota. Ligar exige `entendi`: a pessoa leu que a
    publicacao automatizada pode custar a conta (ADR-016)."""
    if valor and not entendi:
        raise FrotaErro("para ligar a frota, confirme que leu os limites: as plataformas "
                        "podem punir a conta por publicação automatizada")
    async with db.tenant() as t:
        linha = await _config(t)
        doc = dict(linha.settings_json or {}) if linha else {}
        doc["ligada"] = bool(valor)
        doc["ligada_em" if valor else "desligada_em"] = _agora().isoformat()
        if linha is None:
            t.add(db_models.FleetSettings(settings_json=doc))
        else:
            linha.settings_json = doc
            linha.updated_at = _agora()
        await t.commit()
    return {"ligada": bool(valor), "ligada_em": doc.get("ligada_em"),
            "desligada_em": doc.get("desligada_em")}


# --------------------------------------------------------------------------- #
# Aparelhos
# --------------------------------------------------------------------------- #

def _roteiro_json(linha) -> dict:
    passos = (linha.steps_json or {}).get("passos") or []
    return {
        "pacote": linha.app_package,
        "versao": linha.app_version,
        "componente": linha.component,
        "passos": [{"tipo": p.get("tipo"), "descricao": frota_roteiro.descrever(p.get("alvo") or {})}
                   for p in passos],
        "ensinado_em": _iso(linha.taught_at),
        "ensaiado_em": _iso(linha.rehearsed_at),
        "ensaio_ok": linha.rehearsal_ok,
        "ensaio_detalhe": linha.rehearsal_detail,
    }


def _aparelho_json(linha, ligacoes: list, contas: dict, roteiros: list, hoje: str) -> dict:
    import frota_limite
    suas = []
    for l in ligacoes:
        if l.device_id != linha.id:
            continue
        conta = contas.get(l.account_id)
        suas.append({
            "account_id": l.account_id,
            "platform": l.platform,
            "handle": conta.handle if conta else None,
            "modo": l.mode,
            "limite": l.daily_limit,
            "consentiu_em": _iso(l.consent_at),
            "hoje": frota_limite.usados(l.account_id, hoje),
        })
    suas.sort(key=lambda c: plataformas.ordem(c["platform"]))
    return {
        "id": linha.id,
        "serial": linha.serial,
        "nome": linha.name,
        "tipo": linha.kind,
        "endereco": linha.address,
        "notas": linha.notes,
        "criado_em": _iso(linha.created_at),
        "contas": suas,
        "roteiros": {r.platform: _roteiro_json(r) for r in roteiros if r.device_id == linha.id},
        "ocupado": frota_aparelho.ocupado_com(linha.serial),
        "ensinando": linha.id in _ENSINOS,
        "ensaio": _ENSAIOS.get(linha.id),
    }


async def listar() -> list:
    async with db.tenant() as t:
        aparelhos = await t.all(db_models.Device)
        ligacoes = await t.all(db_models.DeviceAccount)
        contas = {a.id: a for a in await t.all(db_models.Account)}
        roteiros = await t.all(db_models.DeviceScript)
        hoje = hoje_de(t.tenant_id)
    aparelhos.sort(key=lambda a: (a.name or "").lower())
    return [_aparelho_json(a, ligacoes, contas, roteiros, hoje) for a in aparelhos]


async def obter(device_id: str) -> dict:
    for aparelho in await listar():
        if aparelho["id"] == device_id:
            return aparelho
    raise FrotaNaoAchou("aparelho não encontrado")


async def _linha(t, device_id: str):
    linha = await t.get(db_models.Device, device_id)
    if linha is None:
        raise FrotaNaoAchou("aparelho não encontrado")
    return linha


def _texto(valor, maximo: int, campo: str, obrigatorio: bool = False) -> Optional[str]:
    texto = " ".join(str(valor or "").split())
    if obrigatorio and not texto:
        raise FrotaErro(f"o aparelho precisa de {campo}")
    if len(texto) > maximo:
        raise FrotaErro(f"{campo} passa de {maximo} caracteres")
    return texto or None


async def _serial_de_outro_tenant(serial: str, tenant_id: str) -> bool:
    """Um celular e de uma conta da instalacao so: o adb e um so para todas, e
    duas contas postando pelo mesmo aparelho seriam duas maos na mesma tela.
    Sessao crua de proposito -- a pergunta atravessa os tenants, e a resposta
    nao diz de quem e."""
    from sqlalchemy import select
    async with db.session() as s:
        donos = (await s.execute(select(db_models.Device.tenant_id)
                                 .where(db_models.Device.serial == serial))).scalars().all()
    return any(d != tenant_id for d in donos)


async def criar(corpo: dict) -> dict:
    serial = str(corpo.get("serial") or "").strip()
    tipo = corpo.get("tipo") or "cabo"
    endereco = str(corpo.get("endereco") or "").strip() or None
    if tipo not in db_models.DEVICE_KINDS:
        raise FrotaErro("tipo de aparelho desconhecido")
    if not serial and endereco:
        serial = endereco
    if not adb_cliente.serial_valido(serial):
        raise FrotaErro("serial inválido: copie o que aparece na lista de aparelhos vistos")
    if endereco and not adb_cliente.endereco_valido(endereco):
        raise FrotaErro("endereço inválido: use ip:porta (o que a tela de depuração do celular mostra)")
    if tipo in ("rede", "nuvem") and not endereco and adb_cliente.endereco_valido(serial):
        endereco = serial
    nome = _texto(corpo.get("nome"), NOME_MAX, "um nome", obrigatorio=True)
    notas = _texto(corpo.get("notas"), NOTAS_MAX, "as notas")
    async with db.tenant() as t:
        if await t.all(db_models.Device, db_models.Device.serial == serial):
            raise FrotaConflito("este aparelho já está na frota")
        if await _serial_de_outro_tenant(serial, t.tenant_id):
            raise FrotaConflito("este aparelho já está na frota de outra conta desta instalação")
        linha = t.add(db_models.Device(serial=serial, name=nome, kind=tipo,
                                       address=endereco, notes=notas))
        await t.commit()
        device_id = linha.id
    return await obter(device_id)


async def editar(device_id: str, corpo: dict) -> dict:
    async with db.tenant() as t:
        linha = await _linha(t, device_id)
        if "nome" in corpo:
            linha.name = _texto(corpo.get("nome"), NOME_MAX, "um nome", obrigatorio=True)
        if "notas" in corpo:
            linha.notes = _texto(corpo.get("notas"), NOTAS_MAX, "as notas")
        if "endereco" in corpo:
            endereco = str(corpo.get("endereco") or "").strip() or None
            if endereco and not adb_cliente.endereco_valido(endereco):
                raise FrotaErro("endereço inválido: use ip:porta")
            linha.address = endereco
        await t.commit()
    return await obter(device_id)


async def apagar(device_id: str) -> bool:
    """Tira o aparelho da frota: as contas dele voltam a postar pelo caminho de
    antes (a cascata sem o aparelho), e o historico e as fotos saem."""
    async with db.tenant() as t:
        linha = await t.get(db_models.Device, device_id)
        if linha is None:
            return False
        serial = linha.serial
        await t.session.delete(linha)
        await t.commit()
    if device_id in _ENSINOS:
        await asyncio.to_thread(encerrar_ensino, device_id)
    frota_registro.apagar(device_id)
    _ESTADOS.pop(serial, None)
    return True


# --------------------------------------------------------------------------- #
# As contas de cada aparelho
# --------------------------------------------------------------------------- #

def _limite(valor) -> int:
    try:
        limite = int(valor if valor not in (None, "") else db_models.LIMITE_DIARIO_PADRAO)
    except (TypeError, ValueError):
        raise FrotaErro("o limite é um número de posts por dia")
    if not 1 <= limite <= db_models.LIMITE_DIARIO_MAXIMO:
        raise FrotaErro(f"o limite vai de 1 a {db_models.LIMITE_DIARIO_MAXIMO} posts por dia: "
                        "15 é o que a via oficial do TikTok, a mais apertada, aceita")
    return limite


async def ligar_conta(device_id: str, corpo: dict) -> dict:
    """Poe uma conta no aparelho, ou muda o modo e o limite dela.

    Uma conta mora num aparelho so: pedi-la aqui a TIRA do aparelho de antes.
    O automatico pede duas coisas, e nenhuma e padrao: o consentimento da
    pessoa, e um roteiro do app ensinado e ensaiado NESTE aparelho."""
    account_id = str(corpo.get("account_id") or "")
    modo = corpo.get("modo") or "entregar"
    if modo not in db_models.FLEET_MODES:
        raise FrotaErro("modo desconhecido")
    limite = _limite(corpo.get("limite"))
    async with db.tenant() as t:
        await _linha(t, device_id)
        conta = await t.get(db_models.Account, account_id)
        if conta is None:
            raise FrotaNaoAchou("conta não encontrada")
        if conta.platform not in plataformas.NO_APARELHO:
            raise FrotaErro(f"o {plataformas.nome(conta.platform)} não tem app que a frota saiba abrir")
        ligacoes = await t.all(db_models.DeviceAccount)
        for l in ligacoes:
            if (l.device_id == device_id and l.platform == conta.platform
                    and l.account_id != account_id):
                outra = await t.get(db_models.Account, l.account_id)
                raise FrotaConflito(
                    f"este aparelho já tem uma conta do {plataformas.nome(conta.platform)} "
                    f"(@{outra.handle if outra else '?'}): um aparelho, uma conta por app -- "
                    "trocar de conta dentro do app seria um toque às cegas")
        atual = next((l for l in ligacoes if l.account_id == account_id), None)
        if modo == "automatico":
            ja_consentiu = bool(atual and atual.device_id == device_id
                                and atual.mode == "automatico" and atual.consent_at)
            if not corpo.get("consentimento") and not ja_consentiu:
                raise FrotaErro("o automático pede o seu consentimento: o motor vai tocar no "
                                "botão de publicar, e a plataforma pode punir a conta por isso")
            roteiro = await t.all(db_models.DeviceScript,
                                  db_models.DeviceScript.device_id == device_id,
                                  db_models.DeviceScript.platform == conta.platform)
            if not roteiro or not roteiro[0].rehearsal_ok:
                raise FrotaConflito("ensine e ensaie o app neste aparelho antes de ligar o "
                                    "automático: sem o ensaio passando, o motor não sabe onde tocar")
            consentiu_em = atual.consent_at if ja_consentiu else _agora()
        else:
            # Voltar a entregar e retirar o consentimento: ligar de novo pede outro.
            consentiu_em = None
        if atual is None:
            t.add(db_models.DeviceAccount(device_id=device_id, account_id=account_id,
                                          platform=conta.platform, mode=modo,
                                          daily_limit=limite, consent_at=consentiu_em))
        else:
            atual.device_id = device_id
            atual.mode = modo
            atual.daily_limit = limite
            atual.consent_at = consentiu_em
        await t.commit()
    return await obter(device_id)


async def soltar_conta(device_id: str, account_id: str) -> bool:
    """A conta sai do aparelho e volta ao caminho de antes. A contagem do dia
    fica: soltar e ligar de novo nao zera o limite."""
    async with db.tenant() as t:
        ligacoes = await t.all(db_models.DeviceAccount,
                               db_models.DeviceAccount.device_id == device_id,
                               db_models.DeviceAccount.account_id == account_id)
        if not ligacoes:
            return False
        await t.session.delete(ligacoes[0])
        await t.commit()
    return True


# --------------------------------------------------------------------------- #
# O que o driver le
# --------------------------------------------------------------------------- #

async def aparelhos_das_contas(t) -> dict:
    """{account_id: AparelhoDaConta} das contas que moram num aparelho, dentro
    da sessao de quem chama (a fila)."""
    ligacoes = await t.all(db_models.DeviceAccount)
    if not ligacoes:
        return {}
    config = await _config(t)
    ligada = bool(config and (config.settings_json or {}).get("ligada"))
    aparelhos = {a.id: a for a in await t.all(db_models.Device)}
    roteiros = {(r.device_id, r.platform): r for r in await t.all(db_models.DeviceScript)}
    hoje = hoje_de(t.tenant_id)
    saida = {}
    for l in ligacoes:
        aparelho = aparelhos.get(l.device_id)
        if aparelho is None:
            continue
        r = roteiros.get((l.device_id, l.platform))
        roteiro = None
        if r is not None:
            roteiro = {"pacote": r.app_package, "versao": r.app_version,
                       "componente": r.component,
                       "passos": (r.steps_json or {}).get("passos") or [],
                       "ensaio_ok": bool(r.rehearsal_ok)}
        saida[l.account_id] = publishers.AparelhoDaConta(
            device_id=aparelho.id, serial=aparelho.serial, nome=aparelho.name,
            modo=l.mode, limite=l.daily_limit, hoje=hoje, frota_ligada=ligada,
            endereco=aparelho.address, roteiro=roteiro)
    return saida


# --------------------------------------------------------------------------- #
# Ao vivo: o adb, o estado e a tela
# --------------------------------------------------------------------------- #

_ESTADOS: dict = {}
#: O estado do aparelho e lido no maximo a cada tanto: e um script com oito
#: `dumpsys`, e o painel pergunta a cada poucos segundos.
IDADE_DO_ESTADO_S = 20.0


def situacao_do_adb() -> dict:
    """O servidor do adb responde? Fora do Docker, o motor tenta liga-lo uma
    vez, se achar o adb nesta maquina."""
    cliente = adb_cliente.Cliente(timeout=3)
    saida = {"endereco": cliente.endereco, "docker": adb_cliente.em_container(),
             "alcancado": False, "versao": None, "erro": None,
             "adb_nesta_maquina": bool(adb_cliente.achar_adb())}
    try:
        saida["versao"] = cliente.versao()
        saida["alcancado"] = True
    except adb_cliente.AdbErro as e:
        if not saida["docker"] and saida["adb_nesta_maquina"] and adb_cliente.ligar_servidor():
            try:
                saida["versao"] = cliente.versao()
                saida["alcancado"] = True
                return saida
            except adb_cliente.AdbErro as e2:
                e = e2
        saida["erro"] = str(e)
    return saida


def vistos() -> list:
    """Os aparelhos que o servidor do adb ve agora."""
    return adb_cliente.Cliente(timeout=5).aparelhos()


def estado(serial: str, idade_max: float = IDADE_DO_ESTADO_S) -> dict:
    """O estado ao vivo, lido no maximo a cada `idade_max` segundos. Erro vira
    o campo `erro`, nunca excecao: o painel desenha o aparelho fora do ar."""
    guardado = _ESTADOS.get(serial)
    if guardado and time.monotonic() - guardado[0] < idade_max:
        return guardado[1]
    try:
        lido = frota_aparelho.Aparelho(serial).estado()
        lido["no_ar"] = True
    except adb_cliente.AdbErro as e:
        lido = {"no_ar": False, "erro": str(e)}
    lido["lido_em"] = _agora().isoformat()
    _ESTADOS[serial] = (time.monotonic(), lido)
    return lido


def _tamanho_do_png(png: bytes) -> tuple:
    return int.from_bytes(png[16:20], "big"), int.from_bytes(png[20:24], "big")


def _elementos(tela: frota_roteiro.Tela, largura: int, altura: int) -> list:
    """O que da para tocar, em fracao da imagem, para o painel contornar."""
    saida = []
    for n in tela.tocaveis():
        x1, y1, x2, y2 = n.caixa
        saida.append({"x": x1 / largura, "y": y1 / altura,
                      "w": (x2 - x1) / largura, "h": (y2 - y1) / altura,
                      "rotulo": n.rotulo or (n.rid.rpartition("/")[2] if n.rid else ""),
                      "tipo": "campo" if n.editavel else "botao"})
    return saida


def tela(serial: str) -> dict:
    """A imagem da tela agora, reduzida para o painel."""
    png = frota_aparelho.Aparelho(serial).tela_png()
    largura, altura = _tamanho_do_png(png)
    dados, extensao = frota_registro.reduzir(png)
    return {"imagem": frota_registro.data_url(dados, extensao),
            "largura": largura, "altura": altura}


def tocar(serial: str, fx: float, fy: float) -> dict:
    """Um toque do painel na tela do aparelho (o controle remoto). Recusado
    enquanto o aparelho publica, ensina ou ensaia."""
    with frota_aparelho.ocupar(serial, "tocado pelo painel"):
        aparelho = frota_aparelho.Aparelho(serial)
        png = aparelho.tela_png()
        largura, altura = _tamanho_do_png(png)
        x = int(min(max(float(fx), 0.0), 1.0) * (largura - 1))
        y = int(min(max(float(fy), 0.0), 1.0) * (altura - 1))
        aparelho.tocar(x, y)
    _dormir(0.8)
    return tela(serial)


def tecla(serial: str, nome: str) -> dict:
    with frota_aparelho.ocupar(serial, "tocado pelo painel"):
        frota_aparelho.Aparelho(serial).tecla(nome)
    _dormir(0.8)
    return tela(serial)


def conectar(endereco: str) -> dict:
    ok, texto = adb_cliente.Cliente().conectar(endereco)
    return {"ok": ok, "mensagem": texto}


def parear(endereco: str, codigo: str) -> dict:
    ok, texto = adb_cliente.Cliente().parear(endereco, codigo)
    return {"ok": ok, "mensagem": texto}


# --------------------------------------------------------------------------- #
# O video de teste
# --------------------------------------------------------------------------- #

def video_de_teste() -> str:
    """Quatro segundos de tela escura e silencio, 720x1280: o ensino e o
    ensaio levam este video ao app, e nunca um corte de verdade -- nenhum dos
    dois toca em publicar, e um corte real ali seria um corte a um toque de
    sair por engano."""
    pasta = os.path.join((os.environ.get("DATA_DIR") or "").strip() or "data", "frota")
    caminho = os.path.join(pasta, "teste.mp4")
    if os.path.exists(caminho) and os.path.getsize(caminho) > 0:
        return caminho
    os.makedirs(pasta, exist_ok=True)
    temporario = caminho + ".parcial.mp4"
    comando = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
               "-f", "lavfi", "-i", "color=c=0x16161a:s=720x1280:d=4:r=30",
               "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
               "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p",
               "-c:a", "aac", "-b:a", "64k", "-movflags", "+faststart", temporario]
    try:
        subprocess.run(comando, check=True, capture_output=True, timeout=120,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError) as e:
        raise FrotaErro(f"não consegui gerar o vídeo de teste com o ffmpeg ({e})")
    os.replace(temporario, caminho)
    return caminho


# --------------------------------------------------------------------------- #
# O ensino
# --------------------------------------------------------------------------- #

@dataclass
class _Sessao:
    device_id: str
    serial: str
    plataforma: str
    pacote: str
    versao: Optional[str]
    componente: Optional[str]
    aparelho: frota_aparelho.Aparelho
    ensino: frota_roteiro.Ensino
    teclado_antes: Optional[str]
    video: Optional[str]
    largura: int
    altura: int
    ultimo_uso: float


_ENSINOS: dict = {}
_TRAVA_DOS_ENSINOS = threading.Lock()


def _app_do_aparelho(aparelho, plataforma: str) -> Optional[str]:
    regra = plataformas.de(plataforma)
    instalados = frota_aparelho.ler_pacotes(aparelho.sh("pm list packages 2>/dev/null"))
    return next((app for app in (regra.apps if regra else ()) if app in instalados), None)


def _preparar(aparelho, plataforma: str, componente: Optional[str]) -> tuple:
    """Acorda o aparelho, acha o app e a tela de compartilhar dele. Levanta
    `FrotaErro` com o que a pessoa precisa fazer no celular."""
    if plataforma not in plataformas.NO_APARELHO:
        raise FrotaErro("plataforma sem app conhecido")
    if aparelho.acordar():
        raise FrotaErro("a tela de bloqueio está na frente: desbloqueie o aparelho")
    pacote = _app_do_aparelho(aparelho, plataforma)
    if not pacote:
        raise FrotaErro(f"o {plataformas.nome(plataforma)} não está instalado neste aparelho")
    telas = aparelho.telas_de_compartilhar(pacote)
    if componente:
        if componente not in telas:
            raise FrotaErro("essa tela de compartilhar não existe no app deste aparelho")
    else:
        componente = frota_aparelho.escolher_tela(telas, plataforma)
        if not componente:
            erro = FrotaConflito(
                "o app tem mais de uma tela que recebe vídeo, e o motor não chuta qual é a "
                "do post: escolha uma" if telas else
                "o app não recebe vídeo pelo compartilhar neste aparelho")
            erro.opcoes = telas
            raise erro
    return pacote, aparelho.versao_do_app(pacote), componente


def _sessao(device_id: str) -> _Sessao:
    with _TRAVA_DOS_ENSINOS:
        sessao = _ENSINOS.get(device_id)
    if sessao is None:
        raise FrotaNaoAchou("não há ensino em andamento neste aparelho")
    sessao.ultimo_uso = time.monotonic()
    return sessao


def estado_do_ensino(device_id: str) -> dict:
    sessao = _sessao(device_id)
    png = sessao.aparelho.tela_png()
    largura, altura = _tamanho_do_png(png)
    if sessao.ensino.tela is None:
        sessao.ensino.atualizar()
    dados, extensao = frota_registro.reduzir(png)
    return {
        "plataforma": sessao.plataforma,
        "pacote": sessao.pacote,
        "versao": sessao.versao,
        "pronto": sessao.ensino.pronto,
        "digita": sessao.ensino.digitar,
        "passos": [{"tipo": p["tipo"], "descricao": frota_roteiro.descrever(p["alvo"])}
                   for p in sessao.ensino.passos],
        "imagem": frota_registro.data_url(dados, extensao),
        "largura": largura,
        "altura": altura,
        "elementos": _elementos(sessao.ensino.tela, largura, altura),
    }


def iniciar_ensino(device_id: str, serial: str, plataforma: str,
                   componente: Optional[str] = None) -> dict:
    """Reserva o aparelho, poe o video de teste no app e mostra a primeira
    tela. Daqui em diante, cada toque vem do painel."""
    varrer_ensinos()
    if device_id in _ENSINOS:
        raise FrotaConflito("já há um ensino em andamento neste aparelho")
    video = video_de_teste()
    frota_aparelho.reservar(serial, f"aprendendo o {plataformas.nome(plataforma)}")
    aparelho = frota_aparelho.Aparelho(serial)
    teclado_antes = None
    no_aparelho = None
    try:
        pacote, versao, componente = _preparar(aparelho, plataforma, componente)
        aparelho.limpar_pasta()
        nome = frota_aparelho.nome_no_aparelho(f"teste-{int(time.time())}", ".mp4")
        uri = aparelho.por_na_galeria(video, nome)
        no_aparelho = f"{frota_aparelho.PASTA_DOS_VIDEOS}/{nome}"
        digita = aparelho.tem_adbkeyboard()
        if digita:
            teclado_antes = aparelho.teclado_atual()
            aparelho.usar_teclado(frota_aparelho.ADBKEYBOARD)
        aparelho.abrir_no_app(uri, pacote, componente)
        _dormir(2.5)
        largura, altura = _tamanho_do_png(aparelho.tela_png())
        ensino = frota_roteiro.Ensino(aparelho, (largura, altura), digitar=digita)
        ensino.atualizar()
    except BaseException:
        _devolver(aparelho, teclado_antes, no_aparelho)
        frota_aparelho.liberar(serial)
        raise
    with _TRAVA_DOS_ENSINOS:
        _ENSINOS[device_id] = _Sessao(device_id, serial, plataforma, pacote, versao, componente,
                                     aparelho, ensino, teclado_antes, no_aparelho,
                                     largura, altura, time.monotonic())
    return estado_do_ensino(device_id)


def _devolver(aparelho, teclado_antes: Optional[str], video: Optional[str]) -> None:
    """O teclado de antes e a pasta sem o video de teste, aconteca o que
    acontecer."""
    if teclado_antes and teclado_antes != frota_aparelho.ADBKEYBOARD:
        try:
            aparelho.usar_teclado(teclado_antes)
        except adb_cliente.AdbErro:
            pass
    if video:
        try:
            aparelho.apagar(video)
        except adb_cliente.AdbErro:
            pass


def ensino_tocar(device_id: str, fx: float, fy: float) -> dict:
    sessao = _sessao(device_id)
    try:
        sessao.ensino.tocar(fx, fy)
    except ValueError as e:
        raise FrotaErro(str(e))
    return estado_do_ensino(device_id)


def ensino_publicar(device_id: str, fx: float, fy: float) -> dict:
    sessao = _sessao(device_id)
    try:
        sessao.ensino.publicar(fx, fy)
    except ValueError as e:
        raise FrotaErro(str(e))
    return estado_do_ensino(device_id)


def ensino_desfazer(device_id: str) -> dict:
    _sessao(device_id).ensino.desfazer()
    return estado_do_ensino(device_id)


def ensino_tecla(device_id: str, nome: str) -> dict:
    sessao = _sessao(device_id)
    sessao.aparelho.tecla(nome)
    _dormir(1.0)
    sessao.ensino.atualizar()
    return estado_do_ensino(device_id)


def roteiro_do_ensino(device_id: str) -> dict:
    """O que o ensino aprendeu, ja validado, para gravar."""
    sessao = _sessao(device_id)
    try:
        passos = sessao.ensino.roteiro()
    except ValueError as e:
        raise FrotaErro(str(e))
    return {"plataforma": sessao.plataforma, "pacote": sessao.pacote,
            "versao": sessao.versao, "componente": sessao.componente, "passos": passos}


def encerrar_ensino(device_id: str) -> bool:
    with _TRAVA_DOS_ENSINOS:
        sessao = _ENSINOS.pop(device_id, None)
    if sessao is None:
        return False
    try:
        _devolver(sessao.aparelho, sessao.teclado_antes, sessao.video)
    finally:
        frota_aparelho.liberar(sessao.serial)
    return True


def varrer_ensinos() -> list:
    """Encerra os ensinos largados (a aba fechada no meio)."""
    agora = time.monotonic()
    with _TRAVA_DOS_ENSINOS:
        largados = [d for d, s in _ENSINOS.items() if agora - s.ultimo_uso > ENSINO_OCIOSO_S]
    for device_id in largados:
        encerrar_ensino(device_id)
    return largados


async def salvar_roteiro(device_id: str, roteiro: dict) -> dict:
    """Grava o roteiro ensinado e zera o ensaio: roteiro novo, ensaio novo."""
    plataforma = roteiro["plataforma"]
    passos = frota_roteiro.validar(roteiro["passos"])
    async with db.tenant() as t:
        await _linha(t, device_id)
        existentes = await t.all(db_models.DeviceScript,
                                 db_models.DeviceScript.device_id == device_id,
                                 db_models.DeviceScript.platform == plataforma)
        doc = {"versao": frota_roteiro.VERSAO, "passos": passos}
        if existentes:
            linha = existentes[0]
            linha.app_package = roteiro["pacote"]
            linha.app_version = roteiro.get("versao")
            linha.component = roteiro.get("componente")
            linha.steps_json = doc
            linha.taught_at = _agora()
            linha.rehearsed_at = None
            linha.rehearsal_ok = None
            linha.rehearsal_detail = None
        else:
            t.add(db_models.DeviceScript(
                device_id=device_id, platform=plataforma, app_package=roteiro["pacote"],
                app_version=roteiro.get("versao"), component=roteiro.get("componente"),
                steps_json=doc))
        await t.commit()
    return await obter(device_id)


async def apagar_roteiro(device_id: str, plataforma: str) -> bool:
    async with db.tenant() as t:
        linhas = await t.all(db_models.DeviceScript,
                             db_models.DeviceScript.device_id == device_id,
                             db_models.DeviceScript.platform == plataforma)
        if not linhas:
            return False
        await t.session.delete(linhas[0])
        await t.commit()
    return True


# --------------------------------------------------------------------------- #
# O ensaio
# --------------------------------------------------------------------------- #

_ENSAIOS: dict = {}
#: As tarefas de ensaio em curso. A referencia existe de proposito: o asyncio
#: guarda so uma referencia fraca da tarefa, e uma tarefa sem dono pode ser
#: recolhida no meio.
_TAREFAS: set = set()


def _ensaiar_no_aparelho(device_id: str, serial: str, plataforma: str, roteiro: dict) -> dict:
    """Refaz o roteiro com o video de teste e para no botao de publicar."""
    registro = frota_registro.Execucao(device_id, "ensaio", plataforma)
    video = video_de_teste()
    aparelho = frota_aparelho.Aparelho(serial)
    no_aparelho = None
    try:
        with frota_aparelho.ocupar(serial, f"ensaiando o {plataformas.nome(plataforma)}"):
            pacote, versao, _componente = _preparar(aparelho, plataforma, roteiro["componente"])
            if roteiro.get("versao") and versao and versao != roteiro["versao"]:
                detalhe = (f"o app mudou de versão desde o ensino ({roteiro['versao']} para "
                           f"{versao}): ensine de novo")
                registro.fechar("falhou", detalhe)
                return {"ok": False, "detalhe": detalhe, "versao": versao, "execucao": registro.id}
            if not aparelho.tem_adbkeyboard():
                detalhe = ("o ADBKeyBoard não está instalado: sem ele o motor não digita a "
                           "legenda (acento e emoji)")
                registro.fechar("falhou", detalhe)
                return {"ok": False, "detalhe": detalhe, "versao": versao, "execucao": registro.id}
            nome = frota_aparelho.nome_no_aparelho(f"ensaio-{int(time.time())}", ".mp4")
            uri = aparelho.por_na_galeria(video, nome)
            no_aparelho = f"{frota_aparelho.PASTA_DOS_VIDEOS}/{nome}"
            aparelho.abrir_no_app(uri, pacote, roteiro["componente"])
            with frota_aparelho.com_adbkeyboard(aparelho):
                resultado = frota_roteiro.Executor(
                    aparelho, roteiro["passos"], legenda=LEGENDA_DO_ENSAIO, ensaio=True,
                    guardar=registro.guardar, log=print).rodar()
            if resultado.ok:
                detalhe = ("O motor chegou ao botão de publicar e não tocou. O app "
                           "ficou na última tela com o vídeo de teste: saia dele sem publicar")
            else:
                detalhe = f"Parou: {resultado.motivo}"
            registro.fechar("passou" if resultado.ok else "falhou", detalhe,
                            passo=resultado.parou_em)
            return {"ok": resultado.ok, "detalhe": detalhe, "versao": versao,
                    "execucao": registro.id}
    except (FrotaErro, adb_cliente.AdbErro) as e:
        registro.fechar("falhou", str(e))
        return {"ok": False, "detalhe": str(e), "versao": None, "execucao": registro.id}
    finally:
        if no_aparelho:
            try:
                aparelho.apagar(no_aparelho)
            except adb_cliente.AdbErro:
                pass


async def ensaiar(device_id: str, plataforma: str) -> dict:
    """Comeca o ensaio do roteiro de `plataforma` neste aparelho, numa tarefa;
    o painel acompanha pelo estado do aparelho (`ensaio`)."""
    if (_ENSAIOS.get(device_id) or {}).get("estado") == "rodando":
        raise FrotaConflito("já há um ensaio rodando neste aparelho")
    async with db.tenant() as t:
        aparelho = await _linha(t, device_id)
        linhas = await t.all(db_models.DeviceScript,
                             db_models.DeviceScript.device_id == device_id,
                             db_models.DeviceScript.platform == plataforma)
        if not linhas:
            raise FrotaNaoAchou("ensine o app antes de ensaiar")
        r = linhas[0]
        roteiro = {"pacote": r.app_package, "versao": r.app_version, "componente": r.component,
                   "passos": (r.steps_json or {}).get("passos") or []}
        serial = aparelho.serial
    if frota_aparelho.ocupado_com(serial):
        raise FrotaConflito(f"o aparelho está ocupado: {frota_aparelho.ocupado_com(serial)}")
    _ENSAIOS[device_id] = {"estado": "rodando", "plataforma": plataforma,
                           "inicio": _agora().isoformat()}

    async def correr():
        try:
            resultado = await asyncio.to_thread(_ensaiar_no_aparelho, device_id, serial,
                                                plataforma, roteiro)
        except Exception as e:
            resultado = {"ok": False, "detalhe": f"{type(e).__name__}: {e}", "versao": None,
                         "execucao": None}
        await gravar_ensaio(device_id, plataforma, resultado)
        _ENSAIOS[device_id] = {"estado": "passou" if resultado["ok"] else "falhou",
                               "plataforma": plataforma, "detalhe": resultado["detalhe"],
                               "execucao": resultado.get("execucao"),
                               "fim": _agora().isoformat()}

    tarefa = asyncio.create_task(correr())
    _TAREFAS.add(tarefa)
    tarefa.add_done_callback(_TAREFAS.discard)
    return _ENSAIOS[device_id]


async def gravar_ensaio(device_id: str, plataforma: str, resultado: dict) -> None:
    try:
        async with db.tenant() as t:
            linhas = await t.all(db_models.DeviceScript,
                                 db_models.DeviceScript.device_id == device_id,
                                 db_models.DeviceScript.platform == plataforma)
            if not linhas:
                return
            linha = linhas[0]
            linha.rehearsed_at = _agora()
            linha.rehearsal_ok = bool(resultado.get("ok"))
            linha.rehearsal_detail = (resultado.get("detalhe") or "")[:1000]
            await t.commit()
    except Exception as e:
        print(f"⚠️  Frota: o resultado do ensaio não foi gravado ({e})")
