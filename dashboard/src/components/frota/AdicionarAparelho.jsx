import React, { useState } from 'react';
import { Cable, Cloud, KeyRound, Loader2, Plus, Wifi } from 'lucide-react';
import { Secao } from '../ui/Pagina';
import { adicionarAparelho, conectarNaRede, parear } from '../../lib/frotaNoMotor';

// Pôr um celular na frota (etapa 7.9). Três caminhos, os três pelo adb:
// - pelo cabo: o celular aparece sozinho na lista quando a depuração USB está
//   ligada e o computador foi autorizado no aviso que aparece nele;
// - pela rede de casa: o Android 11+ tem "Depuração por Wi-Fi", que pareia por
//   um código e depois conecta (a porta de parear não é a de conectar);
// - em nuvem: um celular remoto que dá um endereço de adb.
// Nada aqui disfarça o aparelho: é só o endereço por onde o adb fala com ele.

function Vistos({ vistos, aoAdicionar, ocupado }) {
  if (!vistos.length) {
    return (
      <p className="text-sm text-muted leading-relaxed">
        Nenhum celular novo à vista. Ligue a <strong className="text-ink2">depuração USB</strong> nas opções do
        desenvolvedor do celular, ligue-o ao computador pelo cabo e aceite o aviso “permitir depuração USB” que aparece
        nele.
      </p>
    );
  }
  return (
    <ul className="divide-y divide-[color:var(--color-rule)]" data-vistos>
      {vistos.map((v) => (
        <li key={v.serial} className="flex flex-wrap items-center gap-3 py-2.5">
          <span className="w-8 h-8 rounded-full bg-paper3 grid place-items-center shrink-0">
            {v.usb ? <Cable size={15} className="text-ink2" /> : <Wifi size={15} className="text-ink2" />}
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-sm text-ink truncate">{v.modelo || 'celular'}</p>
            <p className="readout truncate">{v.serial} · {v.rotulo}</p>
          </div>
          {v.no_ar ? (
            <button type="button" className="btn-ghost px-3 py-1.5 text-xs" disabled={ocupado}
                    onClick={() => aoAdicionar(v)}>
              <Plus size={13} /> pôr na frota
            </button>
          ) : (
            <span className="text-[12px] text-muted max-w-xs">
              {v.estado === 'unauthorized'
                ? 'aceite o aviso “permitir depuração USB” no celular'
                : 'o celular ainda não respondeu'}
            </span>
          )}
        </li>
      ))}
    </ul>
  );
}

