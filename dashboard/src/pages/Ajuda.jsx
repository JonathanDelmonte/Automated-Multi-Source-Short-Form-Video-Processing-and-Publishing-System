import React, { useEffect, useState } from 'react';
import { Cpu, Globe, HardDrive } from 'lucide-react';
import PrimeirosPassos from '../components/PrimeirosPassos';
import Pagina, { CabecalhoDaPagina, Secao } from '../components/ui/Pagina';
import { apiFetch } from '../lib/api';
import { hrefDe } from '../lib/rota';

// Ajuda (etapa 7.1): os primeiros passos, como o Virtu Clips funciona e as
// perguntas que já apareceram de verdade -- cada resposta daqui veio de uma
// conversa com o autor ou com o amigo que instalou o ajudante.

const PERGUNTAS = [
  {
    p: 'Onde ficam os meus vídeos?',
    r: 'No seu computador. Pelo instalador, na pasta %LOCALAPPDATA%\\VirtuClips\\dados\\output; pelo Docker, na pasta output do repositório (o atalho abrir-pasta-dos-cortes.bat abre ela). Nada fica na nuvem, e os projetos só saem quando você apaga.',
  },
  {
    p: 'Qual a diferença entre canal e conta?',
    r: 'A conta é o seu perfil numa plataforma (o @ no YouTube, no TikTok ou no Instagram). O canal é a sua marca num nicho, e junta as contas dela: o mesmo "Canal infantil" pode ter uma conta no YouTube e outra no TikTok.',
  },
  {
    p: 'Por que preciso de uma chave de IA?',
    r: 'É com ela que o programa pede a uma IA gratuita (Google Gemini, Groq e outras) para achar os melhores momentos do vídeo. A chave é grátis, leva um minuto e fica guardada no programa deste computador.',
  },
  {
    p: 'Como atualizo o programa?',
    r: 'Quando sair versão nova, aparece um aviso no topo do site com o botão "atualizar agora". Pelo Docker, se o aviso pedir, use o atalho atualizar.bat.',
  },
  {
    p: 'O site diz que não achou o programa. E agora?',
    r: 'O site é só a tela: quem trabalha é o programa no seu computador. Confira se ele está aberto (o ícone perto do relógio, ou o Docker Desktop) e se o navegador tem permissão para falar com este computador.',
  },
];

export default function Ajuda() {
  const [temProjetos, setTemProjetos] = useState(false);
  useEffect(() => {
    let vivo = true;
    (async () => {
      try {
        const res = await apiFetch('/api/jobs');
        const data = res.ok ? await res.json() : {};
        if (vivo) setTemProjetos((data.jobs || []).length > 0);
      } catch { /* os passos seguem sem essa marca */ }
    })();
    return () => { vivo = false; };
  }, []);

  return (
    <Pagina largura="estreita">
      <CabecalhoDaPagina rotulo="ajuda" titulo="Ajuda" descricao="Por onde começar, e as respostas das perguntas que mais aparecem." />

      <PrimeirosPassos temProjetos={temProjetos} />

      <Secao titulo="como o Virtu Clips funciona">
        <ul className="space-y-3 text-sm">
          <li className="flex gap-3">
            <Globe size={17} className="text-muted shrink-0 mt-0.5" />
            <span className="text-ink2"><span className="text-ink">O site é só a tela.</span> Ele abre de qualquer computador e mostra a versão nova sozinho.</span>
          </li>
          <li className="flex gap-3">
            <Cpu size={17} className="text-muted shrink-0 mt-0.5" />
            <span className="text-ink2"><span className="text-ink">Quem trabalha é o programa no seu computador:</span> baixa, transcreve e corta, usando a placa de vídeo quando ela existe.</span>
          </li>
          <li className="flex gap-3">
            <HardDrive size={17} className="text-muted shrink-0 mt-0.5" />
            <span className="text-ink2"><span className="text-ink">Os vídeos ficam no seu disco,</span> e só você decide quando apagar.</span>
          </li>
        </ul>
      </Secao>

      <Secao titulo="perguntas frequentes">
        <div className="divide-y divide-[color:var(--color-rule)]">
          {PERGUNTAS.map(({ p, r }) => (
            <details key={p} className="group py-2.5">
              <summary className="cursor-pointer text-sm text-ink list-none flex items-center justify-between gap-3">
                {p}
                <span className="text-muted group-open:rotate-45 transition-transform text-lg leading-none" aria-hidden="true">+</span>
              </summary>
              <p className="text-muted text-[13px] leading-relaxed mt-2">{r}</p>
            </details>
          ))}
        </div>
      </Secao>

      <Secao titulo="pedir ajuda">
        <p className="text-muted text-[13px] leading-snug">
          Copie as versões em{' '}
          <a href={hrefDe('/configuracoes/versoes')} className="text-ink2 underline underline-offset-2">Configurações → Versões</a>{' '}
          e, se foi um vídeo que deu errado, o log do projeto (o botão de copiar fica no canto do log). Com
          os dois, dá para saber o que aconteceu.
        </p>
      </Secao>
    </Pagina>
  );
}
