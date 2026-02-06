import { useState } from "react";
import { ArrowRight, Check } from "lucide-react";
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
      <DialogContent className="sm:max-w-lg bg-white">
        {step === 1 && (
          <div className="space-y-6" data-testid="tutorial-step-1">
            <div className="text-center">
              <div className="w-16 h-16 bg-victory-gold/30 rounded-sm mx-auto mb-4 flex items-center justify-center">
                <span className="text-3xl">👋</span>
              </div>
              <h2 className="font-heading text-3xl text-navy mb-3">
                Bem-vindo ao DayMinder
              </h2>
              <p className="text-[#8A8F98] font-body leading-relaxed">
                Vamos configurar seus hábitos e começar sua jornada de constância.
              </p>
            </div>

            <div className="bg-paper p-6 rounded-sm border border-[#E5E7EB]">
              <h3 className="font-heading text-lg text-navy mb-3">
                O que você vai conseguir:
              </h3>
              <ul className="space-y-2">
                <li className="flex items-start gap-2 text-sm font-body text-navy">
                  <Check className="w-5 h-5 text-navy shrink-0 mt-0.5" strokeWidth={2.5} />
                  <span>Visualizar seu progresso mensal de forma clara</span>
                </li>
                <li className="flex items-start gap-2 text-sm font-body text-navy">
                  <Check className="w-5 h-5 text-navy shrink-0 mt-0.5" strokeWidth={2.5} />
                  <span>Marcar até 10 hábitos diários</span>
                </li>
                <li className="flex items-start gap-2 text-sm font-body text-navy">
                  <Check className="w-5 h-5 text-navy shrink-0 mt-0.5" strokeWidth={2.5} />
                  <span>Celebrar dias perfeitos com destaque dourado</span>
                </li>
              </ul>
            </div>

            <button
              onClick={handleInitializeDefaults}
              data-testid="initialize-defaults-button"
              className="w-full bg-navy text-white px-6 py-3 rounded-sm font-body font-medium hover:bg-navy/90 transition-all flex items-center justify-center gap-2"
            >
              Começar com hábitos sugeridos
              <ArrowRight className="w-5 h-5" />
            </button>
          </div>
        )}

        {step === 2 && (
          <div className="space-y-6" data-testid="tutorial-step-2">
            <div className="text-center">
              <div className="w-16 h-16 bg-victory-gold/30 rounded-sm mx-auto mb-4 flex items-center justify-center">
                <Check className="w-8 h-8 text-navy" strokeWidth={2.5} />
              </div>
              <h2 className="font-heading text-3xl text-navy mb-3">
                Hábitos criados!
              </h2>
              <p className="text-[#8A8F98] font-body leading-relaxed">
                Criamos 5 hábitos exemplo para você começar. Você pode editá-los ou criar novos.
              </p>
            </div>

            <div className="bg-paper p-6 rounded-sm border border-[#E5E7EB]">
              <h3 className="font-heading text-lg text-navy mb-3">
                Como usar:
              </h3>
              <ol className="space-y-3">
                <li className="flex items-start gap-3 text-sm font-body text-navy">
                  <span className="w-6 h-6 bg-navy text-white rounded-full flex items-center justify-center shrink-0 text-xs font-medium">1</span>
                  <span>Clique em qualquer dia do calendário</span>
                </li>
                <li className="flex items-start gap-3 text-sm font-body text-navy">
                  <span className="w-6 h-6 bg-navy text-white rounded-full flex items-center justify-center shrink-0 text-xs font-medium">2</span>
                  <span>Marque os hábitos que você completou</span>
                </li>
                <li className="flex items-start gap-3 text-sm font-body text-navy">
                  <span className="w-6 h-6 bg-navy text-white rounded-full flex items-center justify-center shrink-0 text-xs font-medium">3</span>
                  <span>Complete todos os hábitos para ver o dia brilhar em dourado!</span>
                </li>
              </ol>
            </div>

            <button
              onClick={handleComplete}
              data-testid="complete-tutorial-button"
              className="w-full bg-navy text-white px-6 py-3 rounded-sm font-body font-medium hover:bg-navy/90 transition-all"
            >
              Entendi, vamos começar!
            </button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