export default function AdicionarAparelho({ vistos = [], aoMudar }) {
  const [ocupado, setOcupado] = useState(false);
  const [mensagem, setMensagem] = useState(null);
  const [rede, setRede] = useState({ endereco: '', nome: '', tipo: 'rede', pareamento: '', codigo: '' });

  const avisar = (tipo, texto) => setMensagem({ tipo, texto });

  const adicionar = async (corpo) => {
    setOcupado(true);
    setMensagem(null);
    const r = await adicionarAparelho(corpo);
    setOcupado(false);
    if (!r.ok) return avisar('erro', r.erro);
    avisar('ok', `${r.data.nome} está na frota.`);
    aoMudar?.();
    return r.data;
  };

  const doCabo = (v) => adicionar({ serial: v.serial, nome: v.modelo || 'Celular', tipo: v.usb ? 'cabo' : 'rede' });

  const fazerPareamento = async () => {
    setOcupado(true);
    setMensagem(null);
    const r = await parear(rede.pareamento.trim(), rede.codigo.trim());
    setOcupado(false);
    if (!r.ok) return avisar('erro', r.erro);
    avisar(r.data.ok ? 'ok' : 'erro', r.data.ok
      ? 'Pareado. Agora conecte pelo endereço que a tela “Depuração por Wi-Fi” mostra (o de cima, não o do código).'
      : `O celular recusou: ${r.data.mensagem}`);
    return null;
  };

  const conectarEAdicionar = async () => {
    const endereco = rede.endereco.trim();
    setOcupado(true);
    setMensagem(null);
    const c = await conectarNaRede(endereco);
    setOcupado(false);
    if (!c.ok) return avisar('erro', c.erro);
    if (!c.data.ok) return avisar('erro', `O adb não conectou: ${c.data.mensagem}`);
    return adicionar({ endereco, nome: rede.nome.trim() || 'Celular', tipo: rede.tipo });
  };

  return (
    <Secao titulo="pôr um celular na frota" icone={Plus}>
      <div className="space-y-2">
        <p className="eyebrow">vistos pelo adb</p>
        <Vistos vistos={vistos} aoAdicionar={doCabo} ocupado={ocupado} />
      </div>

      <details className="rounded-input border border-rule px-3 py-2.5 group">
        <summary className="text-sm text-ink2 cursor-pointer flex items-center gap-2">
          <Wifi size={14} className="text-muted" /> pela rede de casa, ou em nuvem
        </summary>
        <div className="mt-3 space-y-3 text-sm">
          <div className="space-y-2">
            <p className="text-muted text-[13px] leading-snug">
              <KeyRound size={13} className="inline-block align-text-bottom mr-1" />
              Android 11 ou mais novo, na mesma rede: em “Depuração por Wi-Fi”, toque em “parear com código” e copie o
              endereço e o código daquela janela.
            </p>
            <div className="grid sm:grid-cols-[1fr_8rem_auto] gap-2">
              <input className="input-field" placeholder="192.168.0.5:37123" aria-label="endereço de parear"
                     value={rede.pareamento} onChange={(e) => setRede({ ...rede, pareamento: e.target.value })} />
              <input className="input-field" placeholder="código" inputMode="numeric" maxLength={6}
                     aria-label="código de pareamento"
                     value={rede.codigo} onChange={(e) => setRede({ ...rede, codigo: e.target.value })} />
              <button type="button" className="btn-ghost px-3 py-1.5 text-xs" onClick={fazerPareamento}
                      disabled={ocupado || !rede.pareamento || rede.codigo.length !== 6}>
                parear
              </button>
            </div>
          </div>
          <div className="space-y-2">
            <p className="text-muted text-[13px] leading-snug">
              Depois de pareado (ou num celular em nuvem, que já dá o endereço): o endereço de conectar e um nome.
            </p>
            <div className="grid sm:grid-cols-[1fr_1fr_auto] gap-2">
              <input className="input-field" placeholder="192.168.0.5:41235" aria-label="endereço de conectar"
                     value={rede.endereco} onChange={(e) => setRede({ ...rede, endereco: e.target.value })} />
              <input className="input-field" placeholder="nome (Celular da sala)" aria-label="nome do aparelho"
                     value={rede.nome} onChange={(e) => setRede({ ...rede, nome: e.target.value })} />
              <select className="input-field" aria-label="onde está o aparelho" value={rede.tipo}
                      onChange={(e) => setRede({ ...rede, tipo: e.target.value })}>
                <option value="rede">rede de casa</option>
                <option value="nuvem">em nuvem</option>
              </select>
            </div>
            <button type="button" className="btn-primary px-3 py-1.5 text-xs" onClick={conectarEAdicionar}
                    disabled={ocupado || !rede.endereco}>
              {ocupado ? <Loader2 size={13} className="animate-spin" />
                : rede.tipo === 'nuvem' ? <Cloud size={13} /> : <Wifi size={13} />} conectar e pôr na frota
            </button>
          </div>
        </div>
      </details>

      {mensagem && (
        <p role="status" className={`text-sm ${mensagem.tipo === 'erro' ? 'text-[color:var(--color-danger)]' : 'text-ink2'}`}>
          {mensagem.texto}
        </p>
      )}
    </Secao>
  );
}
