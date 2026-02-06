import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, Plus, Trash2, Palette } from "lucide-react";
import { toast } from "sonner";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const PRESET_COLORS = [
  { name: "Navy", value: "#0F1B2D" },
  { name: "Imperial Red", value: "#C0392B" },
  { name: "Blue", value: "#3B82F6" },
  { name: "Green", value: "#10B981" },
  { name: "Purple", value: "#8B5CF6" },
  { name: "Orange", value: "#F97316" },
  { name: "Pink", value: "#EC4899" },
  { name: "Teal", value: "#14B8A6" },
];

const PRESET_ICONS = [
  "circle", "book-open", "activity", "brain", "graduation-cap",
  "coffee", "music", "heart", "moon", "sun", "globe"
];

export default function HabitManager() {
  const navigate = useNavigate();
  const [habits, setHabits] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAddForm, setShowAddForm] = useState(false);
  const [newHabit, setNewHabit] = useState({
    name: "",
    color: "#0F1B2D",
    icon: "circle"
  });

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

  const handleAddHabit = async (e) => {
    e.preventDefault();
    
    if (!newHabit.name.trim()) {
      toast.error('Digite um nome para o hábito');
      return;
    }

    if (habits.length >= 10) {
      toast.error('Máximo de 10 hábitos atingido');
      return;
    }

    try {
      const res = await fetch(`${API}/habits`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(newHabit)
      });

      if (!res.ok) throw new Error('Failed to create habit');

      toast.success('Hábito criado!');
      setNewHabit({ name: "", color: "#0F1B2D", icon: "circle" });
      setShowAddForm(false);
      loadHabits();
    } catch (error) {
      console.error('Error creating habit:', error);
      toast.error('Erro ao criar hábito');
    }
  };

  const handleDeleteHabit = async (habitId) => {
    if (!window.confirm('Tem certeza? Isso apagará todos os registros deste hábito.')) {
      return;
    }

    try {
      const res = await fetch(`${API}/habits/${habitId}`, {
        method: 'DELETE',
        credentials: 'include'
      });

      if (!res.ok) throw new Error('Failed to delete');

      toast.success('Hábito removido');
      loadHabits();
    } catch (error) {
      console.error('Error deleting habit:', error);
      toast.error('Erro ao remover hábito');
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
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button
              onClick={() => navigate('/dashboard')}
              data-testid="back-to-dashboard"
              className="p-2 hover:bg-paper rounded-sm transition-colors"
            >
              <ArrowLeft className="w-5 h-5 text-navy" />
            </button>
            <h1 className="font-heading text-2xl text-navy" data-testid="habit-manager-title">
              Gerenciar Hábitos
            </h1>
          </div>
          
          <div className="text-sm text-[#8A8F98] font-body">
            {habits.length} / 10 hábitos
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Add Habit Button */}
        {!showAddForm && habits.length < 10 && (
          <button
            onClick={() => setShowAddForm(true)}
            data-testid="show-add-habit-form"
            className="w-full mb-6 p-6 border-2 border-dashed border-[#E5E7EB] rounded-sm hover:border-navy/30 transition-all flex items-center justify-center gap-2 text-navy font-body"
          >
            <Plus className="w-5 h-5" />
            Adicionar novo hábito
          </button>
        )}

        {/* Add Habit Form */}
        {showAddForm && (
          <form onSubmit={handleAddHabit} className="mb-6 bg-white border border-[#E5E7EB] rounded-sm p-6 shadow-sm">
            <h3 className="font-heading text-xl text-navy mb-4">Novo Hábito</h3>
            
            <div className="space-y-4">
              {/* Name Input */}
              <div>
                <label className="block text-sm font-body font-medium text-navy mb-2">
                  Nome do hábito
                </label>
                <input
                  type="text"
                  data-testid="habit-name-input"
                  value={newHabit.name}
                  onChange={(e) => setNewHabit({ ...newHabit, name: e.target.value })}
                  placeholder="Ex: Exercício, Leitura, Meditação..."
                  className="w-full px-4 py-2 border border-[#E5E7EB] rounded-sm font-body focus:outline-none focus:ring-2 focus:ring-navy"
                  maxLength={30}
                />
              </div>

              {/* Color Picker */}
              <div>
                <label className="block text-sm font-body font-medium text-navy mb-2 flex items-center gap-2">
                  <Palette className="w-4 h-4" />
                  Cor
                </label>
                <div className="flex flex-wrap gap-2">
                  {PRESET_COLORS.map((color) => (
                    <button
                      key={color.value}
                      type="button"
                      data-testid={`color-${color.name}`}
                      onClick={() => setNewHabit({ ...newHabit, color: color.value })}
                      className={`
                        w-10 h-10 rounded-sm transition-all
                        ${newHabit.color === color.value ? 'ring-2 ring-navy ring-offset-2' : 'hover:scale-110'}
                      `}
                      style={{ backgroundColor: color.value }}
                      title={color.name}
                    />
                  ))}
                </div>
              </div>

              {/* Actions */}
              <div className="flex gap-3 pt-2">
                <button
                  type="submit"
                  data-testid="create-habit-submit"
                  className="flex-1 bg-navy text-white px-6 py-2 rounded-sm font-body font-medium hover:bg-navy/90 transition-all"
                >
                  Criar hábito
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setShowAddForm(false);
                    setNewHabit({ name: "", color: "#0F1B2D", icon: "circle" });
                  }}
                  data-testid="cancel-add-habit"
                  className="px-6 py-2 border border-[#E5E7EB] rounded-sm font-body hover:bg-paper transition-all"
                >
                  Cancelar
                </button>
              </div>
            </div>
          </form>
        )}

        {/* Habits List */}
        <div className="space-y-3">
          {habits.length === 0 ? (
            <div className="text-center py-12 bg-white border border-[#E5E7EB] rounded-sm">
              <p className="text-[#8A8F98] font-body">
                Nenhum hábito criado ainda.
              </p>
            </div>
          ) : (
            habits.map((habit, index) => (
              <div
                key={habit.habit_id}
                data-testid={`habit-item-${habit.habit_id}`}
                className="bg-white border border-[#E5E7EB] rounded-sm p-4 shadow-sm flex items-center gap-4 hover:shadow-md transition-all"
              >
                <div
                  className="w-12 h-12 rounded-sm flex items-center justify-center shrink-0"
                  style={{ backgroundColor: habit.color }}
                >
                  <span className="text-white text-xl font-bold">
                    {index + 1}
                  </span>
                </div>

                <div className="flex-1">
                  <h4 className="font-body font-medium text-navy">
                    {habit.name}
                  </h4>
                </div>

                <button
                  onClick={() => handleDeleteHabit(habit.habit_id)}
                  data-testid={`delete-habit-${habit.habit_id}`}
                  className="p-2 hover:bg-imperial-red/10 rounded-sm transition-all"
                  title="Remover hábito"
                >
                  <Trash2 className="w-5 h-5 text-imperial-red" />
                </button>
              </div>
            ))
          )}
        </div>

        {habits.length >= 10 && (
          <div className="mt-6 p-4 bg-victory-gold/20 border border-victory-gold rounded-sm">
            <p className="text-sm font-body text-navy text-center">
              Você atingiu o limite de 10 hábitos. Remova um hábito para adicionar outro.
            </p>
          </div>
        )}
      </main>
    </div>
  );
}
