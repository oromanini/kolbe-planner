import { motion } from "framer-motion";
import { useNavigate } from "react-router-dom";
import { Target, DollarSign, LogOut } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function Hub() {
  const navigate = useNavigate();

  const handleLogout = async () => {
    try {
      await fetch(`${API}/auth/logout`, { method: 'POST', credentials: 'include' });
      navigate('/');
    } catch (error) {
      console.error('Logout error:', error);
    }
  };

  const modules = [
    {
      title: "Planner de Metas",
      description: "Acompanhe seus hábitos diários e visualize seu progresso mensal",
      icon: Target,
      path: "/dashboard",
      gradient: "from-primary/20 to-primary/5"
    },
    {
      title: "Planner Financeiro",
      description: "Controle seus gastos, entradas e economias do mês",
      icon: DollarSign,
      path: "/finance",
      gradient: "from-secondary/20 to-secondary/5"
    }
  ];

  return (
    <div className="min-h-screen bg-background text-white">
      {/* Header */}
      <header className="border-b border-white/5 bg-background-paper/50 backdrop-blur-xl">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-xl border border-white/10 p-1.5 bg-white/5 flex items-center justify-center overflow-hidden">
              <img src="/kp-logo.svg" alt="Kolbe Planner" className="h-full w-full object-contain" />
            </div>
            <span className="font-heading text-xl font-medium text-white">Kolbe Planner</span>
          </div>
          <button
            onClick={handleLogout}
            className="p-2.5 hover:bg-white/5 rounded-lg transition-all text-slate-400 hover:text-white"
            title="Sair"
          >
            <LogOut className="w-5 h-5" />
          </button>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="text-center mb-16"
        >
          <h1 className="font-heading text-5xl font-medium text-white mb-4">
            Escolha seu <span className="text-primary">planner</span>
          </h1>
          <p className="text-xl text-slate-400">
            Disciplina em todas as áreas da sua vida
          </p>
        </motion.div>

        <div className="grid md:grid-cols-2 gap-8">
          {modules.map((module, index) => {
            const Icon = module.icon;
            return (
              <motion.button
                key={module.path}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.1 }}
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
                onClick={() => navigate(module.path)}
                className={`glass-card p-8 text-left hover:border-primary/30 transition-all group bg-gradient-to-br ${module.gradient}`}
              >
                <div className="w-16 h-16 bg-white/5 rounded-2xl flex items-center justify-center mb-6 group-hover:scale-110 transition-transform">
                  <Icon className="w-8 h-8 text-primary" strokeWidth={2} />
                </div>
                <h2 className="font-heading text-3xl font-medium text-white mb-3">
                  {module.title}
                </h2>
                <p className="text-slate-400 leading-relaxed">
                  {module.description}
                </p>
              </motion.button>
            );
          })}
        </div>
      </main>
    </div>
  );
}
