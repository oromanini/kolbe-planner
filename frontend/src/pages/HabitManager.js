import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowLeft, Plus, Trash2, Palette, Sparkles, Pencil } from "lucide-react";
import { toast } from "sonner";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

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

export default function HabitManager() {
  const navigate = useNavigate();
  const [habits, setHabits] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAddForm, setShowAddForm] = useState(false);
  const [isCreatingHabit, setIsCreatingHabit] = useState(false);
  const [editingHabitId, setEditingHabitId] = useState(null);

  const todayKey = new Date(Date.now() - new Date().getTimezoneOffset() * 60000)
    .toISOString()
    .split('T')[0];

  const emptyHabit = {
    name: "",
    color: "#CD1C33",
    icon: "circle",
    start_date: todayKey,
    end_date: todayKey,
  };

  const [newHabit, setNewHabit] = useState(emptyHabit);

  useEffect(() => {
    loadHabits();
  }, []);

  const loadHabits = async () => {
    try {
      const res = await fetch(`${API}/habits`, { credentials: 'include' });
      const data = await res.json();
      setHabits(data);
    } catch (error) {
      console.error('Error loading habits:', error);
      toast.error('Erro ao carregar hábitos');
    } finally {
      setLoading(false);
    }
  };

  const validateHabit = (habitPayload, isEditing = false) => {
    if (!habitPayload.name.trim()) {
      toast.error('Digite um nome para o objetivo');
      return false;
    }

    if (!isEditing && habits.length >= 10) {
      toast.error('Máximo de 10 hábitos atingido');
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

    return true;
  };

  const handleAddHabit = async (e) => {
    e.preventDefault();

    if (isCreatingHabit || !validateHabit(newHabit)) return;

    try {
      setIsCreatingHabit(true);
      const res = await fetch(`${API}/habits`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          name: newHabit.name.trim(),
          color: newHabit.color,
          icon: newHabit.icon,
          start_date: newHabit.start_date,
          end_date: newHabit.end_date,
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
    });
    setShowAddForm(false);
  };

  const handleSaveEdit = async (e) => {
    e.preventDefault();
    if (!editingHabitId || isCreatingHabit || !validateHabit(newHabit, true)) return;

    try {
      setIsCreatingHabit(true);
      const res = await fetch(`${API}/habits/${editingHabitId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          name: newHabit.name.trim(),
          color: newHabit.color,
          icon: newHabit.icon,
          start_date: newHabit.start_date,
          end_date: newHabit.end_date,
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
      const res = await fetch(`${API}/habits/${habitId}`, {
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
              {habits.length} <span className="text-primary">/ 10</span>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {!showAddForm && !isEditing && habits.length < 10 && (
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

        {(showAddForm || isEditing) && (
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

        <div className="space-y-4">
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

        {habits.length >= 10 && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="mt-8 p-6 bg-primary/10 border border-primary/30 rounded-2xl">
            <p className="text-sm font-body text-slate-300 text-center">
              Você atingiu o limite de <span className="text-primary font-bold">10 hábitos</span>. Remova um hábito para adicionar outro.
            </p>
          </motion.div>
        )}
      </main>
    </div>
  );
}
