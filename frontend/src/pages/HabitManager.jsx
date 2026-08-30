import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowLeft, Plus, Trash2, Palette, Sparkles, Pencil, LayoutList, StickyNote } from "lucide-react";
import { toast } from "sonner";
import GoalsBoard from "../components/GoalsBoard";
import { authFetch } from "../lib/api";
import { BACKEND_URL } from "../lib/env";

const API = `${BACKEND_URL}/api`;

const PRESET_COLORS = [
  { name: "Imperial Red", value: "#CD1C33" },
  { name: "Gold", value: "#D4AF37" },
  { name: "Blue", value: "#3B82F6" },
  { name: "Emerald", value: "#10B981" },
  { name: "Purple", value: "#8B5CF6" },
  { name: "Amber", value: "#F59E0B" },
  { name: "Pink", value: "#EC4899" },
  { name: "Cyan", value: "#06B6D4" },
];

const VIEW_MODE_STORAGE_KEY = "kolbe:goals-view-mode";

// Board is meant to stay open on a TV/projector, so refresh it periodically.
const BOARD_REFRESH_MS = 5 * 60 * 1000;

const WEEKDAY_OPTIONS = [
  { label: "Seg", value: 0 },
  { label: "Ter", value: 1 },
  { label: "Qua", value: 2 },
  { label: "Qui", value: 3 },
  { label: "Sex", value: 4 },
];

