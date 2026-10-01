import React, { useEffect, useState } from 'react';
import { Bot, Hand, Loader2, Plus, ShieldAlert, Trash2 } from 'lucide-react';
import IconePlataforma from '../ui/IconePlataforma';
import { Secao } from '../ui/Pagina';
import { apiJson } from '../../lib/api';
import { ligarConta, soltarConta } from '../../lib/frotaNoMotor';
import { LIMITE_MAXIMO, LIMITE_PADRAO, contasParaLigar, situacaoDoAutomatico } from '../../lib/frota.js';

// As contas que moram no aparelho (etapa 7.9): o modo de cada uma e o limite
// por dia. "Você publica" é o padrão -- o vídeo abre no app e você toca. "O
// motor publica" pede o roteiro ensaiado deste aparelho e o seu consentimento,
// dado aqui, na hora, e retirado ao voltar para "você publica".

function LinhaDaConta({ aparelho, conta, maximo, aoMudar }) {
  const [modo, setModo] = useState(conta.modo);
  const [limite, setLimite] = useState(String(conta.limite));
  const [consentimento, setConsentimento] = useState(false);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState(null);
  const auto = situacaoDoAutomatico(aparelho, conta.platform);
  const mudou = modo !== conta.modo || Number(limite) !== conta.limite;
  const pedeConsentimento = modo === 'automatico' && conta.modo !== 'automatico';

  const salvar = async () => {
    setSalvando(true);
    setErro(null);
    const r = await ligarConta(aparelho.id, {
      account_id: conta.account_id, modo, limite: Number(limite), consentimento,
    });
    setSalvando(false);
    if (!r.ok) return setErro(r.erro);
    setConsentimento(false);
    return aoMudar?.(r.data);
  };

  const soltar = async () => {
    const r = await soltarConta(aparelho.id, conta.account_id);
    if (!r.ok) return setErro(r.erro);
    return aoMudar?.(r.data);
  };

  return (
    <li className="py-3 space-y-2" data-conta-no-aparelho={conta.account_id}>
      <div className="flex flex-wrap items-center gap-2">
        <IconePlataforma platform={conta.platform} size={16} />
        <span className="text-sm text-ink truncate">{conta.handle}</span>
        <span className="readout">{conta.hoje ?? 0} de {conta.limite} hoje</span>
        <button type="button" className="btn-quiet ml-auto px-2 py-1 text-xs" onClick={soltar}
                title="tirar a conta deste aparelho">
          <Trash2 size={13} /> tirar
        </button>
      </div>
      <div className="flex flex-wrap items-end gap-2">
        <label className="space-y-1">
          <span className="readout block">quem toca em publicar</span>
          <select className="input-field py-1.5 text-sm" value={modo} onChange={(e) => setModo(e.target.value)}
                  aria-label={`modo de ${conta.handle}`}>
            <option value="entregar">você (o vídeo abre no app)</option>
            <option value="automatico" disabled={!auto.pode && conta.modo !== 'automatico'}>
              o motor{auto.pode ? '' : ' (falta o ensaio)'}
            </option>
          </select>
        </label>
        <label className="space-y-1">
          <span className="readout block">posts por dia</span>
          <input className="input-field py-1.5 text-sm w-20" type="number" min={1} max={maximo}
                 value={limite} onChange={(e) => setLimite(e.target.value)} aria-label={`limite de ${conta.handle}`} />
        </label>
        {mudou && (
          <button type="button" className="btn-primary px-3 py-1.5 text-xs"
                  disabled={salvando || (pedeConsentimento && !consentimento)} onClick={salvar}>
            {salvando ? <Loader2 size={13} className="animate-spin" /> : null} salvar
          </button>
        )}
      </div>
      {!auto.pode && conta.modo !== 'automatico' && (
        <p className="text-[12px] text-muted">Para o motor publicar: {auto.motivo}.</p>
      )}
      {conta.modo === 'automatico' && !auto.pode && (
        <p className="text-[12px] text-[color:var(--color-warn)]">
          O automático está parado: {auto.motivo}. Até lá, o vídeo é entregue e você publica.
        </p>
      )}
      {pedeConsentimento && (
        <label className="flex items-start gap-2 text-[13px] text-ink2 cursor-pointer rounded-input border border-[color:var(--color-warn)] p-2.5"
               data-consentimento>
          <input type="checkbox" className="mt-0.5 accent-[color:var(--color-accent)]" checked={consentimento}
                 onChange={(e) => setConsentimento(e.target.checked)} />
          <span>
            <ShieldAlert size={13} className="inline-block align-text-bottom mr-1 text-[color:var(--color-warn)]" />
            Consinto que o motor toque no botão de publicar desta conta. Sei que a plataforma pode punir a conta por
            publicação automatizada, e que posso voltar para “você” a qualquer hora.
          </span>
        </label>
      )}
      {erro && <p className="text-[12px] text-[color:var(--color-danger)]" role="alert">{erro}</p>}
    </li>
  );
}

