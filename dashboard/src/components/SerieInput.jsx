import React, { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, CalendarClock, ChevronDown, FileVideo, Link2, Loader2, Radio, Upload, X } from 'lucide-react';
import SegmentedControl from './ui/SegmentedControl';
import {
  BLOCOS, BLOCO_PADRAO, DURACAO_PADRAO, DURACOES, ESTILOS, ROTULOS,
  corpoDaSerie, duracaoEmTexto, ehLiveDaTwitch, formatarTempo, previsao, problemaDoTrecho, lerTempo,
} from '../lib/serie';

// O formulário da série em partes (etapa 7.6): "pego uma live, colo, e ele
// divide em vários clipes de um minuto (...) parte 1, parte 2" (o autor,
// 25-set-2026). O motor corta o vídeo INTEIRO, na ordem, nas pausas da fala;
// nenhuma IA escolhe trecho, então a série não pede chave de IA.
//
// O link vem primeiro (é o caso do autor); o arquivo tem a vantagem de o
// navegador ler a duração dele e dizer, antes de enviar, quantas partes vão
// sair.

function lerDuracao(arquivo, aoLer) {
  try {
    const endereco = URL.createObjectURL(arquivo);
    const video = document.createElement('video');
    video.preload = 'metadata';
    video.onloadedmetadata = () => {
      aoLer(Number.isFinite(video.duration) ? video.duration : null);
      URL.revokeObjectURL(endereco);
    };
    video.onerror = () => { aoLer(null); URL.revokeObjectURL(endereco); };
    video.src = endereco;
  } catch {
    aoLer(null);
  }
}

