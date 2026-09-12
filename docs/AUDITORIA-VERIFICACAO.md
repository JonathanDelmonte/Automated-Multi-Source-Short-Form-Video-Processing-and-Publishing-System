# Auditoria de verificação do Plano Técnico

**Data da verificação:** 12 de setembro de 2026
**Objeto:** `docs/PLANO-TECNICO.md` v2
**Método:** consulta direta aos repositórios e à documentação dos provedores citados.

O Plano Técnico v2 foi escrito em estado pré-código e pede explicitamente confirmação
de dois pontos antes de codar ("confirme antes de codar, isso muda toda hora", §3).
Este documento registra o que a verificação encontrou. **Oito itens divergem** do
documento original; quatro deles mudam o plano de ação.

Os itens 1 a 7 vêm da auditoria documental, anterior a qualquer código. O item 8 foi
encontrado durante a execução da Fase 0.1 e está registrado aqui por pertencer ao mesmo
assunto.

---

## Resumo das divergências

| # | O documento afirma | Verificado | Impacto |
|---|---|---|---|
| 1 | "Fork de projeto MIT existente", "quatro candidatos, todos MIT" | `openshorts` é MIT **com exceção**: o diretório `cloud/` está sob *OpenShorts Commercial License* | **Alto** — bloqueia SaaS |
| 2 | `openshorts` 2.4k ★ · 669 forks | ~4.0k ★ · ~1.0k forks, e é ele mesmo um fork de `kamilstanuch/Autocrop-vertical` | Baixo — veredito se mantém |
| 3 | `clippyme` é repositório doador, "portar os módulos bons" | `clippyme` **é um fork do `openshorts`** | **Alto** — barateia a Fase 2 |
| 4 | YOLOv8/AGPL é "decisão em aberto" (§10) | `openshorts` **já embarca** YOLOv8 (Ultralytics) hoje | **Alto** — passivo herdado |
| 5 | Groq: "30 RPM, 1.000/dia — cobre com folga" | Também há teto de **100.000 tokens/dia** | **Alto** — inverte a conclusão |
| 6 | `clippyme` 0 ★ · 473 commits | 36 ★ · 611 commits | Baixo |
| 7 | `clippyme` como doador de stack gratuita | `clippyme` usa Deepgram e ElevenLabs Scribe (pagos) na transcrição | Médio — filtrar ao portar |
| 8 | §7 fala em "levar o schema herdado" ao desenho multi-tenant | **não há schema no caminho MIT** — todo o ORM era do módulo comercial | **Alto** — muda a Fase 0.5 |

Confirmados sem divergência: limite de upload de 2GB do `openshorts`; custo de
1.600 unidades do `videos.insert` contra 10.000 unidades/dia gratuitas do YouTube
(3 vídeos/dia = 4.800 un., a conta do §1 está correta); exigência de auditoria da
TikTok Content Posting API; existência dos quatro repositórios auditados.

---

## 1. A base não é MIT puro — há um carve-out comercial

O arquivo `LICENSE` do `openshorts` diz, textualmente:

> "EXCEPTION: All content that resides under the 'cloud/' directory of this
> repository is licensed under the license defined in 'cloud/LICENSE' (the
> OpenShorts Commercial License), not under the MIT License below."

E a licença comercial do `cloud/` é source-available com restrição de revenda:
você pode ler, modificar e auto-hospedar para uso pessoal ou interno, mas **não pode
oferecer a terceiros como serviço pago ou hospedado**.

Para o uso declarado na fase inicial — self-hosted, pessoal — isso não dispara. O
problema é que o próprio Plano Técnico projeta a virada para SaaS em três seções
distintas (§3 nota de licença, §7 multi-tenancy, §8 risco de ToS). Se o código do
`cloud/` entrar no fork e o projeto depois virar serviço hospedado pago, é violação
de licença — e a essa altura estará entrelaçado no código.

**Ação:** `git rm -r cloud/` no primeiro commit do fork, antes de qualquer outra
alteração, e registrar a remoção no `NOTICE`. Custo agora: dez minutos. Custo depois:
auditoria de licença no código inteiro.