export default function ContasDoAparelho({ aparelho, plataformas, limite, aoMudar }) {
  const [contas, setContas] = useState(null);
  const [escolhida, setEscolhida] = useState('');
  const [erro, setErro] = useState(null);
  const maximo = limite?.maximo || LIMITE_MAXIMO;

  useEffect(() => {
    let vivo = true;
    apiJson('/api/contas')
      .then((d) => { if (vivo) setContas(d.contas || []); })
      .catch(() => { if (vivo) setContas([]); });
    return () => { vivo = false; };
  }, [aparelho.contas.length]);

  const livres = contasParaLigar(contas, plataformas, aparelho);

  const por = async () => {
    if (!escolhida) return;
    setErro(null);
    const r = await ligarConta(aparelho.id, {
      account_id: escolhida, modo: 'entregar', limite: limite?.padrao || LIMITE_PADRAO,
    });
    if (!r.ok) return setErro(r.erro);
    setEscolhida('');
    return aoMudar?.(r.data);
  };

  return (
    <Secao titulo="contas neste aparelho" icone={Hand}>
      <p className="text-[13px] text-muted leading-snug">
        Uma conta mora num aparelho só, e o aparelho tem uma conta por app: ele posta na conta que estiver aberta no
        app. <Bot size={13} className="inline-block align-text-bottom" /> O motor só publica sozinho com o roteiro
        ensaiado e o seu consentimento.
      </p>
      <ul className="divide-y divide-[color:var(--color-rule)]">
        {aparelho.contas.map((c) => (
          <LinhaDaConta key={`${c.account_id}-${c.modo}-${c.limite}`} aparelho={aparelho} conta={c}
                        maximo={maximo} aoMudar={aoMudar} />
        ))}
        {!aparelho.contas.length && <li className="py-2 text-sm text-muted">Nenhuma conta neste aparelho ainda.</li>}
      </ul>
      {contas && (livres.length ? (
        <div className="flex flex-wrap items-center gap-2">
          <select className="input-field py-1.5 text-sm min-w-0 flex-1" value={escolhida}
                  onChange={(e) => setEscolhida(e.target.value)} aria-label="conta para pôr no aparelho">
            <option value="">escolha uma conta…</option>
            {livres.map((c) => (
              <option key={c.id} value={c.id}>
                {c.handle} · {c.platform}{c.aparelho ? ` (sai de ${c.aparelho.nome})` : ''}
              </option>
            ))}
          </select>
          <button type="button" className="btn-ghost px-3 py-1.5 text-xs" disabled={!escolhida} onClick={por}>
            <Plus size={13} /> pôr no aparelho
          </button>
        </div>
      ) : (
        <p className="text-[12px] text-muted">
          Nenhuma outra conta para este aparelho. As contas se criam nos ajustes de cada canal, ou na Agenda.
        </p>
      ))}
      {erro && <p className="text-[12px] text-[color:var(--color-danger)]" role="alert">{erro}</p>}
    </Secao>
  );
}
