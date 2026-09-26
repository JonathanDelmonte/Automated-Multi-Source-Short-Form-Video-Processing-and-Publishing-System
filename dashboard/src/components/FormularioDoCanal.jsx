import React, { useEffect, useRef, useState } from 'react';
import { AlertTriangle, Check, ImagePlus, Loader2, Plus, RotateCcw, ShieldCheck, X, Zap } from 'lucide-react';
import AvatarDoCanal from './ui/AvatarDoCanal';
import IconePlataforma from './ui/IconePlataforma';
import { Secao } from './ui/Pagina';
import { apiFetch } from '../lib/api';
import { CORES_DO_CANAL, IDIOMAS, NICHOS_SUGERIDOS, reduzirImagem, salvarCanal } from '../lib/canais';
import { ORDEM_DAS_PLATAFORMAS, PLATAFORMAS } from '../lib/plataformas';
import { usePainel } from '../lib/painel';

// Criar e editar um canal (etapa 7.1): a identidade, as contas de cada
// plataforma e se ele espera aprovação antes de postar.
//
// **A aprovação nasce sem resposta.** "Quem escolhe isso é o usuário" (o autor,
// 26-set-2026): nenhuma das duas vem marcada, e o botão de criar só acende
// depois da escolha. O motor recusa do mesmo jeito (`requires_approval` é
// obrigatório ao criar), então a regra não depende só desta tela.
//
// **Conta de outro canal muda de canal.** Uma conta pertence a um canal só; o
// cartão dela diz de qual ela vem antes de a pessoa salvar.

function Opcao({ ativo, onClick, icone, titulo, texto }) {
  const Icone = icone;
  return (
    <button
      type="button"
      role="radio"
      aria-checked={ativo}
      onClick={onClick}
      className={`flex items-start gap-3 p-3.5 rounded-input border text-left transition-colors ${
        ativo ? 'border-[color:var(--color-accent)] bg-paper3' : 'border-rule2 hover:border-[color:var(--color-accent)]'}`}
    >
      <Icone size={18} className={`shrink-0 mt-0.5 ${ativo ? 'text-ink' : 'text-muted'}`} />
      <span className="min-w-0">
        <span className="block text-sm text-ink font-medium">{titulo}</span>
        <span className="block text-[13px] text-muted leading-snug mt-0.5">{texto}</span>
      </span>
    </button>
  );
}

