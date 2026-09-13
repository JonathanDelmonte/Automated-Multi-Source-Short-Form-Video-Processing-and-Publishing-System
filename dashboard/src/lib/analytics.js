// Telemetria: desligada neste fork, e este arquivo é o que garante isso.
//
// O upstream mandava eventos de produto (Signup, CheckoutStarted, Subscribed,
// QuotaWallSeen...) para uma instância de OpenPanel, atrás de um gerenciador
// de consentimento próprio. Saiu tudo junto com a superfície comercial
// (ADR-009), em três peças:
//
//   - o inicializador em `index.html`, que era o único lugar capaz de carregar
//     o tracker;
//   - `public/op1.js`, o script do OpenPanel versionado aqui dentro, que sem o
//     inicializador virou arquivo inalcançável;
//   - `lib/consent.js` e o `CookieBanner`, que existiam só para perguntar
//     sobre esse tracker. Sem ele não há o que perguntar.
//
// **Os três exports continuam de pé de propósito.** Há 13 chamadas a `track()`
// espalhadas por `App.jsx`, `AuthContext.jsx`, `AccountPage.jsx` e
// `TopUpModal.jsx`, quase todas em caminhos de cobrança que o ADR-001 já
// tornou inalcançáveis. Removê-las é mexer em quatro arquivos que o autor vai
// reescrever de qualquer forma quando trocar o frontend; deixar o módulo como
// no-op explícito custa 3 linhas de código e nenhum risco.
//
// Se um dia fizer sentido medir uso *seu*, o lugar é aqui — e a decisão passa
// a ser consciente, em vez de herdada.

export function track(_event, _options) { /* no-op: ver o cabeçalho */ }

export function identify(_user, _props) { /* no-op: ver o cabeçalho */ }

export function reset() { /* no-op: ver o cabeçalho */ }
