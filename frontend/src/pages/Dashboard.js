import { useState, useEffect, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { ChevronLeft, ChevronRight, Settings, LogOut, LayoutDashboard, Target, Landmark } from "lucide-react";
import CalendarGrid from "../components/CalendarGrid";
import ProgressStats from "../components/ProgressStats";
import TutorialModal from "../components/TutorialModal";
import NotificationBell from "../components/NotificationBell";
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
  const [dailyQuote, setDailyQuote] = useState(null);
  const [effectiveMode, setEffectiveMode] = useState("neutral");
  const [calendarView, setCalendarView] = useState("month");

  const currentYear = currentDate.getFullYear();
  const currentMonth = currentDate.getMonth() + 1;

  const today = useMemo(() => {
    const value = new Date();
    value.setHours(0, 0, 0, 0);
    return value;
  }, []);

  const parseDate = (dateString) => {
    const [yearPart, monthPart, dayPart] = dateString.split('-').map(Number);
    return new Date(yearPart, monthPart - 1, dayPart);
  };

  const deadlineNotifications = useMemo(() => {
    const items = [];

    habits.forEach((habit) => {
      if (!habit.start_date || !habit.end_date) {
        return;
      }

      const startDate = parseDate(habit.start_date);
      const endDate = parseDate(habit.end_date);

      const msPerDay = 1000 * 60 * 60 * 24;
      const daysRemaining = Math.floor((endDate - today) / msPerDay);

      if (daysRemaining >= 1 && daysRemaining <= 3 && today >= startDate) {
        items.push({
          habitId: habit.habit_id,
          tone: 'warning',
          message: `Faltam ${daysRemaining} dias para concluir o objetivo ${habit.name}`,
        });
        return;
      }

      if (today > endDate) {
        const periodCompletions = completions.filter((completion) => {
          if (completion.habit_id !== habit.habit_id || !completion.completed) {
            return false;
          }
          const completionDate = parseDate(completion.date);
          return completionDate >= startDate && completionDate <= endDate;
        });

        const uniqueCompletedDays = new Set(periodCompletions.map((completion) => completion.date));
        const requiredDays = (() => {
          let count = 0;
          const cursor = new Date(startDate);
          while (cursor <= endDate) {
            const isWeekday = cursor.getDay() >= 1 && cursor.getDay() <= 5;
            const selectedWeekdays = (habit.selected_weekdays || []).map((value) => value + 1);
            const matchesFrequency = habit.frequency === 'weekdays'
              ? isWeekday
              : habit.frequency === 'custom'
                ? selectedWeekdays.includes(cursor.getDay())
                : true;
            if (matchesFrequency) {
              count++;
            }
            cursor.setDate(cursor.getDate() + 1);
          }
          return count;
        })();

        if (uniqueCompletedDays.size < requiredDays) {
          items.push({
            habitId: habit.habit_id,
            tone: 'danger',
            message: `Você falhou ao cumprir o objetivo ${habit.name} no tempo estimado. Reprograme-se!`,
          });
        }
      }
    });

    return items;
  }, [habits, completions, today]);

  useEffect(() => {
    loadData();
  }, [currentYear, currentMonth]);

  const loadData = async () => {
    try {
      setLoading(true);

      const userRes = await fetch(`${API}/auth/me`, { credentials: 'include' });
      const userData = await userRes.json();
      setUser(userData);

      const quoteRes = await fetch(`${API}/quotes/daily`, { credentials: 'include' });
      if (quoteRes.ok) {
        const quoteData = await quoteRes.json();
        setDailyQuote(quoteData.quote);
        setEffectiveMode(quoteData.mode || "neutral");
      }

      const habitsRes = await fetch(`${API}/habits`, { credentials: 'include' });
      const habitsData = await habitsRes.json();

      if (habitsData.length === 0 && !userData.onboarding_completed) {
        setShowTutorial(true);
      }

      setHabits(habitsData);

      const completionsRes = await fetch(`${API}/completions?year=${currentYear}&month=${currentMonth}`, {
        credentials: 'include',
      });
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
    const existingCompletion = completions.find(
      (completion) => completion.habit_id === habitId && completion.date === date,
    );
    const optimisticCompleted = !(existingCompletion?.completed || false);

    setCompletions((prev) => {
      const completionIndex = prev.findIndex(
        (completion) => completion.habit_id === habitId && completion.date === date,
      );

      if (completionIndex >= 0) {
        return prev.map((completion, index) => (
          index === completionIndex
            ? { ...completion, completed: optimisticCompleted }
            : completion
        ));
      }

      return [
        ...prev,
        {
          habit_id: habitId,
          date,
          completed: optimisticCompleted,
        },
      ];
    });

    try {
      const res = await fetch(`${API}/completions/toggle`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ habit_id: habitId, date }),
      });

      const result = await res.json();
      if (!res.ok) {
        throw new Error(result.detail || 'Não foi possível atualizar este objetivo');
      }

      setCompletions((prev) => {
        const completionIndex = prev.findIndex(
          (completion) => completion.habit_id === habitId && completion.date === date,
        );

        if (completionIndex >= 0) {
          return prev.map((completion, index) => (
            index === completionIndex
              ? { ...completion, completed: result.completed }
              : completion
          ));
        }

        return [
          ...prev,
          {
            habit_id: habitId,
            date,
            completed: result.completed,
          },
        ];
      });

      if (result.completed) {
        toast.success(effectiveMode === 'kolbe' ? 'Persevere! Mais um passo na constância.' : 'Objetivo marcado!', {
          duration: 2000,
        });
      }
    } catch (error) {
      setCompletions((prev) => {
        const completionIndex = prev.findIndex(
          (completion) => completion.habit_id === habitId && completion.date === date,
        );

        if (completionIndex >= 0) {
          if (!existingCompletion) {
            return prev.filter((_, index) => index !== completionIndex);
          }

          return prev.map((completion, index) => (
            index === completionIndex
              ? { ...completion, completed: existingCompletion.completed }
              : completion
          ));
        }

        return existingCompletion ? [...prev, existingCompletion] : prev;
      });

      console.error('Error toggling completion:', error);
      toast.error(error.message || 'Erro ao atualizar');
    }
  };

  const handleLogout = async () => {
    try {
      await fetch(`${API}/auth/logout`, {
        method: 'POST',
        credentials: 'include',
      });
      navigate('/');
    } catch (error) {
      console.error('Logout error:', error);
    }
  };

  const handleCompleteOnboarding = async () => {
    await fetch(`${API}/auth/complete-onboarding`, {
      method: 'POST',
      credentials: 'include',
    });
    setShowTutorial(false);
    loadData();
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-background flex flex-col items-center justify-center gap-5 px-6 text-center">
        <motion.div
          animate={{ rotate: 360 }}
          transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
          className="w-16 h-16 border-4 border-primary/20 border-t-primary rounded-full"
        />
        <p className="text-slate-300 font-body max-w-md">Montando seu planner e separando os próximos passos...</p>
      </div>
    );
  }

  const monthNames = [
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
  ];

  return (
    <div className="min-h-screen bg-background text-white">
      <header className="border-b border-white/5 bg-background-paper/50 backdrop-blur-xl sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="h-12 w-12 rounded-xl border border-white/10 p-1.5 bg-white/5 flex items-center justify-center overflow-hidden">
              <img src="/kp-logo.png" alt="Kolbe Planner" className="h-full w-full object-contain" />
            </div>
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

          <div className="hidden md:flex items-center gap-2 bg-white/5 border border-white/10 rounded-xl p-1">
            <button
              onClick={() => navigate('/dashboard')}
              className="px-3 py-2 rounded-lg bg-primary/20 text-primary text-sm font-medium flex items-center gap-2"
            >
              <Target className="w-4 h-4" />
              Planner de Metas
            </button>
            <button
              onClick={() => navigate('/finance')}
              className="px-3 py-2 rounded-lg text-slate-300 hover:text-white hover:bg-white/5 text-sm font-medium flex items-center gap-2 transition-all"
            >
              <Landmark className="w-4 h-4" />
              Planner Financeiro
            </button>
          </div>

          <div className="flex items-center gap-2">
            <NotificationBell />
            <button
              onClick={() => navigate('/habits')}
              data-testid="quick-goals-button"
              className="px-3 py-2.5 hover:bg-white/5 rounded-lg transition-all text-slate-300 hover:text-white text-sm font-medium"
              title="Ir para metas"
            >
              Metas
            </button>

            <button
              onClick={() => navigate('/settings')}
              data-testid="manage-habits-button"
              className="p-2.5 hover:bg-white/5 rounded-lg transition-all text-slate-400 hover:text-white"
              title="Configurações"
            >
              <Settings className="w-5 h-5" />
            </button>

            {user?.is_admin && (
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

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="grid lg:grid-cols-7 gap-8">
          <div className="lg:col-span-5">
            {dailyQuote && (
              <div className="mb-5 p-3 border border-white/10 rounded-xl bg-white/5 text-sm text-slate-300" data-testid="daily-quote">
                <p className="line-clamp-2">"{dailyQuote.text}" — {dailyQuote.author}</p>
              </div>
            )}

            {deadlineNotifications.length > 0 && (
              <div className="mb-5 space-y-2" data-testid="deadline-notifications">
                {deadlineNotifications.map((notification) => (
                  <div
                    key={`${notification.habitId}-${notification.message}`}
                    className={`p-3 rounded-xl text-sm border ${notification.tone === 'danger' ? 'border-red-500/40 bg-red-500/10 text-red-100' : 'border-amber-400/30 bg-amber-400/10 text-amber-100'}`}
                  >
                    {notification.message}
                  </div>
                ))}
              </div>
            )}

            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="flex items-center justify-between mb-8 gap-4">
              <motion.button
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                onClick={handlePrevMonth}
                data-testid="prev-month-button"
                className="p-3 hover:bg-white/5 rounded-xl transition-all border border-white/10 hover:border-primary/30 text-slate-400 hover:text-white"
              >
                <ChevronLeft className="w-6 h-6" />
              </motion.button>

              <div className="flex flex-col items-center gap-3">
                <h2 className="font-heading text-4xl sm:text-5xl font-medium text-white tracking-tight" data-testid="current-month-title">
                  {monthNames[currentMonth - 1]} <span className="text-primary">{currentYear}</span>
                </h2>
                <div className="flex items-center gap-2 p-1 border border-white/10 rounded-xl bg-white/5">
                  <button
                    type="button"
                    onClick={() => setCalendarView('week')}
                    className={`px-3 py-1.5 rounded-lg text-sm transition-all ${calendarView === 'week' ? 'bg-primary/20 text-primary' : 'text-slate-300 hover:text-white'}`}
                  >
                    Semana
                  </button>
                  <button
                    type="button"
                    onClick={() => setCalendarView('month')}
                    className={`px-3 py-1.5 rounded-lg text-sm transition-all ${calendarView === 'month' ? 'bg-primary/20 text-primary' : 'text-slate-300 hover:text-white'}`}
                  >
                    Mês
                  </button>
                </div>
              </div>

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

            <CalendarGrid
              year={currentYear}
              month={currentMonth}
              habits={habits}
              completions={completions}
              onToggleCompletion={handleToggleCompletion}
              onCreateGoal={() => navigate('/habits')}
              viewMode={calendarView}
              referenceDay={currentDate.getDate()}
            />
          </div>

          <div className="lg:col-span-2">
            <ProgressStats year={currentYear} month={currentMonth} habits={habits} completions={completions} />
          </div>
        </div>
      </main>

      {showTutorial && (
        <TutorialModal
          onComplete={handleCompleteOnboarding}
          onClose={() => setShowTutorial(false)}
          kolbeMode={effectiveMode === "kolbe"}
        />
      )}
    </div>
  );
}