export default function FormularioDoCanal({ canal = null, aoSalvar, aoCancelar }) {
  const { canais } = usePainel();
  const editando = !!canal;
  const [nome, setNome] = useState(canal?.name || '');
  const [nicho, setNicho] = useState(canal?.niche || '');
  const [avatar, setAvatar] = useState(canal?.avatar || null);
  // Um canal novo nasce com uma cor da paleta, sorteada -- o cinza do fim fica
  // de fora do sorteio, e continua escolhível.
  const [cor, setCor] = useState(
    () => canal?.color || CORES_DO_CANAL[Math.floor(Math.random() * (CORES_DO_CANAL.length - 1))]);
  const [idioma, setIdioma] = useState(canal?.language || 'pt-BR');
  const [aprovacao, setAprovacao] = useState(editando ? !!canal.requires_approval : null);
  const [contas, setContas] = useState(null);
  const [selecionadas, setSelecionadas] = useState(() => new Set((canal?.contas || []).map((c) => c.id)));
  const [novas, setNovas] = useState([]);
  const [novaPlataforma, setNovaPlataforma] = useState('youtube');
  const [novoHandle, setNovoHandle] = useState('');
  const [aviso, setAviso] = useState(null);
  const [erro, setErro] = useState(null);
  const [salvando, setSalvando] = useState(false);
  const [lendoImagem, setLendoImagem] = useState(false);
  const arquivo = useRef(null);

  useEffect(() => {
    let vivo = true;
    (async () => {
      try {
        const res = await apiFetch('/api/contas');
        const data = res.ok ? await res.json() : {};
        if (vivo) setContas(data.contas || []);
      } catch {
        if (vivo) setContas([]);
      }
    })();
    return () => { vivo = false; };
  }, []);

  const escolherImagem = async (e) => {
    const escolhido = e.target.files?.[0];
    e.target.value = '';
    if (!escolhido) return;
    setLendoImagem(true);
    setErro(null);
    try {
      setAvatar(await reduzirImagem(escolhido));
    } catch (err) {
      setErro(err?.message || 'Não consegui ler essa imagem.');
    } finally {
      setLendoImagem(false);
    }
  };

  const alternar = (id) => {
    setSelecionadas((atual) => {
      const nova = new Set(atual);
      if (nova.has(id)) nova.delete(id);
      else nova.add(id);
      return nova;
    });
  };

  const acrescentar = () => {
    const handle = novoHandle.trim();
    if (!handle) return;
    const igual = (a) => a.platform === novaPlataforma && a.handle.toLowerCase() === handle.toLowerCase();
    // A conta já cadastrada não vira outra: é marcada, que é o que a pessoa quis.
    const existente = (contas || []).find(igual);
    if (existente) {
      setSelecionadas((atual) => new Set(atual).add(existente.id));
      setAviso(`${existente.handle} já estava cadastrada: marquei ela acima.`);
    } else if (novas.some(igual)) {
      setAviso('Essa conta já está na lista.');
    } else {
      setNovas((atual) => [...atual, { platform: novaPlataforma, handle }]);
      setAviso(null);
    }
    setNovoHandle('');
  };

  const salvar = async (e) => {
    e.preventDefault();
    if (!nome.trim()) {
      setErro('Dê um nome ao canal.');
      return;
    }
    if (aprovacao === null) {
      setErro('Escolha se o canal espera a sua aprovação antes de postar.');
      return;
    }
    setSalvando(true);
    setErro(null);
    const r = await salvarCanal(canal?.id, {
      name: nome.trim(),
      niche: nicho.trim() || null,
      avatar,
      color: cor,
      language: idioma,
      requires_approval: aprovacao,
      contas: [...selecionadas],
      novas_contas: novas,
    });
    setSalvando(false);
    if (!r.ok) {
      setErro(r.erro);
      return;
    }
    await canais.carregar();
    if (aoSalvar) aoSalvar(r.data);
  };

  const previa = { name: nome || '?', avatar, color: cor };
  // As contas deste canal primeiro, depois as soltas, e por último as que estão
  // em outro canal -- que são as que menos se quer marcar aqui.
  const peso = (c) => (c.channel_id && c.channel_id === canal?.id ? 0 : c.channel_id ? 2 : 1);
  const ordenadas = [...(contas || [])].sort((a, b) => peso(a) - peso(b));

  return (
    <form onSubmit={salvar} className="space-y-5">
      <Secao titulo="identidade">
        <div className="flex flex-col sm:flex-row gap-5">
          <div className="flex flex-col items-center gap-2.5 shrink-0">
            <AvatarDoCanal canal={previa} size={96} />
            <div className="flex flex-wrap justify-center gap-1.5">
              <button
                type="button"
                onClick={() => arquivo.current?.click()}
                className="btn-quiet px-3 py-1 text-xs"
                disabled={lendoImagem}
              >
                {lendoImagem ? <Loader2 size={13} className="animate-spin" /> : <ImagePlus size={13} />}
                imagem
              </button>
              {avatar && (
                <button type="button" onClick={() => setAvatar(null)} className="btn-quiet px-3 py-1 text-xs" title="usar as iniciais">
                  <RotateCcw size={13} /> iniciais
                </button>
              )}
            </div>
            <input ref={arquivo} type="file" accept="image/*" className="hidden" onChange={escolherImagem} />
          </div>

          <div className="flex-1 min-w-0 space-y-3.5">
            <label className="block">
              <span className="eyebrow">nome</span>
              <input
                className="input-field mt-1.5"
                maxLength={80}
                value={nome}
                onChange={(e) => setNome(e.target.value)}
                placeholder="Ex.: Canal infantil"
                autoFocus={!editando}
              />
            </label>
            <label className="block">
              <span className="eyebrow">nicho</span>
              <input
                className="input-field mt-1.5"
                maxLength={80}
                list="nichos-do-canal"
                value={nicho}
                onChange={(e) => setNicho(e.target.value)}
                placeholder="Ex.: infantil, finanças, fatos desconhecidos"
              />
              <datalist id="nichos-do-canal">
                {NICHOS_SUGERIDOS.map((n) => <option key={n} value={n} />)}
              </datalist>
            </label>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
              <div>
                <span className="eyebrow">cor</span>
                <div className="flex flex-wrap items-center gap-1.5 mt-2">
                  {CORES_DO_CANAL.map((c) => (
                    <button
                      key={c}
                      type="button"
                      onClick={() => setCor(c)}
                      aria-label={`cor ${c}`}
                      aria-pressed={cor === c}
                      className={`w-7 h-7 rounded-full transition-transform ${cor === c ? 'ring-2 ring-offset-2 ring-offset-[color:var(--color-paper-2)] ring-[color:var(--color-accent)] scale-105' : 'hover:scale-105'}`}
                      style={{ background: c }}
                    />
                  ))}
                  <label
                    className="relative w-7 h-7 rounded-full border border-dashed border-rule2 flex items-center justify-center text-muted hover:text-ink cursor-pointer overflow-hidden"
                    title="outra cor"
                  >
                    <Plus size={13} />
                    <input
                      type="color"
                      value={cor}
                      onChange={(e) => setCor(e.target.value)}
                      className="absolute inset-0 opacity-0 cursor-pointer"
                      aria-label="outra cor"
                    />
                  </label>
                </div>
              </div>
              <label className="block">
                <span className="eyebrow">idioma dos vídeos</span>
                <select className="input-field mt-1.5" value={idioma} onChange={(e) => setIdioma(e.target.value)}>
                  {IDIOMAS.map((i) => <option key={i.id} value={i.id}>{i.nome}</option>)}
                </select>
              </label>
            </div>
          </div>
        </div>
      </Secao>

      <Secao titulo="contas do canal">
        <p className="text-muted text-[13px] leading-snug">
          O mesmo canal no YouTube, no TikTok e no Instagram: cada conta ligada é um galho por onde os
          cortes saem. Uma conta pertence a um canal só.
        </p>
        {contas === null ? (
          <Loader2 size={16} className="animate-spin text-muted" />
        ) : contas.length > 0 && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {ordenadas.map((c) => {
              const marcada = selecionadas.has(c.id);
              const outro = c.channel_id && c.channel_id !== canal?.id ? canais.porId[c.channel_id] : null;
              let legenda = PLATAFORMAS[c.platform]?.nome || c.platform;
              if (marcada) legenda = outro ? `vem do canal ${outro.name}` : 'neste canal';
              else if (outro) legenda = `no canal ${outro.name}`;
              return (
                <button
                  key={c.id}
                  type="button"
                  onClick={() => alternar(c.id)}
                  aria-pressed={marcada}
                  className={`flex items-center gap-2.5 p-2.5 rounded-input border text-left transition-colors ${
                    marcada ? 'border-[color:var(--color-accent)] bg-paper3' : 'border-rule2 hover:border-[color:var(--color-accent)]'}`}
                >
                  <IconePlataforma platform={c.platform} size={20} />
                  <span className="min-w-0 flex-1">
                    <span className="block text-sm text-ink truncate">{c.handle}</span>
                    <span className={`block text-[11px] truncate ${marcada && outro ? 'text-warn' : 'text-muted'}`}>{legenda}</span>
                  </span>
                  <span className={`w-5 h-5 rounded-full border flex items-center justify-center shrink-0 ${
                    marcada ? 'bg-brass border-transparent text-brassink' : 'border-rule2'}`}>
                    {marcada && <Check size={12} />}
                  </span>
                </button>
              );
            })}
          </div>
        )}

        {novas.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {novas.map((n, i) => (
              <span key={`${n.platform}-${n.handle}`} className="inline-flex items-center gap-1.5 pl-2 pr-1 py-1 rounded-full bg-paper3 text-sm text-ink2">
                <IconePlataforma platform={n.platform} size={16} />
                {n.handle}
                <span className="readout">nova</span>
                <button
                  type="button"
                  onClick={() => setNovas((atual) => atual.filter((_, j) => j !== i))}
                  aria-label={`tirar ${n.handle}`}
                  className="p-1 rounded-full text-muted hover:text-ink"
                >
                  <X size={12} />
                </button>
              </span>
            ))}
          </div>
        )}

        <div className="flex flex-wrap items-center gap-2">
          <div role="radiogroup" aria-label="plataforma da conta nova" className="flex rounded-full border border-rule2 p-0.5">
            {ORDEM_DAS_PLATAFORMAS.map((p) => (
              <button
                key={p}
                type="button"
                role="radio"
                aria-checked={novaPlataforma === p}
                onClick={() => setNovaPlataforma(p)}
                title={PLATAFORMAS[p].nome}
                className={`p-1.5 rounded-full transition-colors ${novaPlataforma === p ? 'bg-paper3' : 'text-muted hover:text-ink2'}`}
              >
                <IconePlataforma platform={p} size={18} mono={novaPlataforma !== p} />
              </button>
            ))}
          </div>
          <input
            className="input-field !py-1.5 flex-1 min-w-[10rem]"
            placeholder={`@ da conta no ${PLATAFORMAS[novaPlataforma].nome}`}
            value={novoHandle}
            maxLength={100}
            onChange={(e) => setNovoHandle(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                acrescentar();
              }
            }}
          />
          <button type="button" className="btn-quiet px-3 py-1.5 text-sm" onClick={acrescentar} disabled={!novoHandle.trim()}>
            <Plus size={14} /> adicionar
          </button>
        </div>
        {aviso && <p className="text-muted text-[12px]">{aviso}</p>}
        <p className="text-muted text-[12px] leading-snug">
          Ligar a conta aqui diz ao Virtu Clips que ela é deste canal. Para a conta do YouTube postar
          sozinha, conecte-a na visão geral do canal (depois do cadastro do aplicativo, em
          Configurações); sem conectar, os cortes saem prontos para você colar.
        </p>
      </Secao>

      <Secao titulo="antes de postar">
        <div role="radiogroup" aria-label="aprovação antes de postar" className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          <Opcao
            ativo={aprovacao === true}
            onClick={() => setAprovacao(true)}
            icone={ShieldCheck}
            titulo="eu reviso antes"
            texto="Cada corte espera a sua aprovação antes de sair. Bom para canal novo e para nicho sensível, como o infantil."
          />
          <Opcao
            ativo={aprovacao === false}
            onClick={() => setAprovacao(false)}
            icone={Zap}
            titulo="pode postar sozinho"
            texto="Os cortes saem nos horários do canal sem esperar por você."
          />
        </div>
        <p className="text-muted text-[12px] leading-snug">
          {aprovacao === null && !editando
            ? 'Escolha uma das duas: quem decide é você, e dá para mudar depois nos ajustes do canal. '
            : ''}
          A automação chega na etapa 7.5; a escolha fica guardada desde já.
        </p>
      </Secao>

      {erro && (
        <p className="flex items-start gap-2 text-sm text-danger">
          <AlertTriangle size={15} className="shrink-0 mt-0.5" /> {erro}
        </p>
      )}

      <div className="flex flex-col-reverse sm:flex-row sm:justify-end gap-2">
        {aoCancelar && (
          <button type="button" className="btn-ghost" onClick={aoCancelar}>cancelar</button>
        )}
        <button type="submit" className="btn-primary" disabled={salvando || !nome.trim() || aprovacao === null}>
          {salvando ? <Loader2 size={15} className="animate-spin" /> : <Check size={15} />}
          {editando ? 'salvar' : 'criar canal'}
        </button>
      </div>
    </form>
  );
}
