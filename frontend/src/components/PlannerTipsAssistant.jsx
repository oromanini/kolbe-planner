import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { Bot, ChevronDown, Send, Sparkles, X } from "lucide-react";

import { apiRequest } from "@/lib/api";

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

// Rotas em que o assistente conversa com dados financeiros reais.
const CHAT_ROUTES = ["/finance", "/dashboard"];

const ROUTES_WITH_ASSISTANT = Object.keys(ROUTE_TIPS);
const COOLDOWN_KEY = "planner-assistant-cooldown-until";
const HISTORY_KEY = "kolbe-assistant-history";
const HISTORY_MAX_MESSAGES = 20;

const QUICK_PROMPTS = [
  "Como está meu mês?",
  "Onde estou gastando mais?",
  "Onde posso cortar despesas?",
];

function getTipsForPath(pathname) {
  return ROUTE_TIPS[pathname] || [];
}

function loadHistory() {
  try {
    const raw = sessionStorage.getItem(HISTORY_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.slice(-HISTORY_MAX_MESSAGES) : [];
  } catch {
    return [];
  }
}

function saveHistory(messages) {
  try {
    sessionStorage.setItem(
      HISTORY_KEY,
      JSON.stringify(messages.slice(-HISTORY_MAX_MESSAGES)),
    );
  } catch {
    /* sessionStorage indisponível — histórico fica só em memória */
  }
}

export default function PlannerTipsAssistant() {
  const location = useLocation();
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState(() => loadHistory());
  const [input, setInput] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState("");
  const scrollRef = useRef(null);

  const tips = useMemo(() => getTipsForPath(location.pathname), [location.pathname]);
  const isSupportedRoute = ROUTES_WITH_ASSISTANT.includes(location.pathname);
  const isChatRoute = CHAT_ROUTES.includes(location.pathname);

  const seedTip = tips[0];

  useEffect(() => {
    if (!isSupportedRoute) {
      setIsOpen(false);
      return;
    }
    const canOpenFromCooldown =
      Number(sessionStorage.getItem(COOLDOWN_KEY) || 0) < Date.now();
    if (canOpenFromCooldown) {
      setIsOpen(true);
    }
  }, [isSupportedRoute, location.pathname]);

  useEffect(() => {
    saveHistory(messages);
  }, [messages]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isSending, isOpen]);

  if (!isSupportedRoute || tips.length === 0) {
    return null;
  }

  const dismissForNow = () => {
    const cooldownUntil = Date.now() + 20 * 60 * 1000;
    sessionStorage.setItem(COOLDOWN_KEY, String(cooldownUntil));
    setIsOpen(false);
  };

  const sendMessage = async (text) => {
    const trimmed = text.trim();
    if (!trimmed || isSending) return;

    const nextMessages = [...messages, { role: "user", content: trimmed }].slice(
      -HISTORY_MAX_MESSAGES,
    );
    setMessages(nextMessages);
    setInput("");
    setError("");
    setIsSending(true);

    try {
      const response = await apiRequest("/finance/assistant/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: nextMessages }),
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const payload = await response.json();
      setMessages((current) =>
        [...current, { role: "assistant", content: payload.reply }].slice(
          -HISTORY_MAX_MESSAGES,
        ),
      );
    } catch {
      setError("Não consegui responder agora. Tente novamente em instantes.");
    } finally {
      setIsSending(false);
    }
  };

  const handleSubmit = (event) => {
    event.preventDefault();
    sendMessage(input);
  };

  const handleKeyDown = (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendMessage(input);
    }
  };

  const showConversation = isChatRoute;

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
            className="flex max-h-[min(70vh,560px)] w-[min(380px,calc(100vw-2rem))] flex-col rounded-2xl border border-white/10 bg-slate-900/75 p-5 text-left text-slate-200 shadow-[0_16px_36px_rgba(2,6,23,0.55)] backdrop-blur-xl"
          >
            <div className="mb-4 flex items-start justify-between gap-4">
              <div className="flex items-center gap-2 text-xs uppercase tracking-[0.14em] text-amber-300/90">
                <Sparkles className="h-4 w-4" />
                {showConversation ? "Kolbe · Assistente" : "Dica do Planner"}
              </div>
              <button
                type="button"
                onClick={dismissForNow}
                data-testid="assistant-dismiss"
                aria-label="Silenciar por 20 minutos"
                className="rounded-full border border-white/10 p-1 text-slate-400 transition hover:border-white/30 hover:text-white"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {!showConversation && (
              <p className="text-sm leading-relaxed text-slate-100">{seedTip}</p>
            )}

            {showConversation && (
              <>
                <div
                  ref={scrollRef}
                  className="flex-1 space-y-3 overflow-y-auto pr-1"
                >
                  <div className="rounded-xl bg-white/5 px-3 py-2 text-sm leading-relaxed text-slate-200">
                    {seedTip} Pergunte sobre seus gastos, receitas ou onde economizar.
                  </div>

                  {messages.map((message, index) => (
                    <div
                      key={`${message.role}-${index}`}
                      className={`max-w-[85%] rounded-xl px-3 py-2 text-sm leading-relaxed ${
                        message.role === "user"
                          ? "ml-auto bg-amber-300/15 text-amber-50"
                          : "bg-white/5 text-slate-100"
                      }`}
                    >
                      {message.content}
                    </div>
                  ))}

                  {isSending && (
                    <div className="max-w-[85%] rounded-xl bg-white/5 px-3 py-2 text-sm text-slate-400">
                      Kolbe está digitando…
                    </div>
                  )}
                </div>

                {error && (
                  <p className="mt-2 text-xs text-rose-300/90">{error}</p>
                )}

                {messages.length === 0 && (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {QUICK_PROMPTS.map((prompt) => (
                      <button
                        key={prompt}
                        type="button"
                        onClick={() => sendMessage(prompt)}
                        disabled={isSending}
                        className="rounded-full border border-white/10 px-3 py-1 text-xs text-slate-300 transition hover:border-amber-200/50 hover:text-white disabled:opacity-50"
                      >
                        {prompt}
                      </button>
                    ))}
                  </div>
                )}

                <form onSubmit={handleSubmit} className="mt-3 flex items-end gap-2">
                  <textarea
                    value={input}
                    onChange={(event) => setInput(event.target.value)}
                    onKeyDown={handleKeyDown}
                    rows={1}
                    placeholder="Pergunte ao Kolbe…"
                    data-testid="assistant-input"
                    className="max-h-28 min-h-[40px] flex-1 resize-none rounded-xl border border-white/10 bg-slate-950/60 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:border-amber-200/50 focus:outline-none"
                  />
                  <button
                    type="submit"
                    disabled={isSending || !input.trim()}
                    aria-label="Enviar"
                    className="rounded-xl border border-amber-300/30 bg-slate-950/80 p-2.5 text-amber-300 transition hover:border-amber-200/50 disabled:opacity-40"
                  >
                    <Send className="h-4 w-4" />
                  </button>
                </form>
              </>
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
        <span>Kolbe</span>
        <ChevronDown
          className={`h-4 w-4 text-slate-300 transition-transform ${isOpen ? "rotate-180" : "rotate-0"}`}
        />
      </button>
    </div>
  );
}
