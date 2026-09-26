import React, { useState } from 'react';
import { Baby, CalendarDays, Check, Loader2, Plus, X } from 'lucide-react';
import SegmentedControl from './ui/SegmentedControl';
import { Secao } from './ui/Pagina';
import { salvarCanal } from '../lib/canais';
import { usePainel } from '../lib/painel';
import { fusoDoNavegador, janelasEmTexto, rotuloDoOffset } from '../lib/receita.js';

// A agenda do canal e o "feito para crianças" (etapa 7.5), nos ajustes. As
// janelas valem para tudo o que o canal agenda -- pela receita, pela aprovação
// ou a mão -- e no fuso de quem usa, que o painel manda ao motor.

const HORAS = Array.from({ length: 24 }, (_, h) => h);

export default function AgendaDoCanal({ canal }) {
  const { canais } = usePainel();
  const ajustes = canal.ajustes || {};
  const efetiva = ajustes.agenda_efetiva || { janelas: [11, 15, 19], por_dia: 3, do_canal: false };
  const [janelas, setJanelas] = useState(efetiva.janelas);
  const [porDia, setPorDia] = useState(efetiva.por_dia);
  const [criancas, setCriancas] = useState(
    ajustes.feito_para_criancas === true ? 'sim' : ajustes.feito_para_criancas === false ? 'nao' : 'nicho');
  const [nova, setNova] = useState('');
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState(null);
  const [salvo, setSalvo] = useState(false);
  const fuso = fusoDoNavegador();

  const tirar = (h) => setJanelas((js) => js.filter((x) => x !== h));
  const por = (h) => {
    if (h === '' || janelas.includes(Number(h))) return;
    setJanelas((js) => [...js, Number(h)].sort((a, b) => a - b));
    setNova('');
  };

  const salvar = async () => {
    setSalvando(true);
    setErro(null);
    setSalvo(false);
    const r = await salvarCanal(canal.id, {
      ajustes: {
        agenda: { janelas, por_dia: Number(porDia) },
        feito_para_criancas: criancas === 'sim' ? true : criancas === 'nao' ? false : null,
      },
    });
    setSalvando(false);
    if (!r.ok) {
      setErro(r.erro);
      return;
    }
    setSalvo(true);
    canais.carregar();
  };

  const origemCriancas = ajustes.criancas?.origem === 'nicho' && ajustes.criancas?.valor;
  // Janelas mais perto que o espaçamento mínimo (3 h) viram uma janela só.
  const apertadas = janelas.some((h, i) => i > 0 && h - janelas[i - 1] < 3);

  return (
    <Secao titulo="agenda do canal" icone={CalendarDays}>
      <p className="text-muted text-[13px] leading-snug">
        Os horários em que o canal posta, para tudo o que ele agenda: pela automação, pela aprovação ou à mão. Cada
        post sai alguns minutos antes ou depois da hora, de propósito — horário exato todo dia é um dos sinais que as
        plataformas usam para achar robô.
      </p>
      <div className="space-y-2">
        <span className="eyebrow">janelas do dia</span>
        <div className="flex flex-wrap items-center gap-1.5">
          {janelas.map((h) => (
            <span key={h} className="inline-flex items-center gap-1 pl-2.5 pr-1 py-1 rounded-full border border-rule2 text-sm text-ink">
              {h}h
              <button type="button" onClick={() => tirar(h)} disabled={janelas.length <= 1}
                      className="p-0.5 rounded-full text-muted hover:text-ink disabled:opacity-30" aria-label={`tirar ${h}h`}>
                <X size={12} />
              </button>
            </span>
          ))}
          <label className="inline-flex items-center gap-1.5" htmlFor={`nova-janela-${canal.id}`}>
            <select id={`nova-janela-${canal.id}`} className="input-field py-1 text-sm w-auto" value={nova}
                    onChange={(e) => por(e.target.value)} disabled={janelas.length >= 8}
                    aria-label="acrescentar um horário">
              <option value="">+ horário</option>
              {HORAS.filter((h) => !janelas.includes(h)).map((h) => <option key={h} value={h}>{h}h</option>)}
            </select>
            <Plus size={13} className="text-muted" aria-hidden="true" />
          </label>
        </div>
        {apertadas && (
          <p className="text-[12px] text-muted leading-snug">
            Janelas a menos de 3 h uma da outra não cabem no mesmo dia: o espaçamento mínimo entre dois posts da
            mesma conta é 3 h, e a segunda fica para a janela seguinte.
          </p>
        )}
      </div>
      <label className="block" htmlFor={`por-dia-${canal.id}`}>
        <span className="eyebrow">no máximo, por dia e por conta</span>
        <input id={`por-dia-${canal.id}`} type="number" min={1} max={20} className="input-field mt-1.5 w-24"
               value={porDia} onChange={(e) => setPorDia(e.target.value)} />
      </label>
      <p className="text-[12px] text-muted">
        Hoje: {janelasEmTexto(janelas)}, no fuso deste navegador ({fuso.nome}, {rotuloDoOffset(fuso.offset_min)}).
      </p>

      <div className="space-y-2 pt-1">
        <span className="eyebrow inline-flex items-center gap-1.5"><Baby size={13} /> feito para crianças</span>
        <SegmentedControl
          size="sm"
          options={[
            { value: 'nicho', label: 'pelo nicho', hint: origemCriancas ? 'hoje: sim' : 'hoje: não' },
            { value: 'sim', label: 'sim' },
            { value: 'nao', label: 'não' },
          ]}
          value={criancas}
          onChange={setCriancas}
        />
        <p className="text-muted text-[12px] leading-snug">
          Conteúdo para crianças no YouTube tem de ir marcado assim, pela COPPA (a lei americana): isso desliga os
          comentários e o anúncio personalizado. Com “pelo nicho”, o canal de nicho infantil marca todo envio sozinho.
        </p>
      </div>

      {erro && <p className="text-danger text-sm" role="alert">{erro}</p>}
      <div className="flex flex-wrap items-center gap-2">
        <button type="button" className="btn-primary px-4 py-2 text-sm" onClick={salvar}
                disabled={salvando || !janelas.length || !(Number(porDia) >= 1)}>
          {salvando ? <Loader2 size={15} className="animate-spin" /> : <Check size={15} />} salvar a agenda
        </button>
        {salvo && <span className="text-ok text-sm flex items-center gap-1.5"><Check size={14} /> salvo</span>}
      </div>
    </Secao>
  );
}