## 2. A base é ela mesma um fork

`openshorts` descende de `kamilstanuch/Autocrop-vertical`. Não muda o veredito do
§2 — a tração de ~4.0k estrelas e ~1.0k forks continua sendo o ativo que justifica
a escolha, e o número cresceu desde a redação do documento. Serve para arqueologia
de bug: quando algo em `ffmpeg` ou tracking de rosto parecer inexplicável, o
histórico do upstream original é onde a correção pode já existir.

## 3. `clippyme` é fork do `openshorts`, não um repositório estranho

O README do `clippyme` se descreve como "Fork of OpenShorts, hardened and extended:
cloud-or-local transcription, Gemini viral-moment detection, active-speaker 9:16
reframing, **compose-on-download editing**, and one-click multi-platform scheduling".

Isto é a melhor notícia da auditoria. O §2 do Plano Técnico elege como principal
aquisição do `clippyme` exatamente o "truque de aplicar legenda e logo *na hora do
download*, sem reprocessar o vídeo" — e chama de "a melhor ideia de arquitetura dos
quatro". O documento assume que isso será **portado manualmente**.

Sendo fork da mesma base, não é porte: é operação de git. Adiciona-se o `clippyme`
como segundo remote e comparam-se árvores com ancestral comum, em vez de reescrever
módulo lendo código alheio.

```bash
git remote add clippyme https://github.com/fralapo/clippyme.git
git fetch clippyme
git merge-base HEAD clippyme/main          # o ancestral comum existe
git diff HEAD...clippyme/main -- <caminho do compositor>
```

