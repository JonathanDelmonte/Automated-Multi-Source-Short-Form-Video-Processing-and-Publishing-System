import React, { useEffect, useState } from 'react';
import { Cable, Cloud, GraduationCap, Loader2, Smartphone, Wifi } from 'lucide-react';
import IconePlataforma from '../ui/IconePlataforma';
import { lerTela } from '../../lib/frotaNoMotor';
import { TIPOS, textoDaConta } from '../../lib/frota.js';
import { hrefDe } from '../../lib/rota';

// Um celular na grade da frota: a tela dele ao vivo (uma imagem a cada meio
// minuto, só com a aba à vista), o nome, por onde ele chega e as contas que
// moram nele. Clicar abre o aparelho.

const ICONES = { cabo: Cable, rede: Wifi, nuvem: Cloud };
const RECARGA_DA_TELA_MS = 30_000;

export default function CartaoDoAparelho({ aparelho }) {
  const [tela, setTela] = useState(null);
  const [semTela, setSemTela] = useState(false);
  const Icone = ICONES[aparelho.tipo] || Smartphone;

  useEffect(() => {
    let vivo = true;
    const carregar = async () => {
      if (document.visibilityState !== 'visible') return;
      const r = await lerTela(aparelho.id);
      if (!vivo) return;
      if (r.ok) {
        setTela(r.data.imagem);
        setSemTela(false);
      } else {
        setSemTela(true);
      }
    };
    carregar();
    const id = setInterval(carregar, RECARGA_DA_TELA_MS);
    return () => { vivo = false; clearInterval(id); };
  }, [aparelho.id]);

  return (
    <a href={hrefDe(`/frota/${aparelho.id}`)} className="card card-hover p-3 flex gap-3 min-w-0" data-aparelho={aparelho.id}>
      <div className="w-20 sm:w-24 aspect-[9/19] rounded-[10px] bg-paper3 border border-rule overflow-hidden shrink-0 grid place-items-center">
        {tela
          ? <img src={tela} alt={`tela de ${aparelho.nome}`} className="w-full h-full object-cover" />
          : semTela
            ? <span className="text-[10px] text-muted text-center px-1">fora do ar</span>
            : <Loader2 size={14} className="animate-spin text-muted" />}
      </div>
      <div className="min-w-0 flex-1 space-y-1.5">
        <p className="text-ink text-sm font-medium truncate">{aparelho.nome}</p>
        <p className="readout flex items-center gap-1.5 truncate">
          <Icone size={12} className="shrink-0" /> {TIPOS[aparelho.tipo] || aparelho.tipo}
        </p>
        {aparelho.ocupado && (
          <p className="text-[11px] text-ink2 flex items-center gap-1">
            <Loader2 size={11} className="animate-spin shrink-0" /> <span className="truncate">{aparelho.ocupado}</span>
          </p>
        )}
        {aparelho.ensinando && (
          <p className="text-[11px] text-ink2 flex items-center gap-1">
            <GraduationCap size={11} className="shrink-0" /> aprendendo um app
          </p>
        )}
        <ul className="space-y-1">
          {aparelho.contas.map((c) => (
            <li key={c.account_id} className="flex items-center gap-1.5 text-[12px] text-ink2 min-w-0">
              <IconePlataforma platform={c.platform} size={13} />
              <span className="truncate">{c.handle}</span>
              <span className="text-muted truncate hidden sm:inline">· {textoDaConta(c)}</span>
            </li>
          ))}
          {!aparelho.contas.length && <li className="text-[12px] text-muted">nenhuma conta ainda</li>}
        </ul>
      </div>
    </a>
  );
}
