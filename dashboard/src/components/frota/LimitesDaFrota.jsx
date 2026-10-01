import React from 'react';
import { ShieldAlert } from 'lucide-react';
import { Secao } from '../ui/Pagina';

// Os limites da frota (o "Limites" do plano e o ADR-016), na tela desde a 7.1:
// o que ela faz, o que ela nunca faz, e por quê. Fica visível com a frota
// ligada ou não -- é o que a pessoa leu para ligar.
export default function LimitesDaFrota({ limite = 15 }) {
  return (
    <Secao titulo="os limites" icone={ShieldAlert}>
      <p className="text-muted text-[13px] leading-snug">
        As plataformas proíbem conta falsa e publicação automatizada em massa, e quem paga é a conta: a punição
        não é um erro na tela, é a conta perdida.
      </p>
      <ul className="space-y-1.5 text-sm text-ink2" data-limites>
        <li>Liga só quem quiser, e cada aparelho fica separado: uma conta mora num aparelho, um app por conta.</li>
        <li>Cada conta tem limite de posts por dia: 3 de padrão, no máximo {limite}.</li>
        <li>O padrão é entregar: o vídeo abre no app e você toca em publicar. O motor só toca no botão com o seu
          consentimento, depois de você ensinar o caminho e um ensaio passar.</li>
        <li>O motor só posta. Não cria conta, não curte, não segue, não comenta e não “aquece” conta.</li>
        <li>Nada que engane as plataformas: não muda a identidade do aparelho, não usa proxy ou VPN por aparelho
          e não imita gente (toque sorteado, digitação lenta).</li>
      </ul>
    </Secao>
  );
}