export default function HabitManager() {
  const navigate = useNavigate();
  const [habits, setHabits] = useState([]);
  const [completions, setCompletions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAddForm, setShowAddForm] = useState(false);
  const [isCreatingHabit, setIsCreatingHabit] = useState(false);
  const [editingHabitId, setEditingHabitId] = useState(null);
  const [viewMode, setViewMode] = useState(() => (
    typeof window !== 'undefined' && window.localStorage.getItem(VIEW_MODE_STORAGE_KEY) === 'board'
      ? 'board'
      : 'list'
  ));

  const todayKey = new Date(Date.now() - new Date().getTimezoneOffset() * 60000)
    .toISOString()
    .split('T')[0];

  const emptyHabit = {
    name: "",
    color: "#CD1C33",
    icon: "circle",
    start_date: todayKey,
    end_date: todayKey,
    frequency: "daily",
    selected_weekdays: [0, 1, 2, 3, 4],
  };

  const [newHabit, setNewHabit] = useState(emptyHabit);

  useEffect(() => {
    loadHabits();
    loadCompletions();
  }, []);

  useEffect(() => {
    window.localStorage.setItem(VIEW_MODE_STORAGE_KEY, viewMode);

    if (viewMode !== 'board') return undefined;

    const interval = setInterval(() => {
      loadHabits();
      loadCompletions();
    }, BOARD_REFRESH_MS);

    return () => clearInterval(interval);
  }, [viewMode]);

  const loadHabits = async () => {
    try {
      const res = await authFetch(`${API}/habits`, { credentials: 'include' });
      const data = await res.json();
      setHabits(data);
    } catch (error) {
      console.error('Error loading habits:', error);
      toast.error('Erro ao carregar hábitos');
    } finally {
      setLoading(false);
    }
  };

  const loadCompletions = async () => {
    const [year, month] = todayKey.split('-');
    try {
      const res = await authFetch(`${API}/completions?year=${Number(year)}&month=${Number(month)}`, {
        credentials: 'include',
      });
      if (!res.ok) throw new Error('Failed to load completions');
      const data = await res.json();
      setCompletions(data);
    } catch (error) {
      console.error('Error loading completions:', error);
    }
  };

  const handleToggleCompletion = async (habitId, date) => {
    const previous = completions;

    setCompletions((prev) => {
      const index = prev.findIndex(
        (completion) => completion.habit_id === habitId && completion.date === date,
      );

      if (index >= 0) {
        return prev.map((completion, currentIndex) => (
          currentIndex === index
            ? { ...completion, completed: !completion.completed }
            : completion
        ));
      }

      return [...prev, { habit_id: habitId, date, completed: true }];
    });

    try {
      const res = await authFetch(`${API}/completions/toggle`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ habit_id: habitId, date }),
      });

      const result = await res.json();
      if (!res.ok) {
        throw new Error(result.detail || 'Não foi possível atualizar esta meta');
      }

      setCompletions((prev) => {
        const index = prev.findIndex(
          (completion) => completion.habit_id === habitId && completion.date === date,
        );

        if (index >= 0) {
          return prev.map((completion, currentIndex) => (
            currentIndex === index
              ? { ...completion, completed: result.completed }
              : completion
          ));
        }

        return [...prev, { habit_id: habitId, date, completed: result.completed }];
      });
    } catch (error) {
      setCompletions(previous);
      console.error('Error toggling completion:', error);
      toast.error(error.message || 'Erro ao atualizar');
    }
  };

  const validateHabit = (habitPayload, isEditing = false) => {
    if (!habitPayload.name.trim()) {
      toast.error('Digite um nome para o objetivo');
      return false;
    }

    if (!habitPayload.start_date || !habitPayload.end_date) {
      toast.error('Preencha as datas de início e fim do objetivo');
      return false;
    }

    if (habitPayload.start_date < todayKey) {
      toast.error('A data inicial deve ser hoje ou futura');
      return false;
    }

    if (habitPayload.end_date < habitPayload.start_date) {
      toast.error('A data final deve ser igual ou posterior à data inicial');
      return false;
    }

    if (habitPayload.frequency === 'custom' && (!habitPayload.selected_weekdays || habitPayload.selected_weekdays.length === 0)) {
      toast.error('Selecione pelo menos um dia da semana');
      return false;
    }

    return true;
  };

  const handleAddHabit = async (e) => {
    e.preventDefault();

    if (isCreatingHabit || !validateHabit(newHabit)) return;

    try {
      setIsCreatingHabit(true);
      const res = await authFetch(`${API}/habits`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          name: newHabit.name.trim(),
          color: newHabit.color,
          icon: newHabit.icon,
          start_date: newHabit.start_date,
          end_date: newHabit.end_date,
          frequency: newHabit.frequency,
          selected_weekdays: newHabit.selected_weekdays,
        }),
      });

      if (!res.ok) throw new Error('Failed to create habit');

      toast.success('Objetivo criado!');
      setNewHabit(emptyHabit);
      setShowAddForm(false);
      await loadHabits();
    } catch (error) {
      console.error('Error creating habit:', error);
      toast.error('Erro ao criar hábito');
    } finally {
      setIsCreatingHabit(false);
    }
  };

  const handleStartEdit = (habit) => {
    setEditingHabitId(habit.habit_id);
    setNewHabit({
      name: habit.name,
      color: habit.color,
      icon: habit.icon || "circle",
      start_date: habit.start_date,
      end_date: habit.end_date,
      frequency: habit.frequency || "daily",
      selected_weekdays: habit.selected_weekdays || [0, 1, 2, 3, 4],
    });
    setShowAddForm(false);
  };

  const handleSaveEdit = async (e) => {
    e.preventDefault();
    if (!editingHabitId || isCreatingHabit || !validateHabit(newHabit, true)) return;

    try {
      setIsCreatingHabit(true);
      const res = await authFetch(`${API}/habits/${editingHabitId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          name: newHabit.name.trim(),
          color: newHabit.color,
          icon: newHabit.icon,
          start_date: newHabit.start_date,
          end_date: newHabit.end_date,
          frequency: newHabit.frequency,
          selected_weekdays: newHabit.selected_weekdays,
        }),
      });

      if (!res.ok) throw new Error('Failed to update habit');

      toast.success('Objetivo atualizado!');
      setEditingHabitId(null);
      setNewHabit(emptyHabit);
      await loadHabits();
    } catch (error) {
      console.error('Error updating habit:', error);
      toast.error('Erro ao atualizar hábito');
    } finally {
      setIsCreatingHabit(false);
    }
  };

  const handleDeleteHabit = async (habitId) => {
    if (!window.confirm('Tem certeza? Isso apagará todos os registros deste objetivo.')) {
      return;
    }

    try {
      const res = await authFetch(`${API}/habits/${habitId}`, {
        method: 'DELETE',
        credentials: 'include',
      });

      if (!res.ok) throw new Error('Failed to delete');

      toast.success('Objetivo removido');
      loadHabits();
    } catch (error) {
      console.error('Error deleting habit:', error);
      toast.error('Erro ao remover hábito');
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-background flex flex-col items-center justify-center gap-5 px-6 text-center">
        <motion.div
          animate={{ rotate: 360 }}
          transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
          className="w-16 h-16 border-4 border-primary/20 border-t-primary rounded-full"
        />
        <p className="text-slate-300 font-body max-w-md">Organizando seus objetivos para você editar sem pressa...</p>
      </div>
    );
  }

  const isEditing = Boolean(editingHabitId);

  return (
    <div className="min-h-screen bg-background text-white">
      <header className="border-b border-white/5 bg-background-paper/50 backdrop-blur-xl sticky top-0 z-50">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button
              onClick={() => navigate('/dashboard')}
              data-testid="back-to-dashboard"
              className="p-2.5 hover:bg-white/5 rounded-lg transition-all text-slate-400 hover:text-white"
            >
              <ArrowLeft className="w-5 h-5" />
            </button>
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-xl border border-white/10 p-1.5 bg-white/5 flex items-center justify-center overflow-hidden">
                <img src="/kp-logo.png" alt="Kolbe Planner" className="h-full w-full object-contain" />
              </div>
              <h1 className="font-heading text-2xl font-medium text-white" data-testid="habit-manager-title">
                Gerenciar Hábitos
              </h1>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={() => navigate('/dashboard')}
              className="px-4 py-2 rounded-lg text-sm text-slate-200 border border-white/10 hover:bg-white/5"
            >
              Voltar à dashboard
            </button>
            <div className="text-sm text-slate-400 font-body px-4 py-2 bg-white/5 rounded-lg border border-white/10">
              {habits.length} <span className="text-primary">objetivos</span>
            </div>
          </div>
        </div>
      </header>

      <main className={`${viewMode === 'board' ? 'max-w-7xl' : 'max-w-5xl'} mx-auto px-4 sm:px-6 lg:px-8 py-8`}>
        <div className="mb-8 flex items-center justify-center">
          <div className="flex items-center gap-1 p-1 border border-white/10 rounded-xl bg-white/5">
            <button
              type="button"
              onClick={() => setViewMode('list')}
              data-testid="goals-view-list"
              className={`px-4 py-2 rounded-lg text-sm font-body flex items-center gap-2 transition-all ${viewMode === 'list' ? 'bg-primary/20 text-primary' : 'text-slate-300 hover:text-white'}`}
            >
              <LayoutList className="w-4 h-4" />
              Lista
            </button>
            <button
              type="button"
              onClick={() => setViewMode('board')}
              data-testid="goals-view-board"
              className={`px-4 py-2 rounded-lg text-sm font-body flex items-center gap-2 transition-all ${viewMode === 'board' ? 'bg-primary/20 text-primary' : 'text-slate-300 hover:text-white'}`}
            >
              <StickyNote className="w-4 h-4" />
              Quadro de hoje
            </button>
          </div>
        </div>

        {viewMode === 'board' && (
          <>
            <GoalsBoard
              habits={habits}
              completions={completions}
              todayKey={todayKey}
              onToggleCompletion={handleToggleCompletion}
              onCreateGoal={() => {
                setViewMode('list');
                setShowAddForm(true);
              }}
            />
            <p className="mt-4 text-center text-xs text-slate-500 font-body">
              O quadro mostra apenas as metas de hoje. Clique em um card para marcar como concluída.
            </p>
          </>
        )}

        {viewMode === 'list' && !showAddForm && !isEditing && (
          <motion.button
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            whileHover={{ scale: 1.01 }}
            onClick={() => setShowAddForm(true)}
            data-testid="show-add-habit-form"
            className="w-full mb-8 p-8 border-2 border-dashed border-white/10 rounded-2xl hover:border-primary/30 transition-all flex items-center justify-center gap-3 text-slate-400 hover:text-white font-body bg-white/5 backdrop-blur-sm"
          >
            <Plus className="w-6 h-6" />
            <span className="font-medium">Adicionar novo objetivo</span>
          </motion.button>
        )}

        {viewMode === 'list' && (showAddForm || isEditing) && (
          <motion.form
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            onSubmit={isEditing ? handleSaveEdit : handleAddHabit}
            className="mb-8 glass-card p-8"
          >
            <h3 className="font-heading text-2xl font-medium text-white mb-6 flex items-center gap-2">
              {isEditing ? <Pencil className="w-6 h-6 text-primary" /> : <Plus className="w-6 h-6 text-primary" />}
              {isEditing ? 'Editar objetivo' : 'Novo Objetivo'}
            </h3>

            <div className="space-y-6">
              <div>
                <label className="block text-sm font-body font-medium text-slate-300 mb-3">Nome do objetivo</label>
                <input
                  type="text"
                  data-testid="habit-name-input"
                  value={newHabit.name}
                  onChange={(e) => setNewHabit({ ...newHabit, name: e.target.value })}
                  placeholder="Ex: Exercício, Leitura, Meditação..."
                  className="w-full px-5 py-4 bg-slate-950/50 border border-white/10 rounded-xl font-body text-white placeholder:text-slate-600 focus:border-primary/50 focus:ring-2 focus:ring-primary/20 transition-all outline-none"
                  maxLength={30}
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-body font-medium text-slate-300 mb-3">Período (DE)</label>
                  <input
                    type="date"
                    value={newHabit.start_date}
                    min={todayKey}
                    onChange={(e) => {
                      const nextStart = e.target.value;
                      setNewHabit({
                        ...newHabit,
                        start_date: nextStart,
                        end_date: newHabit.end_date < nextStart ? nextStart : newHabit.end_date,
                      });
                    }}
                    className="w-full px-5 py-4 bg-slate-950/50 border border-white/10 rounded-xl font-body text-white focus:border-primary/50 focus:ring-2 focus:ring-primary/20 transition-all outline-none"
                  />
                </div>
                <div>
                  <label className="block text-sm font-body font-medium text-slate-300 mb-3">Período (ATÉ)</label>
                  <input
                    type="date"
                    value={newHabit.end_date}
                    min={newHabit.start_date}
                    onChange={(e) => setNewHabit({ ...newHabit, end_date: e.target.value })}
                    className="w-full px-5 py-4 bg-slate-950/50 border border-white/10 rounded-xl font-body text-white focus:border-primary/50 focus:ring-2 focus:ring-primary/20 transition-all outline-none"
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm font-body font-medium text-slate-300 mb-3">Frequência</label>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <button
                    type="button"
                    onClick={() => setNewHabit({ ...newHabit, frequency: "daily" })}
                    className={`px-4 py-3 rounded-xl border text-left transition-all ${newHabit.frequency === "daily" ? "border-primary/60 bg-primary/10 text-white" : "border-white/10 text-slate-300 hover:border-white/20"}`}
                  >
                    Todos os dias
                  </button>
                  <button
                    type="button"
                    onClick={() => setNewHabit({ ...newHabit, frequency: "custom" })}
                    className={`px-4 py-3 rounded-xl border text-left transition-all ${newHabit.frequency === "custom" ? "border-primary/60 bg-primary/10 text-white" : "border-white/10 text-slate-300 hover:border-white/20"}`}
                  >
                    Selecionar dias
                  </button>
                </div>
                {newHabit.frequency === "custom" && (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {WEEKDAY_OPTIONS.map((day) => {
                      const isSelected = newHabit.selected_weekdays.includes(day.value);
                      return (
                        <button
                          key={day.value}
                          type="button"
                          onClick={() => {
                            const updatedDays = isSelected
                              ? newHabit.selected_weekdays.filter((value) => value !== day.value)
                              : [...newHabit.selected_weekdays, day.value].sort((a, b) => a - b);
                            setNewHabit({ ...newHabit, selected_weekdays: updatedDays });
                          }}
                          className={`px-3 py-2 rounded-lg border text-sm transition-all ${isSelected ? "border-primary/60 bg-primary/10 text-white" : "border-white/10 text-slate-300 hover:border-white/20"}`}
                        >
                          {day.label}
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>

              <div>
                <label className="block text-sm font-body font-medium text-slate-300 mb-3 flex items-center gap-2">
                  <Palette className="w-4 h-4" />
                  Cor do objetivo
                </label>
                <div className="flex flex-wrap gap-3">
                  {PRESET_COLORS.map((color) => (
                    <motion.button
                      key={color.value}
                      type="button"
                      data-testid={`color-${color.name}`}
                      onClick={() => setNewHabit({ ...newHabit, color: color.value })}
                      whileHover={{ scale: 1.1 }}
                      whileTap={{ scale: 0.95 }}
                      className={`w-12 h-12 rounded-xl transition-all relative ${newHabit.color === color.value ? 'ring-2 ring-primary ring-offset-2 ring-offset-background shadow-glow' : 'hover:scale-110'}`}
                      style={{
                        backgroundColor: color.value,
                        boxShadow: newHabit.color === color.value ? `0 0 20px ${color.value}` : 'none',
                      }}
                      title={color.name}
                    />
                  ))}
                </div>
              </div>

              <div className="flex gap-3 pt-4">
                <motion.button
                  type="submit"
                  data-testid="create-habit-submit"
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                  disabled={isCreatingHabit}
                  className="flex-1 bg-primary text-primary-foreground px-8 py-4 rounded-full font-body font-bold hover:bg-primary/90 transition-all shadow-lg shadow-primary/20 disabled:cursor-not-allowed disabled:opacity-70"
                >
                  {isCreatingHabit ? (
                    <span className="flex items-center justify-center gap-2">
                      <motion.span
                        animate={{ rotate: 360 }}
                        transition={{ duration: 0.8, repeat: Infinity, ease: "linear" }}
                        className="w-4 h-4 border-2 border-primary-foreground/40 border-t-primary-foreground rounded-full"
                      />
                      Salvando...
                    </span>
                  ) : isEditing ? 'Salvar alterações' : 'Criar objetivo'}
                </motion.button>
                <motion.button
                  type="button"
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                  onClick={() => {
                    setShowAddForm(false);
                    setEditingHabitId(null);
                    setNewHabit(emptyHabit);
                  }}
                  data-testid="cancel-add-habit"
                  className="px-8 py-4 border border-white/20 rounded-full font-body hover:bg-white/5 transition-all text-white"
                >
                  Cancelar
                </motion.button>
              </div>
            </div>
          </motion.form>
        )}

        <div className={`space-y-4 ${viewMode === 'board' ? 'hidden' : ''}`}>
          {habits.length === 0 ? (
            <div className="text-center py-20 glass-card">
              <p className="text-slate-400 font-body text-lg">Nenhum objetivo criado ainda.</p>
            </div>
          ) : (
            habits.map((habit, index) => (
              <motion.div
                key={habit.habit_id}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.05 }}
                data-testid={`habit-item-${habit.habit_id}`}
                className="glass-card p-6 hover:border-primary/30 transition-all group"
              >
                <div className="flex items-center gap-4">
                  <div
                    className="w-16 h-16 rounded-2xl flex items-center justify-center shrink-0 relative overflow-hidden"
                    style={{ backgroundColor: `${habit.color}20`, border: `2px solid ${habit.color}` }}
                  >
                    <span className="font-heading text-2xl font-bold" style={{ color: habit.color }}>
                      {index + 1}
                    </span>
                  </div>

                  <div className="flex-1">
                    <h4 className="font-body font-bold text-xl text-white mb-1">{habit.name}</h4>
                    <div className="flex items-center gap-2">
                      <div
                        className="w-3 h-3 rounded-full"
                        style={{ backgroundColor: habit.color, boxShadow: `0 0 10px ${habit.color}` }}
                      />
                      <span className="text-sm text-slate-400">{habit.color}</span>
                    </div>
                    <p className="text-xs text-slate-500 mt-1">
                      {habit.start_date} até {habit.end_date}
                    </p>
                    <p className="text-xs text-slate-500">
                      {habit.frequency === "daily"
                        ? "Frequência: todos os dias"
                        : `Frequência: ${WEEKDAY_OPTIONS.filter((day) => (habit.selected_weekdays || []).includes(day.value)).map((day) => day.label).join(', ') || 'dias úteis'}`}
                    </p>
                  </div>

                  <div className="flex items-center gap-2">
                    <motion.button
                      whileHover={{ scale: 1.1 }}
                      whileTap={{ scale: 0.9 }}
                      onClick={() => handleStartEdit(habit)}
                      data-testid={`edit-habit-${habit.habit_id}`}
                      className="p-3 hover:bg-primary/10 rounded-xl transition-all text-slate-400 hover:text-primary"
                      title="Editar objetivo"
                    >
                      <Pencil className="w-5 h-5" />
                    </motion.button>

                    <motion.button
                      whileHover={{ scale: 1.1 }}
                      whileTap={{ scale: 0.9 }}
                      onClick={() => handleDeleteHabit(habit.habit_id)}
                      data-testid={`delete-habit-${habit.habit_id}`}
                      className="p-3 hover:bg-secondary/10 rounded-xl transition-all text-slate-400 hover:text-secondary"
                      title="Remover objetivo"
                    >
                      <Trash2 className="w-5 h-5" />
                    </motion.button>
                  </div>
                </div>
              </motion.div>
            ))
          )}
        </div>

      </main>
    </div>
  );
}
