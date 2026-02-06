import { motion, AnimatePresence } from "framer-motion";
import { ArrowRight, Check, TrendingUp, Target, Zap, Calendar, Mail, Lock, User } from "lucide-react";
import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function LandingPage() {
  const navigate = useNavigate();
  const [showAuth, setShowAuth] = useState(false);
  const [isLogin, setIsLogin] = useState(true);
  const [formData, setFormData] = useState({ email: "", password: "", name: "" });
  const [loading, setLoading] = useState(false);
  const [wordIndex, setWordIndex] = useState(0);
  
  const words = ["HÁBITOS DIÁRIOS", "METAS", "CALENDÁRIO", "TEMPO", "DINHEIRO"];
  
  useEffect(() => {
    const interval = setInterval(() => {
      setWordIndex((prev) => (prev + 1) % words.length);
    }, 2000);
    return () => clearInterval(interval);
  }, []);
  // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
  const handleGoogleLogin = () => {
    const redirectUrl = window.location.origin + '/hub';
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
  };

  const handleEmailAuth = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const endpoint = isLogin ? '/auth/login' : '/auth/register';
      const res = await fetch(`${API}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(formData)
      });
      
      if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || 'Erro na autenticação');
      }
      
      toast.success(isLogin ? 'Login realizado!' : 'Conta criada!');
      navigate('/hub');
    } catch (error) {
      toast.error(error.message);
    } finally {
      setLoading(false);
    }
  };

  const fadeInUp = {
    initial: { opacity: 0, y: 30 },
    whileInView: { opacity: 1, y: 0 },
    viewport: { once: true },
    transition: { duration: 0.6, ease: "easeOut" }
  };

  return (
    <div className="min-h-screen bg-background text-white overflow-hidden">
      {/* Fixed Logo Header */}
      <header className="fixed top-0 left-0 right-0 z-50 border-b border-white/5 bg-background-paper/80 backdrop-blur-md">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <img 
              src="https://customer-assets.emergentagent.com/job_dayminder-4/artifacts/sptbro7d_Kolbe%20Planner%20%282%29.png" 
              alt="Kolbe Planner" 
              className="h-10 w-10 object-contain"
            />
            <span className="font-heading text-xl font-medium text-white">
              Kolbe Planner
            </span>
          </div>
          <button 
            onClick={() => setShowAuth(true)}
            className="text-sm font-body text-slate-400 hover:text-white transition-colors"
          >
            Entrar
          </button>
        </div>
      </header>

      {/* Hero Section */}
      <section className="relative min-h-screen flex items-center justify-center px-4 pt-20">
        {/* Background with overlay */}
        <div className="absolute inset-0 bg-gradient-hero"></div>
        <div 
          className="absolute inset-0 opacity-20"
          style={{
            backgroundImage: "url('https://images.unsplash.com/photo-1761437855740-c894da924d79?crop=entropy&cs=srgb&fm=jpg&q=85')",
            backgroundSize: "cover",
            backgroundPosition: "center"
          }}
        ></div>
        <div className="absolute inset-0 bg-gradient-to-b from-transparent via-background/50 to-background"></div>
        
        {/* Hero Content */}
        <div className="relative z-10 max-w-5xl mx-auto text-center">
          <motion.div
            initial={{ opacity: 0, y: 50 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, ease: "easeOut" }}
          >
            <h1 
              className="font-heading text-6xl md:text-8xl font-medium tracking-tight leading-none mb-8"
              data-testid="landing-hero-title"
            >
              Domine seus<br />
              <AnimatePresence mode="wait">
                <motion.span 
                  key={wordIndex}
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -20 }}
                  transition={{ duration: 0.5 }}
                  className="text-primary inline-block"
                >
                  {words[wordIndex]}
                </motion.span>
              </AnimatePresence>
            </h1>
            
            <p 
              className="text-lg md:text-2xl text-slate-300 max-w-3xl mx-auto mb-12 leading-relaxed font-body"
              data-testid="landing-hero-subtitle"
            >
              Para pessoas disciplinadas que constroem progresso visível.<br className="hidden md:block" />
              Veja cada dia se transformar em vitória.
            </p>
            
            <div className="flex flex-col sm:flex-row gap-4 justify-center items-center">
              <motion.button 
                onClick={() => setShowAuth(true)}
                data-testid="landing-login-button"
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                className="group bg-primary text-white hover:bg-primary/90 shadow-lg shadow-primary/20 font-bold tracking-wide px-10 py-5 rounded-full transition-all flex items-center gap-3 text-lg"
              >
                Começar agora
                <ArrowRight className="w-6 h-6 group-hover:translate-x-1 transition-transform" />
              </motion.button>
              
              <motion.button
                whileHover={{ scale: 1.02 }}
                className="bg-transparent border border-white/20 text-white hover:bg-white/5 hover:border-white/40 px-10 py-5 rounded-full transition-all text-lg font-medium"
              >
                Ver demonstração
              </motion.button>
            </div>
          </motion.div>
        </div>

        {/* Scroll indicator */}
        <motion.div 
          className="absolute bottom-10 left-1/2 -translate-x-1/2"
          animate={{ y: [0, 10, 0] }}
          transition={{ duration: 2, repeat: Infinity }}
        >
          <div className="w-6 h-10 border-2 border-white/20 rounded-full flex justify-center p-2">
            <div className="w-1 h-3 bg-primary rounded-full"></div>
          </div>
        </motion.div>
      </section>

      {/* Features Section */}
      <section className="relative py-32 px-4 border-t border-white/5">
        <div className="max-w-7xl mx-auto">
          <motion.div {...fadeInUp} className="text-center mb-20">
            <h2 
              className="font-heading text-5xl md:text-6xl font-medium text-white mb-6 tracking-tight"
              data-testid="features-section-title"
            >
              Construa constância<br />com <span className="text-primary">precisão visual</span>
            </h2>
            <p className="text-xl text-slate-400 max-w-2xl mx-auto">
              Cada dia é uma oportunidade. Cada mês, uma prova do seu progresso.
            </p>
          </motion.div>
          
          <div className="grid md:grid-cols-3 gap-8">
            {/* Feature 1 */}
            <motion.div 
              {...fadeInUp}
              data-testid="feature-visual"
              className="glass-card p-8 hover:border-primary/30 transition-all group relative overflow-hidden"
            >
              <div className="absolute top-0 right-0 w-32 h-32 bg-primary/10 rounded-full blur-3xl group-hover:bg-primary/20 transition-all"></div>
              
              <div className="relative z-10">
                <div className="w-14 h-14 bg-primary/10 rounded-2xl flex items-center justify-center mb-6 group-hover:scale-110 transition-transform">
                  <Calendar className="w-7 h-7 text-primary" strokeWidth={2} />
                </div>
                <h3 className="font-heading text-2xl font-medium text-white mb-4">
                  Calendário Visual
                </h3>
                <p className="text-slate-400 leading-relaxed">
                  Grade mensal intuitiva. Veja seus hábitos preenchendo cada dia com clareza absoluta.
                </p>
              </div>
            </motion.div>

            {/* Feature 2 */}
            <motion.div 
              {...fadeInUp}
              transition={{ delay: 0.1 }}
              data-testid="feature-victory"
              className="glass-card p-8 hover:border-primary/30 transition-all group relative overflow-hidden"
            >
              <div className="absolute top-0 right-0 w-32 h-32 bg-primary/10 rounded-full blur-3xl group-hover:bg-primary/20 transition-all"></div>
              
              <div className="relative z-10">
                <div className="w-14 h-14 bg-primary/10 rounded-2xl flex items-center justify-center mb-6 group-hover:scale-110 transition-transform">
                  <Zap className="w-7 h-7 text-primary" strokeWidth={2} />
                </div>
                <h3 className="font-heading text-2xl font-medium text-white mb-4">
                  Dias Perfeitos
                </h3>
                <p className="text-slate-400 leading-relaxed">
                  Complete 100% dos hábitos e veja seu dia brilhar em dourado. Satisfação instantânea.
                </p>
              </div>
            </motion.div>

            {/* Feature 3 */}
            <motion.div 
              {...fadeInUp}
              transition={{ delay: 0.2 }}
              data-testid="feature-history"
              className="glass-card p-8 hover:border-primary/30 transition-all group relative overflow-hidden"
            >
              <div className="absolute top-0 right-0 w-32 h-32 bg-primary/10 rounded-full blur-3xl group-hover:bg-primary/20 transition-all"></div>
              
              <div className="relative z-10">
                <div className="w-14 h-14 bg-primary/10 rounded-2xl flex items-center justify-center mb-6 group-hover:scale-110 transition-transform">
                  <TrendingUp className="w-7 h-7 text-primary" strokeWidth={2} />
                </div>
                <h3 className="font-heading text-2xl font-medium text-white mb-4">
                  Progresso Ilimitado
                </h3>
                <p className="text-slate-400 leading-relaxed">
                  Navegue por todos os meses. Sua linha do tempo de disciplina, sempre acessível.
                </p>
              </div>
            </motion.div>
          </div>
        </div>
      </section>

      {/* Social Proof / Stats */}
      <section className="relative py-24 px-4 border-t border-white/5">
        <div className="max-w-7xl mx-auto">
          <motion.div {...fadeInUp} className="glass-card-heavy p-12 text-center">
            <div className="grid md:grid-cols-3 gap-12 divide-x-0 md:divide-x divide-white/10">
              <div>
                <div className="font-heading text-5xl font-bold text-primary mb-2">10</div>
                <div className="text-slate-400 uppercase tracking-wider text-sm">Hábitos Simultâneos</div>
              </div>
              <div>
                <div className="font-heading text-5xl font-bold text-primary mb-2">∞</div>
                <div className="text-slate-400 uppercase tracking-wider text-sm">Histórico Ilimitado</div>
              </div>
              <div>
                <div className="font-heading text-5xl font-bold text-primary mb-2">100%</div>
                <div className="text-slate-400 uppercase tracking-wider text-sm">Visualização Completa</div>
              </div>
            </div>
          </motion.div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="relative py-32 px-4 border-t border-white/5">
        <div className="max-w-4xl mx-auto text-center">
          <motion.div {...fadeInUp}>
            <h2 
              className="font-heading text-5xl md:text-6xl font-medium text-white mb-6 tracking-tight"
              data-testid="cta-title"
            >
              Pronto para ser<br />
              <span className="text-primary">imparável?</span>
            </h2>
            <p className="text-xl text-slate-400 mb-12 max-w-2xl mx-auto">
              Zero fricção. Zero complexidade. Apenas você construindo a melhor versão de si mesmo.
            </p>
            <motion.button 
              onClick={() => setShowAuth(true)}
              data-testid="cta-login-button"
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              className="bg-primary text-white hover:bg-primary/90 shadow-lg shadow-primary/30 font-bold tracking-wide px-12 py-6 rounded-full transition-all text-xl inline-flex items-center gap-3"
            >
              Entrar com Google
              <ArrowRight className="w-6 h-6" />
            </motion.button>
          </motion.div>
        </div>
      </section>

      {/* Auth Modal */}
      {showAuth && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4" onClick={() => setShowAuth(false)}>
          <motion.div 
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            onClick={(e) => e.stopPropagation()}
            className="glass-card-heavy p-8 max-w-md w-full"
          >
            <h2 className="font-heading text-3xl font-medium text-white mb-6">
              {isLogin ? 'Entrar' : 'Criar conta'}
            </h2>
            
            <form onSubmit={handleEmailAuth} className="space-y-4">
              {!isLogin && (
                <div>
                  <label className="block text-sm text-slate-400 mb-2">Nome</label>
                  <div className="relative">
                    <User className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-500" />
                    <input 
                      type="text"
                      value={formData.name}
                      onChange={(e) => setFormData({...formData, name: e.target.value})}
                      className="w-full pl-11 pr-4 py-3 bg-slate-950/50 border border-white/10 rounded-lg text-white"
                      placeholder="Seu nome"
                      required={!isLogin}
                    />
                  </div>
                </div>
              )}
              
              <div>
                <label className="block text-sm text-slate-400 mb-2">Email</label>
                <div className="relative">
                  <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-500" />
                  <input 
                    type="email"
                    value={formData.email}
                    onChange={(e) => setFormData({...formData, email: e.target.value})}
                    className="w-full pl-11 pr-4 py-3 bg-slate-950/50 border border-white/10 rounded-lg text-white"
                    placeholder="seu@email.com"
                    required
                  />
                </div>
              </div>
              
              <div>
                <label className="block text-sm text-slate-400 mb-2">Senha</label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-500" />
                  <input 
                    type="password"
                    value={formData.password}
                    onChange={(e) => setFormData({...formData, password: e.target.value})}
                    className="w-full pl-11 pr-4 py-3 bg-slate-950/50 border border-white/10 rounded-lg text-white"
                    placeholder="••••••••"
                    required
                    minLength={6}
                  />
                </div>
              </div>
              
              <button 
                type="submit"
                disabled={loading}
                className="w-full bg-primary text-white py-3 rounded-full font-bold hover:bg-primary/90 transition-all disabled:opacity-50"
              >
                {loading ? 'Processando...' : (isLogin ? 'Entrar' : 'Criar conta')}
              </button>
            </form>
            
            <div className="relative my-6">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-white/10"></div>
              </div>
              <div className="relative flex justify-center text-sm">
                <span className="px-2 bg-background text-slate-500">ou</span>
              </div>
            </div>
            
            <button 
              onClick={handleGoogleLogin}
              className="w-full border border-white/20 text-white py-3 rounded-full font-medium hover:bg-white/5 transition-all flex items-center justify-center gap-2"
            >
              <svg className="w-5 h-5" viewBox="0 0 24 24">
                <path fill="currentColor" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                <path fill="currentColor" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                <path fill="currentColor" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
                <path fill="currentColor" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
              </svg>
              Continuar com Google
            </button>
            
            <p className="text-center text-sm text-slate-400 mt-6">
              {isLogin ? 'Não tem uma conta?' : 'Já tem uma conta?'}{' '}
              <button 
                onClick={() => setIsLogin(!isLogin)}
                className="text-primary hover:underline font-medium"
              >
                {isLogin ? 'Criar conta' : 'Entrar'}
              </button>
            </p>
          </motion.div>
        </div>
      )}

      {/* Footer */}
      <footer className="py-12 px-4 border-t border-white/5">
        <div className="max-w-7xl mx-auto text-center">
          <p className="text-slate-500 text-sm font-body">
            Kolbe Planner &copy; 2025 — A plataforma para pessoas que levam disciplina a sério
          </p>
        </div>
      </footer>
    </div>
  );
}
