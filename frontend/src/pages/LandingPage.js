import { ArrowRight, Check } from "lucide-react";

export default function LandingPage() {
  // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
  const handleLogin = () => {
    const redirectUrl = window.location.origin + '/dashboard';
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
  };

  return (
    <div className="min-h-screen bg-paper">
      {/* Hero Section */}
      <section className="relative min-h-screen flex items-center justify-center px-4">
        <div className="absolute inset-0 opacity-5 bg-[url('data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNjAiIGhlaWdodD0iNjAiIHZpZXdCb3g9IjAgMCA2MCA2MCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48ZyBmaWxsPSJub25lIiBmaWxsLXJ1bGU9ImV2ZW5vZGQiPjxnIGZpbGw9IiMwRjFCMkQiIGZpbGwtb3BhY2l0eT0iMC40Ij48cGF0aCBkPSJNMzYgMzBoMnYyaC0yVjMwem0wLTEwaC4ydjJIMzZ2LTJ6bTAgMTBoLS4ydjJIMzZ2LTJ6Ii8+PC9nPjwvZz48L3N2Zz4=')]"></div>
        
        <div className="max-w-4xl mx-auto text-center relative z-10">
          <h1 
            className="font-heading text-5xl sm:text-6xl lg:text-7xl tracking-tight leading-none text-navy mb-6"
            data-testid="landing-hero-title"
          >
            Veja sua disciplina<br />tomar forma
          </h1>
          
          <p 
            className="text-lg sm:text-xl text-[#8A8F98] max-w-2xl mx-auto mb-12 font-body leading-relaxed"
            data-testid="landing-hero-subtitle"
          >
            Um planner minimalista para pessoas que trabalham, estudam e praticam<br className="hidden sm:block" />
            hábitos recorrentes. Acompanhe seu progresso visualmente.
          </p>
          
          <button 
            onClick={handleLogin}
            data-testid="landing-login-button"
            className="group bg-navy text-white px-8 py-4 rounded-sm font-body font-medium hover:bg-navy/90 transition-all inline-flex items-center gap-2 shadow-sm"
          >
            Começar agora
            <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
          </button>
        </div>
      </section>

      {/* Features Section */}
      <section className="py-24 px-4 border-t border-[#E5E7EB]">
        <div className="max-w-5xl mx-auto">
          <h2 
            className="font-heading text-3xl sm:text-4xl text-navy text-center mb-16 tracking-tight"
            data-testid="features-section-title"
          >
            Constância visível
          </h2>
          
          <div className="grid md:grid-cols-3 gap-12">
            <div className="text-center" data-testid="feature-visual">
              <div className="w-16 h-16 bg-white border border-[#E5E7EB] rounded-sm mx-auto mb-6 flex items-center justify-center">
                <div className="grid grid-cols-3 gap-1">
                  {[...Array(9)].map((_, i) => (
                    <div key={i} className={`w-2 h-2 rounded-full ${i < 6 ? 'bg-navy' : 'bg-navy/20'}`}></div>
                  ))}
                </div>
              </div>
              <h3 className="font-heading text-xl text-navy mb-3">Visualização clara</h3>
              <p className="text-[#8A8F98] font-body leading-relaxed">
                Veja o mês inteiro sendo preenchido. Cada dia é um quadrado com seus hábitos.
              </p>
            </div>

            <div className="text-center" data-testid="feature-victory">
              <div className="w-16 h-16 bg-white border border-[#E5E7EB] rounded-sm mx-auto mb-6 flex items-center justify-center">
                <Check className="w-8 h-8 text-[#F2E6C9]" strokeWidth={3} />
              </div>
              <h3 className="font-heading text-xl text-navy mb-3">Satisfação ao completar</h3>
              <p className="text-[#8A8F98] font-body leading-relaxed">
                Dias 100% completos ganham destaque dourado. Celebre suas vitórias.
              </p>
            </div>

            <div className="text-center" data-testid="feature-history">
              <div className="w-16 h-16 bg-white border border-[#E5E7EB] rounded-sm mx-auto mb-6 flex items-center justify-center">
                <div className="flex gap-1">
                  <div className="w-2 h-8 bg-navy/30 rounded-sm"></div>
                  <div className="w-2 h-10 bg-navy/50 rounded-sm"></div>
                  <div className="w-2 h-12 bg-navy rounded-sm"></div>
                </div>
              </div>
              <h3 className="font-heading text-xl text-navy mb-3">Histórico ilimitado</h3>
              <p className="text-[#8A8F98] font-body leading-relaxed">
                Navegue entre meses. Veja sua linha do tempo de disciplina.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="py-24 px-4 border-t border-[#E5E7EB]">
        <div className="max-w-3xl mx-auto text-center">
          <h2 
            className="font-heading text-4xl sm:text-5xl text-navy mb-6 tracking-tight"
            data-testid="cta-title"
          >
            Comece hoje
          </h2>
          <p className="text-lg text-[#8A8F98] mb-8 font-body">
            Zero fricção. Zero complexidade. Apenas você e seus hábitos.
          </p>
          <button 
            onClick={handleLogin}
            data-testid="cta-login-button"
            className="bg-navy text-white px-8 py-4 rounded-sm font-body font-medium hover:bg-navy/90 transition-all shadow-sm"
          >
            Entrar com Google
          </button>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-8 px-4 border-t border-[#E5E7EB]">
        <div className="max-w-5xl mx-auto text-center">
          <p className="text-sm text-[#8A8F98] font-body">
            DayMinder &copy; 2025 — Planner minimalista para formação de hábitos
          </p>
        </div>
      </footer>
    </div>
  );
}