export default function SerieInput({ onProcess, isProcessing, canalId = null, canalNome = null, motorAntigo = false }) {
  const [modo, setModo] = useState('url');
  const [url, setUrl] = useState('');
  const [arquivo, setArquivo] = useState(null);
  const [duracaoDoArquivo, setDuracaoDoArquivo] = useState(null);
  const [nome, setNome] = useState('');
  const [duracao, setDuracao] = useState(DURACAO_PADRAO);
  const [rotulo, setRotulo] = useState('inicio');
  const [estilo, setEstilo] = useState('classic');
  const [bloco, setBloco] = useState(BLOCO_PADRAO);
  const [trechoAberto, setTrechoAberto] = useState(false);
  const [inicio, setInicio] = useState('');
  const [fim, setFim] = useState('');
  // Com canal, a série já sai agendada: é o "pronto quando" da etapa.
  const [agendar, setAgendar] = useState(!!canalId);
  const [layout, setLayout] = useState(() => {
    try { return localStorage.getItem('os_layout') || 'auto'; } catch { return 'auto'; }
  });
  const [confirmado, setConfirmado] = useState(false);

  useEffect(() => { setAgendar(!!canalId); }, [canalId]);
  useEffect(() => {
    setDuracaoDoArquivo(null);
    if (arquivo) lerDuracao(arquivo, setDuracaoDoArquivo);
  }, [arquivo]);

  const live = modo === 'url' && ehLiveDaTwitch(url);
  const problema = problemaDoTrecho(inicio, fim);
  const conta = useMemo(() => (modo === 'file' && duracaoDoArquivo
    ? previsao(duracaoDoArquivo, duracao, lerTempo(inicio), lerTempo(fim))
    : null), [modo, duracaoDoArquivo, duracao, inicio, fim]);
  const temFonte = modo === 'url' ? !!url.trim() : !!arquivo;
  const pode = temFonte && confirmado && !problema && !conta?.erro && !isProcessing && !motorAntigo;

  const enviar = (e) => {
    e.preventDefault();
    if (!pode) return;
    try { localStorage.setItem('os_layout', layout); } catch { /* sem armazenamento */ }
    onProcess({
      type: modo,
      payload: modo === 'url' ? url.trim() : arquivo,
      acknowledged: true,
      outputFormat: 'vertical',
      layout,
      serie: corpoDaSerie({ nome, duracao, rotulo, estilo, inicio, fim,
                            agendar: agendar && !!canalId, bloco: live ? bloco : null }),
    });
  };

  const aba = (valor, Icone, texto) => (
    <button
      type="button"
      onClick={() => setModo(valor)}
      className={`flex items-center gap-2 pb-3 px-1 -mb-px border-b-2 text-sm lowercase whitespace-nowrap transition-colors ${modo === valor
        ? 'text-ink border-brass' : 'text-muted border-transparent hover:text-ink2'}`}
    >
      <Icone size={16} className={`hidden sm:block ${modo === valor ? 'text-brass' : ''}`} />
      {texto}
    </button>
  );

  return (
    <form className="card p-4 sm:p-6 space-y-5 animate-fade" onSubmit={enviar}>
      <div className="flex gap-4 sm:gap-6 border-b border-rule">
        {aba('url', Link2, 'link do vídeo')}
        {aba('file', Upload, 'enviar arquivo')}
      </div>

      {modo === 'url' ? (
        <div className="space-y-2">
          <input
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://… o link da live ou do vídeo longo"
            className="input-field"
            aria-label="link do vídeo"
          />
          {live && (
            <div className="space-y-2 pt-1" data-live-no-ar>
              <p className="text-[12px] text-ink2 flex items-center gap-1.5">
                <Radio size={13} className="text-danger shrink-0" /> live da Twitch no ar: grava por até
              </p>
              <SegmentedControl
                size="sm"
                options={BLOCOS.map((m) => ({ value: m, label: m < 60 ? `${m} min` : `${m / 60} h`.replace('.5 h', ' h 30') }))}
                value={bloco}
                onChange={setBloco}
              />
              <p className="text-[11px] text-muted leading-snug">
                A gravação começa agora e para no fim do bloco, ou quando a live acabar. Para a live inteira desde o
                começo, use o link do vídeo salvo depois que ela terminar.
              </p>
            </div>
          )}
        </div>
      ) : (
        <div
          className={`border-2 border-dashed rounded-card p-5 sm:p-7 text-center transition-colors ${arquivo ? 'border-brass' : 'border-rule2 hover:border-brass'}`}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => { e.preventDefault(); if (e.dataTransfer.files?.[0]) setArquivo(e.dataTransfer.files[0]); }}
        >
          {arquivo ? (
            <div className="flex items-center justify-center gap-3 text-ok min-w-0">
              <FileVideo size={18} className="shrink-0" />
              <span className="font-medium truncate">{arquivo.name}</span>
              {duracaoDoArquivo && <span className="readout shrink-0">{formatarTempo(duracaoDoArquivo)}</span>}
              <button type="button" onClick={() => setArquivo(null)} aria-label="tirar o arquivo"
                      className="p-1 text-muted hover:text-ink hover:bg-paper3 rounded-full transition-colors">
                <X size={16} />
              </button>
            </div>
          ) : (
            <label className="cursor-pointer block">
              <input type="file" accept="video/*" className="hidden"
                     onChange={(e) => setArquivo(e.target.files?.[0] || null)} />
              <Upload className="mx-auto mb-3 text-muted" size={18} />
              <p className="text-ink2 lowercase">clique para enviar ou arraste o vídeo aqui</p>
            </label>
          )}
        </div>
      )}

      <div className="space-y-1.5">
        <label className="eyebrow block" htmlFor="nome-da-serie">nome da série</label>
        <input
          id="nome-da-serie"
          value={nome}
          onChange={(e) => setNome(e.target.value)}
          maxLength={80}
          placeholder="em branco, vale o título do vídeo"
          className="input-field"
        />
        <p className="text-[11px] text-muted">Cada parte sai como “{(nome.trim() || 'Nome') } - Parte 1”, “Parte 2”…</p>
      </div>

      <div className="space-y-2">
        <p className="eyebrow">cada parte com cerca de</p>
        <SegmentedControl
          size="sm"
          options={DURACOES.map((s) => ({ value: s, label: duracaoEmTexto(s) }))}
          value={duracao}
          onChange={setDuracao}
        />
        <p className="text-[11px] text-muted leading-snug">
          {conta?.texto
            ? <>O vídeo vira <span className="text-ink2">{conta.texto}</span>, cortadas nas pausas da fala.</>
            : conta?.erro
              ? <span className="text-danger">{conta.erro}</span>
              : 'As partes cobrem o vídeo inteiro, sem buraco e sem repetir, cortadas nas pausas da fala: uma live de 1 hora dá 60 partes de 1 min.'}
        </p>
      </div>

      <div className="space-y-2">
        <p className="eyebrow">“parte n” no vídeo</p>
        <SegmentedControl size="sm" minColPx={96} options={ROTULOS} value={rotulo} onChange={setRotulo} />
        {rotulo !== 'nao' && (
          <select value={estilo} onChange={(e) => setEstilo(e.target.value)}
                  className="input-field !w-auto text-xs py-1.5" aria-label="estilo do rótulo">
            {ESTILOS.map((e) => <option key={e.value} value={e.value}>{e.label}</option>)}
          </select>
        )}
      </div>

      <div>
        <button type="button" onClick={() => setTrechoAberto((v) => !v)}
                className="flex items-center gap-1.5 text-xs text-muted hover:text-ink2 lowercase transition-colors">
          <ChevronDown size={14} className={`transition-transform ${trechoAberto ? 'rotate-180' : ''}`} />
          só um trecho do vídeo
          {(inicio || fim) && <span className="text-brass">·</span>}
        </button>
        {trechoAberto && (
          <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-3 animate-fade">
            <label className="space-y-1.5">
              <span className="eyebrow block">começar em</span>
              <input value={inicio} onChange={(e) => setInicio(e.target.value)} placeholder="0:00"
                     className="input-field" inputMode="numeric" />
            </label>
            <label className="space-y-1.5">
              <span className="eyebrow block">terminar em</span>
              <input value={fim} onChange={(e) => setFim(e.target.value)} placeholder="o fim do vídeo"
                     className="input-field" inputMode="numeric" />
            </label>
            <p className="sm:col-span-2 text-[11px] text-muted leading-snug">
              Para pular a tela de “já começa” de uma live, por exemplo. Como 1:30 ou 1:02:30.
            </p>
            {problema && <p className="sm:col-span-2 text-[12px] text-danger">{problema}</p>}
          </div>
        )}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 pt-3 border-t border-rule">
        <span className="text-xs text-ink2">enquadramento vertical</span>
        <select value={layout} onChange={(e) => setLayout(e.target.value)}
                className="input-field !w-auto text-xs py-1.5" aria-label="enquadramento vertical">
          <option value="auto">automático (a IA escolhe por vídeo)</option>
          <option value="split">duas pessoas, uma em cima da outra</option>
          <option value="screencast">tela em cima, quem apresenta embaixo</option>
          <option value="none">só um recorte</option>
        </select>
      </div>

      {canalId ? (
        <label className="flex items-start gap-2.5 text-[13px] sm:text-xs text-ink2 cursor-pointer select-none">
          <input type="checkbox" checked={agendar} onChange={(e) => setAgendar(e.target.checked)}
                 className="mt-0.5 w-4 h-4 shrink-0 accent-[var(--color-accent)] cursor-pointer" />
          <span className="flex items-start gap-1.5">
            <CalendarClock size={14} className="shrink-0 mt-px text-muted" />
            <span>
              Agendar no canal {canalNome ? <span className="text-ink">{canalNome}</span> : ''} quando ficar pronta: as
              partes entram na agenda dele, na ordem, uma por janela.
            </span>
          </span>
        </label>
      ) : (
        <p className="text-[12px] text-muted">
          Sem canal, a série fica no projeto, e você agenda de lá. Escolha um canal acima para ela entrar na agenda
          sozinha quando ficar pronta.
        </p>
      )}

      <label className="flex items-start gap-2.5 text-left text-[13px] sm:text-xs leading-relaxed text-muted cursor-pointer select-none">
        <input type="checkbox" checked={confirmado} onChange={(e) => setConfirmado(e.target.checked)}
               className="mt-0.5 w-4 h-4 shrink-0 accent-[var(--color-accent)] cursor-pointer" />
        <span>
          Confirmo que posso publicar este vídeo em partes: é meu, tem licença livre (Creative Commons ou domínio
          público) ou tenho autorização. Vídeo com direitos autorais de outra pessoa leva reclamação ou strike no canal.
        </span>
      </label>

      {motorAntigo && (
        // O site é publicado antes do programa de quem usa: um programa de antes
        // da 7.6 ignoraria o pedido de série e faria cortes comuns, em silêncio.
        <p className="flex items-start gap-2 text-[13px] text-brass" data-aviso-serie-motor>
          <AlertTriangle size={15} className="shrink-0 mt-0.5" />
          <span>
            O programa deste computador é de antes das séries: ele faria cortes comuns no lugar das partes.
            Atualize-o primeiro — o aviso no topo do site tem o botão.
          </span>
        </p>
      )}

      <button type="submit" disabled={!pode} className="w-full btn-primary">
        {isProcessing ? <><Loader2 size={16} className="animate-spin" /> enviando…</> : 'criar a série'}
      </button>
    </form>
  );
}
