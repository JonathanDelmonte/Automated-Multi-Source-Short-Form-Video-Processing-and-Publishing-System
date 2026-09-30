import React, { useEffect, useState } from 'react';
import { AlertTriangle, Loader2, Palette, Wand2 } from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';
import { corpoDaCriacao, fraseDaCota, resumoDoEstilo, situacaoDaCriacao } from '../../lib/criacao.js';
import { criarVideo, lerEstilo } from '../../lib/criacaoNoMotor';
import { hrefDe, ir } from '../../lib/rota';

// Criar → Vídeo criado por IA (etapa 7.7): o vídeo sai no estilo do canal, e a
// ideia é opcional -- sem ela, o roteiro inventa uma, sem repetir os temas que
// o canal já fez. O que impede criar (o estilo incompleto, uma chave, a cota do
// dia) vem do motor e aparece ANTES do clique.

export default function CriarVideoDeIA({ canalId, aoCriar }) {
  const { configCarregada, criacaoNoMotor } = useAuth();
  const situacao = situacaoDaCriacao({ configCarregada, criacaoNoMotor });
  const [tela, setTela] = useState(null);
  const [ideia, setIdeia] = useState('');
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState(null);

  useEffect(() => {
    let vivo = true;
    setTela(null);
    setErro(null);
    if (!canalId || situacao !== 'pronto') return undefined;
    lerEstilo(canalId).then((r) => {
      if (!vivo) return;
      if (r.ok) setTela(r.data);
      else setErro(r.erro);
    });
    return () => { vivo = false; };
  }, [canalId, situacao]);

  const criar = async () => {
    setEnviando(true);
    setErro(null);
    const r = await criarVideo(corpoDaCriacao({ canalId, ideia }));
    setEnviando(false);
    if (!r.ok) {
      setErro(r.erro);
      return;
    }
    if (aoCriar) aoCriar(r.data.job_id);
    ir(`/projetos/${r.data.job_id}`);
  };

  if (situacao === 'motor-antigo') {
    return (
      <p className="flex items-start gap-2 text-sm text-ink2" data-aviso-criacao-motor>
        <AlertTriangle size={15} className="shrink-0 mt-0.5 text-muted" />
        <span>O programa deste computador ainda não cria vídeos por IA. Atualize-o pelo aviso no topo da página.</span>
      </p>
    );
  }
  if (!canalId) {
    return <p className="text-sm text-ink2">Escolha o canal: o vídeo sai no estilo que está salvo nele.</p>;
  }
  if (tela === null && !erro) return <Loader2 size={18} className="animate-spin text-muted" aria-label="carregando" />;

  const spec = tela?.estilo?.spec;
  const bloqueio = tela ? tela.pode_criar : null;
  const pode = tela && !bloqueio && !enviando;

  return (
    <div className="space-y-4">
      {tela && (
        <div className="card p-4 space-y-2">
          <p className="flex items-start gap-2 text-sm text-ink2 min-w-0">
            <Palette size={15} className="shrink-0 mt-0.5 text-muted" />
            <span className="min-w-0">
              {spec ? resumoDoEstilo(spec) : 'Este canal ainda não tem estilo.'}{' '}
              <a href={hrefDe(`/canais/${canalId}/criar`)} className="text-muted underline underline-offset-2 hover:text-ink2">
                {spec ? 'mudar o estilo' : 'configurar o estilo'}
              </a>
            </span>
          </p>
          {bloqueio && (
            <p className="flex items-start gap-2 text-sm text-danger" data-bloqueio-da-criacao>
              <AlertTriangle size={15} className="shrink-0 mt-0.5" /> <span className="min-w-0">{bloqueio}</span>
            </p>
          )}
          {tela.cota && spec && <p className="text-[12px] text-muted">{fraseDaCota(tela.cota, spec.cenas)}</p>}
        </div>
      )}

      <label className="block" htmlFor="ideia-do-video">
        <span className="eyebrow">sobre o que é este vídeo? (opcional)</span>
        <textarea id="ideia-do-video" className="input-field mt-1.5 min-h-[5rem]" maxLength={500} value={ideia}
                  onChange={(e) => setIdeia(e.target.value)}
                  placeholder="Ex.: a Lulu aprende a dividir a cenoura com os amigos" />
        <span className="block text-muted text-[12px] mt-1.5 leading-snug">
          Sem ideia, o roteiro inventa uma no estilo do canal, sem repetir os temas que ele já fez.
        </span>
      </label>

      {erro && (
        <p className="flex items-start gap-2 text-sm text-danger">
          <AlertTriangle size={15} className="shrink-0 mt-0.5" /> <span className="min-w-0 break-words">{erro}</span>
        </p>
      )}

      <button type="button" className="btn-primary px-4 py-2.5 text-sm w-full sm:w-auto" onClick={criar} disabled={!pode}>
        {enviando ? <Loader2 size={15} className="animate-spin" /> : <Wand2 size={15} />} criar o vídeo
      </button>
      <p className="text-[12px] text-muted leading-snug">
        O roteiro, as imagens, a narração e a legenda são feitos neste computador com as IAs grátis das suas chaves.
        Um vídeo de um minuto leva alguns minutos; ele aparece em Projetos, e dali vai para a agenda como qualquer corte.
      </p>
    </div>
  );
}
