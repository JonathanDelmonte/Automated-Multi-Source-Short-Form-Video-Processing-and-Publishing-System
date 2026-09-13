import { StrictMode, useState, useEffect, lazy, Suspense } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import { AuthProvider, useAuth } from './contexts/AuthContext'
import AccountPage from './components/AccountPage'

const App = lazy(() => import('./App.jsx'))
const OAuthConsent = lazy(() => import('./components/OAuthConsent'))

// A landing e as páginas de preço saíram (ADR-009): eram a home comercial do
// upstream, anunciando features que a Fase 0.3 removeu por serem pagas. Sem
// elas o app é a raiz, e não há mais o desvio pela marca `openshorts_skip_
// landing` no localStorage — quem abre a porta 5175 cai direto na ferramenta.
function PageShell({ title, children }) {
  return (
    <div className="min-h-screen bg-paper text-ink2">
      <header className="h-14 sm:h-16 border-b border-rule bg-paper flex items-center justify-between gap-3 px-4 sm:px-6 sticky top-0 z-20">
        <a href="#app" className="font-display lowercase text-lg text-ink truncate">Cortes</a>
        <a href="#app" className="text-sm lowercase text-muted hover:text-ink transition-colors shrink-0">← <span className="hidden sm:inline">Back to app</span><span className="sm:hidden">back</span></a>
      </header>
      <main className="p-4 sm:p-6 md:p-8 pb-[max(2rem,env(safe-area-inset-bottom))]">
        {title && <h1 className="font-display lowercase text-2xl sm:text-3xl text-ink text-center mb-6 sm:mb-10">{title}</h1>}
        {children}
      </main>
    </div>
  );
}

function AccountView() {
  const { isSignedIn, loading } = useAuth();
  // Sem sessão vai para o app, não para a página de preço, que não existe mais.
  // No self-host `billingEnabled` é false e não há login nenhum, então esta
  // view só é alcançável por quem digitou o hash à mão.
  useEffect(() => {
    if (!loading && !isSignedIn) window.location.hash = '#app';
  }, [loading, isSignedIn]);
  return <PageShell><AccountPage /></PageShell>;
}

// Destino depois de apagar a conta. View própria porque a sessão já não
// existe: mandar para #/account devolveria a pessoa ao app sem explicação.
function DeletedView() {
  return (
    <div className="min-h-screen bg-paper text-ink2 flex items-center justify-center p-6">
      <div className="max-w-md text-center space-y-4">
        <h1 className="font-display lowercase text-2xl sm:text-3xl text-ink">Your account is deleted</h1>
        <p className="text-sm">
          Your projects, clips and transcripts are gone, any subscription is
          cancelled, and your API keys no longer work. We've emailed you a
          confirmation with the details.
        </p>
        <p className="text-sm text-muted">
          You're welcome back any time — signing up again with the same address
          starts a brand-new, empty account.
        </p>
      </div>
    </div>
  );
}

function Root() {
  const resolveView = () => {
    const hash = window.location.hash || '';
    if (hash.startsWith('#/auth/')) return 'auth';       // AuthContext consumes then redirects
    if (hash.startsWith('#/oauth/authorize')) return 'oauth';
    if (hash.startsWith('#/account')) return 'account';
    if (hash.startsWith('#/deleted')) return 'deleted';
    return 'app';
  };

  const [view, setView] = useState(resolveView);

  useEffect(() => {
    const handleHashChange = () => setView(resolveView());
    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, []);

  if (view === 'account') return <AccountView />;
  if (view === 'oauth') return <OAuthConsent />;
  if (view === 'deleted') return <DeletedView />;
  if (view === 'auth') {
    return <div className="min-h-screen flex items-center justify-center bg-background text-zinc-400">Signing you in…</div>;
  }
  return <App />;
}

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <AuthProvider>
      <Suspense fallback={<div className="min-h-screen bg-paper flex items-center justify-center text-muted text-sm lowercase">loading…</div>}>
        <Root />
      </Suspense>
    </AuthProvider>
  </StrictMode>,
)
