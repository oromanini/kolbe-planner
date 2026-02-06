import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowLeft, Users, Target, CheckCircle, Shield } from "lucide-react";
import { toast } from "sonner";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function AdminDashboard() {
  const navigate = useNavigate();
  const [stats, setStats] = useState(null);
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadAdminData();
  }, []);

  const loadAdminData = async () => {
    try {
      const statsRes = await fetch(`${API}/admin/stats`, { credentials: 'include' });
      const statsData = await statsRes.json();
      setStats(statsData);

      const usersRes = await fetch(`${API}/admin/users`, { credentials: 'include' });
      const usersData = await usersRes.json();
      setUsers(usersData);
    } catch (error) {
      console.error('Error loading admin data:', error);
      toast.error('Erro ao carregar dados');
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <motion.div
          animate={{ rotate: 360 }}
          transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
          className="w-16 h-16 border-4 border-primary/20 border-t-primary rounded-full"
        ></motion.div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background text-white">
      {/* Header */}
      <header className="border-b border-white/5 bg-background-paper/50 backdrop-blur-xl sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex items-center gap-4">
          <button
            onClick={() => navigate('/dashboard')}
            data-testid="back-to-dashboard"
            className="p-2.5 hover:bg-white/5 rounded-lg transition-all text-slate-400 hover:text-white"
          >
            <ArrowLeft className="w-5 h-5" />
          </button>
          <h1 className="font-heading text-2xl font-bold text-white flex items-center gap-2" data-testid="admin-title">
            <Shield className="w-6 h-6 text-primary" />
            Administração
          </h1>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Stats Grid */}
        <div className="grid md:grid-cols-3 gap-6 mb-8">
          <motion.div 
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="glass-card p-8" 
            data-testid="stat-users"
          >
            <div className="flex items-center gap-4 mb-4">
              <div className="w-14 h-14 bg-primary/10 rounded-2xl flex items-center justify-center">
                <Users className="w-7 h-7 text-primary" strokeWidth={2} />
              </div>
              <span className="text-sm text-slate-400 font-body uppercase tracking-widest">
                Usuários
              </span>
            </div>
            <p className="font-heading text-5xl font-bold text-white">
              {stats?.total_users || 0}
            </p>
          </motion.div>

          <motion.div 
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="glass-card p-8" 
            data-testid="stat-habits"
          >
            <div className="flex items-center gap-4 mb-4">
              <div className="w-14 h-14 bg-primary/10 rounded-2xl flex items-center justify-center">
                <Target className="w-7 h-7 text-primary" strokeWidth={2} />
              </div>
              <span className="text-sm text-slate-400 font-body uppercase tracking-widest">
                Hábitos
              </span>
            </div>
            <p className="font-heading text-5xl font-bold text-white">
              {stats?.total_habits || 0}
            </p>
          </motion.div>

          <motion.div 
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
            className="glass-card p-8" 
            data-testid="stat-completions"
          >
            <div className="flex items-center gap-4 mb-4">
              <div className="w-14 h-14 bg-primary/10 rounded-2xl flex items-center justify-center">
                <CheckCircle className="w-7 h-7 text-primary" strokeWidth={2} />
              </div>
              <span className="text-sm text-slate-400 font-body uppercase tracking-widest">
                Conclusões
              </span>
            </div>
            <p className="font-heading text-5xl font-bold text-white">
              {stats?.total_completions || 0}
            </p>
          </motion.div>
        </div>

        {/* Users Table */}
        <motion.div 
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="glass-card overflow-hidden"
        >
          <div className="px-8 py-6 border-b border-white/5">
            <h2 className="font-heading text-2xl font-bold text-white" data-testid="users-table-title">
              Usuários Cadastrados
            </h2>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-white/5 border-b border-white/5">
                <tr>
                  <th className="px-8 py-4 text-left text-xs font-body font-medium text-slate-400 uppercase tracking-wider">
                    Usuário
                  </th>
                  <th className="px-8 py-4 text-left text-xs font-body font-medium text-slate-400 uppercase tracking-wider">
                    Email
                  </th>
                  <th className="px-8 py-4 text-left text-xs font-body font-medium text-slate-400 uppercase tracking-wider">
                    Tutorial
                  </th>
                  <th className="px-8 py-4 text-left text-xs font-body font-medium text-slate-400 uppercase tracking-wider">
                    Cadastro
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {users.map((user, index) => (
                  <motion.tr 
                    key={user.user_id}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: index * 0.05 }}
                    data-testid={`user-row-${user.user_id}`}
                    className="hover:bg-white/5 transition-colors"
                  >
                    <td className="px-8 py-4 whitespace-nowrap">
                      <div className="flex items-center gap-3">
                        {user.picture && (
                          <img
                            src={user.picture}
                            alt={user.name}
                            className="w-10 h-10 rounded-full border-2 border-primary/20"
                          />
                        )}
                        <span className="font-body text-sm text-white font-medium">
                          {user.name}
                        </span>
                      </div>
                    </td>
                    <td className="px-8 py-4 whitespace-nowrap">
                      <span className="font-body text-sm text-slate-400">
                        {user.email}
                      </span>
                    </td>
                    <td className="px-8 py-4 whitespace-nowrap">
                      <span className={`
                        inline-flex px-3 py-1 text-xs font-body font-medium rounded-full
                        ${user.onboarding_completed 
                          ? 'bg-primary/20 text-primary border border-primary/30' 
                          : 'bg-white/5 text-slate-400 border border-white/10'
                        }
                      `}>
                        {user.onboarding_completed ? 'Completo' : 'Pendente'}
                      </span>
                    </td>
                    <td className="px-8 py-4 whitespace-nowrap">
                      <span className="font-body text-sm text-slate-400">
                        {new Date(user.created_at).toLocaleDateString('pt-BR')}
                      </span>
                    </td>
                  </motion.tr>
                ))}
              </tbody>
            </table>
          </div>

          {users.length === 0 && (
            <div className="px-8 py-16 text-center">
              <p className="text-slate-400 font-body text-lg">
                Nenhum usuário cadastrado ainda.
              </p>
            </div>
          )}
        </motion.div>
      </main>
    </div>
  );
}
