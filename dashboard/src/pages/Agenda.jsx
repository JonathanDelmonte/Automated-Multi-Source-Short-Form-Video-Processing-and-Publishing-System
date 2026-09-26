import React from 'react';
import PublicacoesTab from '../components/PublicacoesTab';
import Pagina, { CabecalhoDaPagina, EmBreve } from '../components/ui/Pagina';

// Agenda: o que vai sair, e quando, em todos os canais -- o pacote do dia,
// publicar ou agendar um projeto (num canal inteiro ou numa conta) e a fila,
// com os galhos de cada corte (etapa 7.3). O calendário vem na 7.5.
//
// O autor achou a antiga aba "Publicação" confusa (26-set-2026); por isso cada
// parte diz, em uma frase, o que faz, e as contas saíram daqui para as
// Configurações e para a página de cada canal.
export default function Agenda() {
  return (
    <Pagina largura="media">
      <CabecalhoDaPagina
        rotulo="agenda"
        titulo="Agenda"
        descricao="O que vai sair e quando. Baixe o pacote do dia para postar à mão, ou publique e agende um projeto num canal ou numa conta."
      />
      <PublicacoesTab secoes={['pacote', 'publicar', 'fila']} />
      <EmBreve
        etapa="7.5"
        titulo="O calendário de todos os canais"
        itens={[
          'Os posts de cada canal num calendário, dia a dia, com a cor do canal.',
          'Arrastar um post para outro horário.',
        ]}
      >
        <p>
          A trava de segurança já vale: se o computador estiver desligado na hora de postar, os
          atrasados saem um de cada vez quando ele voltar, e o resto é reagendado nas janelas
          seguintes, nunca todos juntos.
        </p>
      </EmBreve>
    </Pagina>
  );
}
