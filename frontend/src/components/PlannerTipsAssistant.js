import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { Bot, ChevronDown, Sparkles, X } from "lucide-react";

const ROUTE_TIPS = {
  "/": [
    "Defina uma prioridade antes de entrar: clareza acelera o primeiro passo.",
    "Use o planner como ritual diário de execução, não como lista infinita.",
  ],
  "/hub": [
    "Comece seu dia escolhendo apenas 1 meta principal. Clareza reduz fricção.",
    "Use o hub para decidir o próximo passo em menos de 30 segundos.",
    "Quando estiver em dúvida, priorize tarefas de alto impacto e baixo atrito.",
  ],
  "/dashboard": [
    "Você rende mais com foco curto: escolha um bloco de 25 minutos agora.",
    "Se houver muitas pendências, ataque primeiro o item que desbloqueia os demais.",
    "Revise o dia em 60 segundos antes de abrir uma nova tarefa.",
  ],
  "/habits": [
    "Comece pelo hábito mais simples pendente para ganhar momentum.",
    "Consistência vence intensidade: mantenha a sequência mesmo com ações pequenas.",
    "Acabou de concluir um hábito? Aproveite e emende o próximo em até 5 minutos.",
  ],
  "/finance": [
    "Revise hoje a categoria com maior gasto da semana para recuperar controle.",
    "Antes de planejar o mês, valide despesas fixas e margem de segurança.",
    "Uma pequena correção recorrente vale mais do que um corte drástico pontual.",
  ],
  "/settings": [
    "Ajuste preferências agora para reduzir decisões repetidas no resto da semana.",
    "Configurações bem definidas economizam energia mental diariamente.",
    "Mantenha o ambiente limpo: menos ruído visual, mais execução.",
  ],
};

const ROUTES_WITH_ASSISTANT = Object.keys(ROUTE_TIPS);
const HINT_INTERVAL_MS = 90 * 1000;
const COOLDOWN_KEY = "planner-assistant-cooldown-until";

function getTipsForPath(pathname) {
  return ROUTE_TIPS[pathname] || [];
}

export default function PlannerTipsAssistant() {
  const location = useLocation();
  const [isOpen, setIsOpen] = useState(false);
  const [activeTipIndex, setActiveTipIndex] = useState(0);
  const [tipHistory, setTipHistory] = useState([]);
  const intervalRef = useRef(null);

  const tips = useMemo(() => getTipsForPath(location.pathname), [location.pathname]);
  const isSupportedRoute = ROUTES_WITH_ASSISTANT.includes(location.pathname);

  useEffect(() => {
    if (!isSupportedRoute) {
      setIsOpen(false);
      return;
    }

    const canOpenFromCooldown = Number(sessionStorage.getItem(COOLDOWN_KEY) || 0) < Date.now();
    if (canOpenFromCooldown) {
      setIsOpen(true);
    }
  }, [isSupportedRoute, location.pathname]);

  useEffect(() => {
    setActiveTipIndex(0);
    setTipHistory([]);
  }, [location.pathname]);

  useEffect(() => {
    if (!isSupportedRoute || tips.length <= 1) {
      return undefined;
    }

    intervalRef.current = setInterval(() => {
      setActiveTipIndex((previousIndex) => {
        const nextIndex = (previousIndex + 1) % tips.length;

        setTipHistory((previousHistory) => {
          const previousTip = tips[previousIndex];
          if (!previousTip) {
            return previousHistory;
          }

          const nextHistory = [previousTip, ...previousHistory.filter((tip) => tip !== previousTip)];
          return nextHistory.slice(0, 3);
        });

        return nextIndex;
      });
    }, HINT_INTERVAL_MS);

    return () => {
      clearInterval(intervalRef.current);
    };
  }, [isSupportedRoute, tips]);

  if (!isSupportedRoute || tips.length === 0) {
    return null;
  }

  const dismissForNow = () => {
    const cooldownUntil = Date.now() + 20 * 60 * 1000;
    sessionStorage.setItem(COOLDOWN_KEY, String(cooldownUntil));
    setIsOpen(false);
  };

  const activeTip = tips[activeTipIndex];

  return (
    <div className="fixed bottom-5 right-5 z-50 flex flex-col items-end gap-3">
      <AnimatePresence>
        {isOpen && (
          <motion.section
            key="planner-assistant-panel"
            initial={{ opacity: 0, y: 14, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 8, scale: 0.98 }}
            transition={{ duration: 0.2, ease: "easeOut" }}
            className="w-[min(360px,calc(100vw-2rem))] rounded-2xl border border-white/10 bg-slate-900/75 p-5 text-left text-slate-200 shadow-[0_16px_36px_rgba(2,6,23,0.55)] backdrop-blur-xl"
          >
            <div className="mb-4 flex items-start justify-between gap-4">
              <div className="flex items-center gap-2 text-xs uppercase tracking-[0.14em] text-amber-300/90">
                <Sparkles className="h-4 w-4" />
                Dica do Planner
              </div>
              <button
                type="button"
                onClick={dismissForNow}
                data-testid="assistant-dismiss"
                aria-label="Silenciar dicas por 20 minutos"
                className="rounded-full border border-white/10 p-1 text-slate-400 transition hover:border-white/30 hover:text-white"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <p className="text-sm leading-relaxed text-slate-100">{activeTip}</p>

            {tipHistory.length > 0 && (
              <div className="mt-4 border-t border-white/10 pt-3">
                <p className="mb-2 text-[11px] uppercase tracking-[0.12em] text-slate-400">Últimas dicas</p>
                <ul className="space-y-2 text-xs text-slate-300">
                  {tipHistory.map((tip) => (
                    <li key={tip} className="line-clamp-2">
                      • {tip}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </motion.section>
        )}
      </AnimatePresence>

      <button
        type="button"
        data-testid="assistant-toggle"
        onClick={() => setIsOpen((value) => !value)}
        className="group inline-flex items-center gap-2 rounded-full border border-amber-300/30 bg-slate-950/80 px-4 py-3 text-sm font-medium text-slate-100 shadow-[0_0_22px_rgba(212,175,55,0.18)] backdrop-blur-xl transition hover:-translate-y-0.5 hover:border-amber-200/50 hover:shadow-[0_0_26px_rgba(212,175,55,0.25)]"
      >
        <Bot className="h-4 w-4 text-amber-300" />
        <span>Coach</span>
        <ChevronDown
          className={`h-4 w-4 text-slate-300 transition-transform ${isOpen ? "rotate-180" : "rotate-0"}`}
        />
      </button>
    </div>
  );
}
