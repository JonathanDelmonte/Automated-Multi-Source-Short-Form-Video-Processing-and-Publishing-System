import React from 'react';
import CalendarioDosCanais from '../components/CalendarioDosCanais';
import PublicacoesTab from '../components/PublicacoesTab';
import Pagina, { CabecalhoDaPagina } from '../components/ui/Pagina';

// Agenda: o que vai sair, e quando, em todos os canais -- o calendário da
// semana (etapa 7.5), o pacote do dia, publicar ou agendar um projeto (num
// canal inteiro ou numa conta) e a fila, com os galhos de cada corte (7.3).
//
// O autor achou a antiga aba "Publicação" confusa (26-set-2026); por isso cada
// parte diz, em uma frase, o que faz, e as contas saíram daqui para as
// Configurações e para a página de cada canal.
export default function Agenda() {
  return (
    <Pagina largura="larga">
      <CabecalhoDaPagina
        rotulo="agenda"
        titulo="Agenda"
        descricao="O que vai sair e quando, em todos os canais. Baixe o pacote do dia para postar à mão, ou publique e agende um projeto num canal ou numa conta."
      />
      <CalendarioDosCanais />
      <PublicacoesTab secoes={['pacote', 'publicar', 'fila']} />
      <p className="text-muted text-[13px] leading-snug">
        A trava de segurança vale para tudo: se o computador estiver desligado na hora de postar, os atrasados saem
        um de cada vez quando ele voltar, e o resto é reagendado nas janelas seguintes, nunca todos juntos.
      </p>
    </Pagina>
  );
}
