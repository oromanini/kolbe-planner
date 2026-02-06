import { useState } from "react";
import { motion } from "framer-motion";
import { ArrowRight, Check, Sparkles, Zap } from "lucide-react";
import { Dialog, DialogContent } from "./ui/dialog";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function TutorialModal({ onComplete, onClose }) {
  const [step, setStep] = useState(1);

  const handleInitializeDefaults = async () => {
    try {
      await fetch(`${API}/habits/initialize-defaults`, {
        method: 'POST',
        credentials: 'include'
      });
      setStep(2);
    } catch (error) {
      console.error('Error initializing defaults:', error);
    }
  };

  const handleComplete = () => {
    onComplete();
  };

  return (
    <Dialog open={true} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-lg glass-card-heavy border-white/10">
        {step === 1 && (
          <motion.div 
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="space-y-8" 
            data-testid="tutorial-step-1"
          >
            <div className="text-center">
              <motion.div 
                initial={{ scale: 0 }}
                animate={{ scale: 1 }}
                transition={{ type: "spring", stiffness: 200 }}
                className="w-20 h-20 bg-gradient-gold rounded-2xl mx-auto mb-6 flex items-center justify-center shadow-glow-strong"
              >
                <Sparkles className="w-10 h-10 text-background" />
              </motion.div>
              <h2 className="font-heading text-4xl font-medium text-white mb-4">
                Bem-vindo ao<br />
                <span className="text-gradient-red">Kolbe Planner</span>
              </h2>
              <p className="text-slate-400 font-body leading-relaxed text-lg">
                Configure seus hábitos e comece sua jornada<br />de constância e disciplina.
              </p>
            </div>

            <div className="glass-card p-6 space-y-4">
              <h3 className="font-heading text-lg font-medium text-white mb-4 flex items-center gap-2">
                <Zap className="w-5 h-5 text-primary" />
                O que você vai conseguir
              </h3>
              <ul className="space-y-3">
                <li className="flex items-start gap-3 text-sm font-body text-slate-300">
                  <div className="w-6 h-6 bg-primary/20 rounded-lg flex items-center justify-center shrink-0 mt-0.5">
                    <Check className="w-4 h-4 text-primary" strokeWidth={3} />
                  </div>
                  <span>Visualizar progresso mensal de forma clara e impactante</span>
                </li>
                <li className="flex items-start gap-3 text-sm font-body text-slate-300">
                  <div className="w-6 h-6 bg-primary/20 rounded-lg flex items-center justify-center shrink-0 mt-0.5">
                    <Check className="w-4 h-4 text-primary" strokeWidth={3} />
                  </div>
                  <span>Acompanhar até 10 hábitos diários simultaneamente</span>
                </li>
                <li className="flex items-start gap-3 text-sm font-body text-slate-300">
                  <div className="w-6 h-6 bg-primary/20 rounded-lg flex items-center justify-center shrink-0 mt-0.5">
                    <Check className="w-4 h-4 text-primary" strokeWidth={3} />
                  </div>
                  <span>Celebrar dias 100% completos com destaque dourado</span>
                </li>
              </ul>
            </div>

            <motion.button
              onClick={handleInitializeDefaults}
              data-testid="initialize-defaults-button"
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              className="w-full bg-primary text-primary-foreground px-8 py-4 rounded-full font-body font-bold hover:bg-primary/90 transition-all flex items-center justify-center gap-3 shadow-lg shadow-primary/30"
            >
              Começar com hábitos sugeridos
              <ArrowRight className="w-5 h-5" />
            </motion.button>
          </motion.div>
        )}

        {step === 2 && (
          <motion.div 
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="space-y-8" 
            data-testid="tutorial-step-2"
          >
            <div className="text-center">
              <motion.div 
                initial={{ scale: 0, rotate: -180 }}
                animate={{ scale: 1, rotate: 0 }}
                transition={{ type: "spring", stiffness: 150 }}
                className="w-20 h-20 bg-gradient-gold rounded-2xl mx-auto mb-6 flex items-center justify-center shadow-glow-strong"
              >
                <Check className="w-10 h-10 text-background" strokeWidth={3} />
              </motion.div>
              <h2 className="font-heading text-4xl font-bold text-white mb-4">
                Hábitos<br />
                <span className="text-gradient-red">criados!</span>
              </h2>
              <p className="text-slate-400 font-body leading-relaxed text-lg">
                Criamos 5 hábitos exemplo para você começar.<br />Edite ou crie novos quando quiser.
              </p>
            </div>

            <div className="glass-card p-6 space-y-4">
              <h3 className="font-heading text-lg font-bold text-white mb-4">
                Como usar
              </h3>
              <ol className="space-y-4">
                <li className="flex items-start gap-3 text-sm font-body text-slate-300">
                  <span className="w-8 h-8 bg-primary text-primary-foreground rounded-full flex items-center justify-center shrink-0 text-xs font-bold">1</span>
                  <span>Clique em qualquer dia do calendário para abrir</span>
                </li>
                <li className="flex items-start gap-3 text-sm font-body text-slate-300">
                  <span className="w-8 h-8 bg-primary text-primary-foreground rounded-full flex items-center justify-center shrink-0 text-xs font-bold">2</span>
                  <span>Marque os hábitos que você completou naquele dia</span>
                </li>
                <li className="flex items-start gap-3 text-sm font-body text-slate-300">
                  <span className="w-8 h-8 bg-primary text-primary-foreground rounded-full flex items-center justify-center shrink-0 text-xs font-bold">3</span>
                  <span>Complete 100% dos hábitos e veja o dia brilhar em <span className="text-primary font-bold">dourado</span>!</span>
                </li>
              </ol>
            </div>

            <motion.button
              onClick={handleComplete}
              data-testid="complete-tutorial-button"
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              className="w-full bg-primary text-primary-foreground px-8 py-4 rounded-full font-body font-bold hover:bg-primary/90 transition-all shadow-lg shadow-primary/30"
            >
              Entendi, vamos começar!
            </motion.button>
          </motion.div>
        )}
      </DialogContent>
    </Dialog>
  );
}