Confirmado no README do `clippyme` que a técnica é real e já otimizada: camadas
adjacentes são fundidas em passes compartilhados de `ffmpeg` ("grade+subtitles in
one, hook+logo in one"), resultando em 3 encodes em vez de 5 numa composição
completa. Os 6 presets de legenda citados no §2 existem: `classic_white`,
`hormozi_bold`, `neon_glow`, `mrbeast_box`, `minimal_clean`, `fire_impact`.

**Ação:** a Fase 2 deixa de ser "~2 semanas escrevendo motor de template" e passa a
ser cherry-pick assistido mais o schema JSON próprio do §5. Estimativa cai para
cerca de uma semana.

## 4. O YOLOv8 já está dentro — a decisão não está mais em aberto

O §10 lista como decisão pendente "se o tracking de rosto usa MediaPipe puro desde o
início, evitando a AGPL do YOLOv8". A verificação mostra que a stack do `openshorts`
hoje é Python 3.11, FastAPI, google-genai, faster-whisper, **YOLOv8**, MediaPipe,
OpenCV, yt-dlp, FFmpeg. O `clippyme` também traz YOLOv8 (Ultralytics).

Ou seja: o passivo AGPL-3.0 entra no repositório no minuto do fork, sem ninguém
decidir nada. E o próprio §3 do Plano Técnico já diagnosticou o custo disso —
"essa escolha fica mais cara de desfazer depois de estar no código inteiro".
A janela barata para decidir é agora, não depois.

**Ação:** ver `docs/DECISOES.md`, ADR-003.

## 5. O gargalo do Groq é token, não requisição

O §3 do Plano Técnico registra o Groq como "30 RPM, 1.000 por dia, 128k contexto" e
conclui: "1.000/dia cobre com folga, e a velocidade encurta o job inteiro". A tabela
está incompleta. O free tier do Llama 3.3 70B no Groq tem, além disso:

- **12.000 tokens por minuto**
- **100.000 tokens por dia**

O teto diário de tokens é o que aperta primeiro, e com folga. Estimativa para o pior
caso que o próprio plano elege como alvo da Fase 1 (live de 4h da Twitch):

| Grandeza | Estimativa | Base |
|---|---|---|
| Fala em 4h | ~34.000–38.000 palavras | 140–160 palavras/min, conversacional |
| Transcrição tokenizada | ~58.000 tokens | ~1,7 tok/palavra (português tokeniza pior que inglês) |
| Com janelas de 20% de sobreposição (§3) | ~70.000 tokens | ×1,2 |
| Somado o scaffolding de prompt e rubrica por janela | ~75.000+ tokens | — |

Contra um teto de 100.000 tokens/dia: **uma única live de 4h consome de 60% a 75% do
orçamento diário inteiro do Groq.** A segunda live do dia não roda. As 1.000
requisições/dia nunca chegam a ser tocadas — são irrelevantes.

São estimativas com as premissas à vista, não medição; a ordem de grandeza é o que
importa e ela é inequívoca. Consequência direta: o pré-filtro heurístico do §3, que
o §10 deixou como "entra já na fase 0 ou só quando o rate limit apertar", **já está
apertado por construção** no caso de uso alvo. E a ordem da cascata precisa depender
da duração da fonte, não ser fixa.

**Ação:** ver `docs/DECISOES.md`, ADR-004 e ADR-005.

## 6. Ao portar do `clippyme`, filtrar a transcrição paga

A stack de pipeline do `clippyme` é `yt-dlp` · **Deepgram REST** · **ElevenLabs
Scribe REST** · Faster-Whisper · PySceneDetect · YOLOv8 · MediaPipe · ffmpeg ·
auto-editor · Pillow. Deepgram e ElevenLabs Scribe são pagos e violam a restrição de
custo zero do Plano Técnico.

Não é impedimento — o `faster-whisper` está lá junto e é o caminho que o §3 escolhe.
É um alerta de que o cherry-pick do item 3 precisa ser seletivo: trazer o compositor
e os presets de legenda, deixar os caminhos de transcrição paga para trás.

## 8. Não existe banco de dados no caminho self-host

*Encontrado durante a execução da Fase 0.1, não na auditoria documental.*

O §7 do plano define nove tabelas e o §9 trata multi-tenancy como adaptação de algo
existente. Na prática, o caminho MIT do upstream não persiste nada em banco:

- `sqlalchemy`, `asyncpg` e `alembic` aparecem só no `requirements-billing.txt`,
  nunca no `requirements.txt`.
- O `docker-compose.yml` do self-host não declara serviço de banco. O Postgres existe
  apenas no `docker-compose.cloud.yml`.
- Todo o ORM morava em `cloud.models`, e o `alembic/env.py` se identificava como
  ambiente "for cloud-mode migrations", com `versions/` vazio.

A camada de persistência inteira pertencia ao módulo comercial e saiu com ele na
remoção da ADR-001.

**Consequência:** a Fase 0.5 deixa de ser migração e passa a ser autoria. Ver ADR-008,
seção de revisão. O efeito líquido é favorável — não há migração que quebre, e o
`tenant_id` entra na primeira tabela escrita —, mas a fase cresce de 2–3 para 3–5 dias.

## 7. Aviso de segurança do `clippyme` confirmado

O §2 registra que "o clippyme avisa explicitamente que só deve rodar em LAN
confiável". Confirmado: a documentação diz para não expor à internet pública sem um
reverse proxy terminando TLS na frente, e classifica o projeto como adequado a
"trusted LAN deployment". Reforça a Fase 4 (auth) como pré-requisito de qualquer
exposição, não como refinamento.

---

## Fontes

- [mutonby/openshorts](https://github.com/mutonby/openshorts) e seu [LICENSE](https://github.com/mutonby/openshorts/blob/main/LICENSE)
- [fralapo/clippyme](https://github.com/fralapo/clippyme)
- [NaufalRizqullah/opensource-clipping](https://github.com/NaufalRizqullah/opensource-clipping)
- [artbyjazi/autoclip](https://github.com/artbyjazi/autoclip)
- Limites do free tier do Groq: [TokenMix](https://tokenmix.ai/blog/groq-free-tier-limits-2026), [Grizzly Peak Software](https://www.grizzlypeaksoftware.com/articles/p/groq-api-free-tier-limits-in-2026-what-you-actually-get-uwysd6mb), [Price Per Token](https://pricepertoken.com/endpoints/groq/free)

> Os limites de free tier de LLM mudam sem aviso. Reconfirmar antes da Fase 0,
> conforme o próprio Plano Técnico determina.
