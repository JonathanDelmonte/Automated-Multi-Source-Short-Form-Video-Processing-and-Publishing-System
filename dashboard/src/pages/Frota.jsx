import React from 'react';
import { ShieldAlert, Smartphone } from 'lucide-react';
import IconePlataforma from '../components/ui/IconePlataforma';
import Pagina, { CabecalhoDaPagina, EmBreve, Secao } from '../components/ui/Pagina';

// Frota de aparelhos (etapa 7.9, "phone farm"): celulares ligados ao
// computador, cada um com as contas de um canal, postando pelo próprio
// aplicativo. É onde o Instagram mais vai ser usado (o autor, 26-set-2026).
// Os limites abaixo são do plano, e ficam escritos na tela desde já.
export default function Frota() {
  return (
    <Pagina largura="media">
      <CabecalhoDaPagina
        rotulo="frota"
        titulo="Frota de aparelhos"
        descricao="Celulares, físicos ou em nuvem, cada um postando pelos aplicativos das contas de um canal."
      />
      <EmBreve
        etapa="7.9"
        titulo="O que a frota vai fazer"
        itens={[
          'Os aparelhos, físicos ou em nuvem, e o estado de cada um.',
          'As contas de cada aparelho e o que ele posta, com limite por conta.',
          'Postar pelo aplicativo na hora da agenda, só nas contas que pedirem: a frota nunca entra sozinha na publicação automática.',
        ]}
      >
        <p className="flex items-center gap-2">
          <Smartphone size={15} className="shrink-0" />
          O Instagram é o que mais vai sair por aqui
          <IconePlataforma platform="instagram" size={15} />
        </p>
      </EmBreve>
      <Secao titulo="os limites, desde já" icone={ShieldAlert}>
        <p className="text-muted text-[13px] leading-snug">
          As plataformas proíbem conta falsa e publicação automatizada em massa, e quem paga é a conta.
        </p>
        <ul className="space-y-1.5 text-sm text-ink2">
          <li>Liga só quem quiser, e cada aparelho fica separado dos outros.</li>
          <li>Cada conta tem limite de posts.</li>
          <li>Não entra ferramenta para enganar as plataformas: criar contas em massa, disfarçar aparelho ou rede.</li>
        </ul>
      </Secao>
    </Pagina>
  );
}
