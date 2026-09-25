// As IAs gratuitas que as Configurações oferecem (25-set-2026).
//
// As chaves são guardadas no motor deste computador (chaves_ia.py), e não no
// navegador. Aqui mora só o que é da tela: nome, para que serve e onde se cria
// a chave. A lista de variáveis é a do motor (`chaves_ia.VARIAVEIS`) e o
// `treina` é o `trains_on_data` da cascata (llm_cascade.py): um teste do
// motor compara os três.
//
// Os links são os do `.env.example`, conferidos no levantamento do ADR-011. O
// `artigo` é para a frase sair certa: "aceita pelo Groq", "aceita pela NVIDIA".
export const PROVEDORES = [
  {
    id: 'gemini',
    nome: 'Google Gemini',
    artigo: 'o',
    recomendado: true,
    link: 'https://aistudio.google.com/app/apikey',
    paraQue: 'Escolhe os melhores momentos, decide o formato de cada corte e faz as miniaturas. É a única que olha as imagens do vídeo.',
    campos: [{ variavel: 'GEMINI_API_KEY', exemplo: 'AIza… ou AQ.…' }],
    treina: true,
  },
  {
    id: 'groq',
    nome: 'Groq',
    artigo: 'o',
    recomendado: true,
    link: 'https://console.groq.com/keys',
    paraQue: 'A mais rápida para escolher os momentos. Uma chave só vale por três modelos, cada um com a própria cota.',
    campos: [{ variavel: 'GROQ_API_KEY', exemplo: 'gsk_…' }],
    treina: false,
  },
  {
    id: 'nvidia',
    nome: 'NVIDIA',
    artigo: 'a',
    link: 'https://build.nvidia.com',
    paraQue: 'O Nemotron, grátis com o cadastro de desenvolvedor da NVIDIA.',
    campos: [{ variavel: 'NVIDIA_API_KEY', exemplo: 'nvapi-…' }],
    treina: true,
  },
  {
    id: 'mistral',
    nome: 'Mistral',
    artigo: 'a',
    link: 'https://console.mistral.ai/api-keys',
    paraQue: 'Modo gratuito; o cadastro pede um número de telefone.',
    campos: [{ variavel: 'MISTRAL_API_KEY' }],
    treina: true,
  },
  {
    id: 'ollama-cloud',
    nome: 'Ollama Cloud',
    artigo: 'o',
    link: 'https://ollama.com/settings/keys',
    paraQue: 'Modelos grandes hospedados pelo Ollama, com limite por semana.',
    campos: [{ variavel: 'OLLAMA_CLOUD_API_KEY' }],
    treina: false,
  },
  {
    id: 'openrouter',
    nome: 'OpenRouter',
    artigo: 'o',
    link: 'https://openrouter.ai/keys',
    paraQue: 'Sorteia um modelo gratuito entre vários; 50 pedidos por dia.',
    campos: [{ variavel: 'OPENROUTER_API_KEY', exemplo: 'sk-or-…' }],
    treina: true,
  },
  {
    id: 'cloudflare',
    nome: 'Cloudflare',
    artigo: 'a',
    link: 'https://dash.cloudflare.com/profile/api-tokens',
    paraQue: 'Workers AI: uma cota diária grátis, dividida entre os modelos. Precisa do token e do ID da conta.',
    campos: [
      { variavel: 'CLOUDFLARE_API_TOKEN', rotulo: 'token (com permissão Workers AI)' },
      { variavel: 'CLOUDFLARE_ACCOUNT_ID', rotulo: 'ID da conta (na barra lateral do painel da Cloudflare)' },
    ],
    treina: false,
  },
  {
    id: 'zai',
    nome: 'Z.ai (GLM)',
    artigo: 'a',
    link: 'https://z.ai/manage-apikey/apikey-list',
    paraQue: 'O GLM-4.7-Flash, grátis e sem prazo; um pedido por vez, com servidor na China.',
    campos: [{ variavel: 'ZAI_API_KEY' }],
    treina: true,
  },
];
