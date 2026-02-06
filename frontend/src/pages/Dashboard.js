import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { ChevronLeft, ChevronRight, Settings, LogOut, LayoutDashboard, Sparkles } from "lucide-react";
import CalendarGrid from "../components/CalendarGrid";
import ProgressStats from "../components/ProgressStats";
import TutorialModal from "../components/TutorialModal";
import { toast } from "sonner";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function Dashboard() {
  const navigate = useNavigate();
  const [user, setUser] = useState(null);
  const [habits, setHabits] = useState([]);
  const [completions, setCompletions] = useState([]);
  const [currentDate, setCurrentDate] = useState(new Date());
  const [loading, setLoading] = useState(true);
  const [showTutorial, setShowTutorial] = useState(false);

  const currentYear = currentDate.getFullYear();
  const currentMonth = currentDate.getMonth() + 1;

  useEffect(() => {
    loadData();
  }, [currentYear, currentMonth]);

  const loadData = async () => {
    try {
      setLoading(true);
      
      const userRes = await fetch(`${API}/auth/me`, { credentials: 'include' });
      const userData = await userRes.json();
      setUser(userData);

      const habitsRes = await fetch(`${API}/habits`, { credentials: 'include' });
      const habitsData = await habitsRes.json();
      
      if (habitsData.length === 0 && !userData.onboarding_completed) {
        setShowTutorial(true);
      }
      
      setHabits(habitsData);

      const completionsRes = await fetch(
        `${API}/completions?year=${currentYear}&month=${currentMonth}`,
        { credentials: 'include' }
      );
      const completionsData = await completionsRes.json();
      setCompletions(completionsData);

    } catch (error) {
      console.error('Error loading data:', error);
      toast.error('Erro ao carregar dados');
    } finally {
      setLoading(false);
    }
  };

  const handlePrevMonth = () => {
    const newDate = new Date(currentDate);
    newDate.setMonth(newDate.getMonth() - 1);
    setCurrentDate(newDate);
  };

  const handleNextMonth = () => {
    const newDate = new Date(currentDate);
    newDate.setMonth(newDate.getMonth() + 1);
    setCurrentDate(newDate);
  };

  const handleToggleCompletion = async (habitId, date) => {
    try {
      const res = await fetch(`${API}/completions/toggle`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ habit_id: habitId, date })
      });

      const result = await res.json();
      await loadData();
      
      if (result.completed) {
        toast.success('Hábito marcado!', {
          duration: 2000,
        });
      }
    } catch (error) {
      console.error('Error toggling completion:', error);
      toast.error('Erro ao atualizar');
    }
  };

  const handleLogout = async () => {
    try {
      await fetch(`${API}/auth/logout`, {
        method: 'POST',
        credentials: 'include'
      });
      navigate('/');
    } catch (error) {
      console.error('Logout error:', error);
    }
  };

  const handleCompleteOnboarding = async () => {
    await fetch(`${API}/auth/complete-onboarding`, {
      method: 'POST',
      credentials: 'include'
    });
    setShowTutorial(false);
    loadData();
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

  const monthNames = [
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
  ];

  return (
    <div className="min-h-screen bg-background text-white">
      {/* Header */}
      <header className="border-b border-white/5 bg-background-paper/50 backdrop-blur-xl sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <img 
              src="https://customer-assets.emergentagent.com/job_dayminder-4/artifacts/sptbro7d_Kolbe%20Planner%20%282%29.png" 
              alt="Kolbe Planner" 
              className="h-12 w-12 object-contain"
            />
            <div>
              <h1 className="font-heading text-2xl font-medium text-white" data-testid="dashboard-title">
                Kolbe Planner
              </h1>
              {user && (
                <p className="text-sm text-slate-400 font-body" data-testid="user-name">
                  {user.name}
                </p>
              )}
            </div>
          </div>
          
          <div className="flex items-center gap-2">
            <button
              onClick={() => navigate('/habits')}
              data-testid="manage-habits-button"
              className="p-2.5 hover:bg-white/5 rounded-lg transition-all text-slate-400 hover:text-white"
              title="Gerenciar hábitos"
            >
              <Settings className="w-5 h-5" />
            </button>
            
            {user?.email && user.email.includes('@emergent') && (
              <button
                onClick={() => navigate('/admin')}
                data-testid="admin-button"
                className="p-2.5 hover:bg-white/5 rounded-lg transition-all text-slate-400 hover:text-white"
                title="Admin"
              >
                <LayoutDashboard className="w-5 h-5" />
              </button>
            )}
            
            <button
              onClick={handleLogout}
              data-testid="logout-button"
              className="p-2.5 hover:bg-white/5 rounded-lg transition-all text-slate-400 hover:text-white"
              title="Sair"
            >
              <LogOut className="w-5 h-5" />
            </button>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="grid lg:grid-cols-7 gap-8">
          {/* Calendar - Main Area */}
          <div className="lg:col-span-5">
            {/* Month Navigation */}
            <motion.div 
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex items-center justify-between mb-8"
            >
              <motion.button
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                onClick={handlePrevMonth}
                data-testid="prev-month-button"
                className="p-3 hover:bg-white/5 rounded-xl transition-all border border-white/10 hover:border-primary/30 text-slate-400 hover:text-white"
              >
                <ChevronLeft className="w-6 h-6" />
              </motion.button>
              
              <h2 
                className="font-heading text-4xl sm:text-5xl font-medium text-white tracking-tight"
                data-testid="current-month-title"
              >
                {monthNames[currentMonth - 1]} <span className="text-primary">{currentYear}</span>
              </h2>
              
              <motion.button
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                onClick={handleNextMonth}
                data-testid="next-month-button"
                className="p-3 hover:bg-white/5 rounded-xl transition-all border border-white/10 hover:border-primary/30 text-slate-400 hover:text-white"
              >
                <ChevronRight className="w-6 h-6" />
              </motion.button>
            </motion.div>

            {/* Calendar Grid */}
            <CalendarGrid
              year={currentYear}
              month={currentMonth}
              habits={habits}
              completions={completions}
              onToggleCompletion={handleToggleCompletion}
            />
          </div>

          {/* Sidebar - Stats & Habits */}
          <div className="lg:col-span-2">
            <ProgressStats
              year={currentYear}
              month={currentMonth}
              habits={habits}
              completions={completions}
            />
          </div>
        </div>
      </main>

      {/* Tutorial Modal */}
      {showTutorial && (
        <TutorialModal
          onComplete={handleCompleteOnboarding}
          onClose={() => setShowTutorial(false)}
        />
      )}
    </div>
  );
}
