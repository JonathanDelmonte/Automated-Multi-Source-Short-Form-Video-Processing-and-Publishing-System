import { createContext, useContext } from 'react';

// O que toda página do painel precisa saber sem que o App passe de mão em mão
// (Fase 7, etapa 7.1): a chave de IA do navegador, se falta chave, o jeito de
// pedir uma, e os canais. Quem monta o valor é o App, que é quem tem a sessão
// e o aviso de chave; as páginas só leem.
export const PainelContext = createContext(null);

export const usePainel = () => useContext(PainelContext);
