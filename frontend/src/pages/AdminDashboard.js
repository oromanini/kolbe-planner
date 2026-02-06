import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, Users, Target, CheckCircle } from "lucide-react";
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
      // Load stats
      const statsRes = await fetch(`${API}/admin/stats`, { credentials: 'include' });
      const statsData = await statsRes.json();
      setStats(statsData);

      // Load users
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
      <div className="min-h-screen bg-paper flex items-center justify-center">
        <div className="w-16 h-16 border-4 border-navy border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-paper">
      {/* Header */}
      <header className="border-b border-[#E5E7EB] bg-white">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex items-center gap-4">
          <button
            onClick={() => navigate('/dashboard')}
            data-testid="back-to-dashboard"
            className="p-2 hover:bg-paper rounded-sm transition-colors"
          >
            <ArrowLeft className="w-5 h-5 text-navy" />
          </button>
          <h1 className="font-heading text-2xl text-navy" data-testid="admin-title">
            Administração
          </h1>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Stats Grid */}
        <div className="grid md:grid-cols-3 gap-6 mb-8">
          <div className="bg-white border border-[#E5E7EB] rounded-sm p-6 shadow-sm" data-testid="stat-users">
            <div className="flex items-center gap-3 mb-2">
              <div className="w-10 h-10 bg-navy/10 rounded-sm flex items-center justify-center">
                <Users className="w-6 h-6 text-navy" />
              </div>
              <span className="text-sm text-[#8A8F98] font-body uppercase tracking-wide">
                Total Usuários
              </span>
            </div>
            <p className="font-heading text-4xl text-navy">
              {stats?.total_users || 0}
            </p>
          </div>

          <div className="bg-white border border-[#E5E7EB] rounded-sm p-6 shadow-sm" data-testid="stat-habits">
            <div className="flex items-center gap-3 mb-2">
              <div className="w-10 h-10 bg-navy/10 rounded-sm flex items-center justify-center">
                <Target className="w-6 h-6 text-navy" />
              </div>
              <span className="text-sm text-[#8A8F98] font-body uppercase tracking-wide">
                Total Hábitos
              </span>
            </div>
            <p className="font-heading text-4xl text-navy">
              {stats?.total_habits || 0}
            </p>
          </div>

          <div className="bg-white border border-[#E5E7EB] rounded-sm p-6 shadow-sm" data-testid="stat-completions">
            <div className="flex items-center gap-3 mb-2">
              <div className="w-10 h-10 bg-victory-gold/30 rounded-sm flex items-center justify-center">
                <CheckCircle className="w-6 h-6 text-navy" />
              </div>
              <span className="text-sm text-[#8A8F98] font-body uppercase tracking-wide">
                Total Conclusões
              </span>
            </div>
            <p className="font-heading text-4xl text-navy">
              {stats?.total_completions || 0}
            </p>
          </div>
        </div>

        {/* Users Table */}
        <div className="bg-white border border-[#E5E7EB] rounded-sm shadow-sm overflow-hidden">
          <div className="px-6 py-4 border-b border-[#E5E7EB]">
            <h2 className="font-heading text-xl text-navy" data-testid="users-table-title">
              Usuários
            </h2>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-paper border-b border-[#E5E7EB]">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-body font-medium text-[#8A8F98] uppercase tracking-wider">
                    Nome
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-body font-medium text-[#8A8F98] uppercase tracking-wider">
                    Email
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-body font-medium text-[#8A8F98] uppercase tracking-wider">
                    Onboarding
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-body font-medium text-[#8A8F98] uppercase tracking-wider">
                    Data de Criação
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#E5E7EB]">
                {users.map((user) => (
                  <tr key={user.user_id} data-testid={`user-row-${user.user_id}`}>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center gap-3">
                        {user.picture && (
                          <img
                            src={user.picture}
                            alt={user.name}
                            className="w-8 h-8 rounded-full"
                          />
                        )}
                        <span className="font-body text-sm text-navy">
                          {user.name}
                        </span>
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span className="font-body text-sm text-[#8A8F98]">
                        {user.email}
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span className={`
                        inline-flex px-2 py-1 text-xs font-body font-medium rounded-sm
                        ${user.onboarding_completed 
                          ? 'bg-victory-gold/20 text-navy' 
                          : 'bg-paper text-[#8A8F98]'
                        }
                      `}>
                        {user.onboarding_completed ? 'Completo' : 'Pendente'}
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span className="font-body text-sm text-[#8A8F98]">
                        {new Date(user.created_at).toLocaleDateString('pt-BR')}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {users.length === 0 && (
            <div className="px-6 py-12 text-center">
              <p className="text-[#8A8F98] font-body">
                Nenhum usuário cadastrado ainda.
              </p>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
