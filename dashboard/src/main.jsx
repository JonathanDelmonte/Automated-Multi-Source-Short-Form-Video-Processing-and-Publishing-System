import { StrictMode, lazy, Suspense } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import { AuthProvider } from './contexts/AuthContext'

const App = lazy(() => import('./App.jsx'))

// O painel é uma página só, e quem escolhe a tela é o próprio App, pelo
// endereço depois do `#`. As telas de conta em nuvem do projeto original
// (`#/account`, `#/oauth/authorize`, `#/deleted`, `#/auth/`) saíram na limpeza
// da 7.1 (26-set-2026): chamavam o módulo comercial que saiu no ADR-001.
createRoot(document.getElementById('root')).render(
  <StrictMode>
    <AuthProvider>
      <Suspense fallback={<div className="min-h-screen bg-paper flex items-center justify-center text-muted text-sm lowercase">carregando…</div>}>
        <App />
      </Suspense>
    </AuthProvider>
  </StrictMode>,
)
