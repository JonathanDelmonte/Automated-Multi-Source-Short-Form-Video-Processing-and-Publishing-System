// O selo "IA · 45,3 mil tokens" no topo dos cortes gerados (25-set-2026).
//
// Era "GEMINI · $0.01200": o nome fixo do primeiro provedor e o preço de
// tabela do plano PAGO. Com as chaves gratuitas da cascata (ADR-011) não há
// cobrança nenhuma, e quem respondeu pode nem ter sido o Gemini -- o autor viu
// o dólar e perguntou se estava pagando. O selo passou a dizer o que é verdade
// em todo caso, quantos tokens o job gastou, e o title diz quem respondeu e
// quanto aquilo custaria num plano pago.
const compacto = new Intl.NumberFormat('pt-BR', { notation: 'compact', maximumFractionDigits: 1 });
const inteiro = new Intl.NumberFormat('pt-BR');
const dolar = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'USD', maximumSignificantDigits: 2 });

export function seloDaIA(custo) {
  const entrada = Number(custo?.input_tokens) || 0;
  const saida = Number(custo?.output_tokens) || 0;
  const preco = Number(custo?.total_cost) || 0;
  const detalhe = [
    custo?.model ? `Quem respondeu: ${custo.model}.` : null,
    `${inteiro.format(entrada)} tokens de entrada e ${inteiro.format(saida)} de saída.`,
    preco > 0
      ? `Com chave gratuita, não há cobrança; num plano pago, isto custaria cerca de ${dolar.format(preco)}.`
      : 'Com chave gratuita, não há cobrança.',
  ].filter(Boolean).join(' ');
  return { texto: `IA · ${compacto.format(entrada + saida)} tokens`, detalhe };
}
