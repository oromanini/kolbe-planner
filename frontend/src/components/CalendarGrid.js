import { useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Check } from "lucide-react";
import { Dialog, DialogContent } from "./ui/dialog";

export default function CalendarGrid({
  year,
  month,
  habits,
  completions,
  onToggleCompletion,
  onCreateGoal,
  viewMode = "month",
  referenceDay = 1,
}) {
  const [selectedDay, setSelectedDay] = useState(null);
  const [isDialogOpen, setIsDialogOpen] = useState(false);

  const daysInMonth = new Date(year, month, 0).getDate();
  const firstDayOfMonth = new Date(year, month - 1, 1).getDay();


  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const toDate = (dateString) => {
    const [yearPart, monthPart, dayPart] = dateString.split('-').map(Number);
    return new Date(yearPart, monthPart - 1, dayPart);
  };

  const getDateForDay = (day) => new Date(year, month - 1, day);

  const isPastDay = (day) => {
    const date = getDateForDay(day);
    date.setHours(0, 0, 0, 0);
    return date < today;
  };

  const isHabitInPeriod = (habit, day) => {
    const date = getDateForDay(day);
    const start = toDate(habit.start_date);
    const end = toDate(habit.end_date);
    return date >= start && date <= end;
  };

  const canToggleAnyHabitOnDay = (day) => !isPastDay(day) && habits.some((habit) => isHabitInPeriod(habit, day));

  const getDayProgress = (day) => {
    const activeHabits = habits.filter((habit) => isHabitInPeriod(habit, day));
    if (activeHabits.length === 0) return { completed: 0, total: 0, percentage: 0 };

    const completedCount = activeHabits.filter((habit) => isHabitCompletedOnDay(habit.habit_id, day)).length;

    return {
      completed: completedCount,
      total: activeHabits.length,
      percentage: (completedCount / activeHabits.length) * 100,
    };
  };

  const handleDayClick = (day) => {
    if (!day || !canToggleAnyHabitOnDay(day)) return;
    setSelectedDay(day);
    setIsDialogOpen(true);
  };

  const handleToggle = async (habitId) => {
    const dateStr = `${year}-${String(month).padStart(2, '0')}-${String(selectedDay).padStart(2, '0')}`;
    await onToggleCompletion(habitId, dateStr);
  };

  const isHabitCompletedOnDay = (habitId, day) => {
    const dateStr = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
    const completion = completions.find((c) => c.habit_id === habitId && c.date === dateStr);
    return completion?.completed || false;
  };

  const visibleDays = useMemo(() => {
    if (viewMode === "month") {
      const monthDays = [];
      for (let i = 0; i < firstDayOfMonth; i++) monthDays.push(null);
      for (let day = 1; day <= daysInMonth; day++) monthDays.push(day);
      return monthDays;
    }

    const safeReferenceDay = Math.max(1, Math.min(referenceDay || 1, daysInMonth));
    const refDate = new Date(year, month - 1, safeReferenceDay);
    const dayOfWeek = refDate.getDay();
    const weekStart = new Date(refDate);
    weekStart.setDate(refDate.getDate() - dayOfWeek);

    return Array.from({ length: 7 }, (_, index) => {
      const date = new Date(weekStart);
      date.setDate(weekStart.getDate() + index);

      if (date.getFullYear() !== year || date.getMonth() !== month - 1) {
        return null;
      }

      return date.getDate();
    });
  }, [viewMode, referenceDay, daysInMonth, firstDayOfMonth, year, month]);

  return (
    <>
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.4 }}
        className="glass-card overflow-hidden"
      >
        <div className="grid grid-cols-7 bg-background-paper border-b border-white/5">
          {['Dom', 'Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb'].map((day, i) => (
            <div
              key={i}
              className="py-4 text-center text-xs font-body font-medium text-slate-500 uppercase tracking-widest"
            >
              {day}
            </div>
          ))}
        </div>

        <div className="grid grid-cols-7 gap-px bg-white/5" data-testid="calendar-grid">
          {visibleDays.map((day, index) => {
            if (!day) {
              return <div key={`empty-${index}`} className="bg-background-paper aspect-square"></div>;
            }

            const progress = getDayProgress(day);
            const isComplete = progress.percentage === 100 && progress.total > 0;
            const isPartial = progress.percentage > 0 && progress.percentage < 100;
            const dayLocked = !canToggleAnyHabitOnDay(day);
            const activeHabits = habits.filter((habit) => isHabitInPeriod(habit, day));

            return (
              <motion.button
                key={`${viewMode}-${day}`}
                data-testid={`calendar-day-${day}`}
                onClick={() => handleDayClick(day)}
                whileHover={dayLocked ? undefined : { scale: 1.05 }}
                whileTap={dayLocked ? undefined : { scale: 0.95 }}
                className={`
                  bg-background-paper aspect-square p-2 relative transition-all group min-h-[80px]
                  ${isComplete ? 'bg-gradient-to-br from-primary/20 to-primary/5 shadow-glow' : ''}
                  ${isPartial ? 'bg-white/5' : ''}
                  ${dayLocked ? 'opacity-45 cursor-not-allowed' : 'hover:bg-background-subtle cursor-pointer'}
                `}
              >
                <div className={`text-xs font-body font-medium mb-1.5 text-right ${isComplete ? 'text-primary font-bold' : 'text-slate-400'}`}>
                  {day}
                </div>

                <div className="space-y-0.5 text-left overflow-hidden">
                  {activeHabits.slice(0, 4).map((habit) => {
                    const completed = isHabitCompletedOnDay(habit.habit_id, day);
                    return (
                      <div key={habit.habit_id} className="flex items-center gap-1 text-[10px] leading-tight">
                        <div
                          className="w-1.5 h-1.5 rounded-full flex-shrink-0"
                          style={{
                            backgroundColor: completed ? habit.color : 'rgba(255,255,255,0.15)',
                            boxShadow: completed ? `0 0 6px ${habit.color}` : 'none',
                          }}
                        />
                        <span className={`truncate ${completed ? 'text-slate-300' : 'text-slate-600'}`}>{habit.name}</span>
                      </div>
                    );
                  })}
                  {activeHabits.length > 4 && <div className="text-[9px] text-slate-600 text-center">+{activeHabits.length - 4}</div>}
                </div>

                {isComplete && (
                  <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    className="absolute inset-0 border-2 border-primary/50 pointer-events-none rounded-sm"
                  />
                )}
              </motion.button>
            );
          })}
        </div>
      </motion.div>

      <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
        <DialogContent className="sm:max-w-md glass-card-heavy border-white/10">
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="font-heading text-3xl font-medium text-white" data-testid="day-dialog-title">
                Dia <span className="text-primary">{selectedDay}</span>
              </h3>
            </div>

            {habits.filter((habit) => selectedDay && isHabitInPeriod(habit, selectedDay)).length === 0 ? (
              <div className="text-center py-10 space-y-4">
                <p className="text-slate-400 font-body">Nenhum objetivo ativo nesta data.</p>
                <button
                  onClick={() => {
                    setIsDialogOpen(false);
                    onCreateGoal?.();
                  }}
                  className="px-4 py-2 rounded-lg bg-primary text-white font-body font-medium hover:opacity-90 transition-opacity"
                >
                  Gerenciar objetivos
                </button>
              </div>
            ) : (
              <div className="space-y-3" data-testid="habits-list">
                <AnimatePresence>
                  {habits.filter((habit) => selectedDay && isHabitInPeriod(habit, selectedDay)).map((habit, index) => {
                    const completed = selectedDay ? isHabitCompletedOnDay(habit.habit_id, selectedDay) : false;

                    return (
                      <motion.button
                        key={habit.habit_id}
                        initial={{ opacity: 0, x: -20 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: index * 0.05 }}
                        data-testid={`habit-toggle-${habit.habit_id}`}
                        onClick={() => handleToggle(habit.habit_id)}
                        whileHover={{ scale: 1.02 }}
                        whileTap={{ scale: 0.98 }}
                        className={`
                          w-full p-4 rounded-xl border-2 transition-all flex items-center gap-4
                          ${completed ? 'border-primary/50 bg-primary/10 shadow-glow' : 'border-white/10 hover:border-white/20 bg-white/5'}
                        `}
                      >
                        <div
                          className="w-8 h-8 rounded-full flex items-center justify-center transition-all relative overflow-hidden"
                          style={{
                            backgroundColor: completed ? habit.color : 'transparent',
                            border: completed ? 'none' : `2px solid ${habit.color}`,
                            boxShadow: completed ? `0 0 20px ${habit.color}` : 'none',
                          }}
                        >
                          {completed && (
                            <motion.div
                              initial={{ scale: 0, rotate: -180 }}
                              animate={{ scale: 1, rotate: 0 }}
                              transition={{ type: "spring", stiffness: 200 }}
                            >
                              <Check className="w-5 h-5 text-white" strokeWidth={3} />
                            </motion.div>
                          )}
                        </div>

                        <span className="font-body font-medium text-white flex-1 text-left">{habit.name}</span>
                      </motion.button>
                    );
                  })}
                </AnimatePresence>
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
