import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X, Check } from "lucide-react";
import { Dialog, DialogContent } from "./ui/dialog";

export default function CalendarGrid({ year, month, habits, completions, onToggleCompletion }) {
  const [selectedDay, setSelectedDay] = useState(null);
  const [isDialogOpen, setIsDialogOpen] = useState(false);

  const daysInMonth = new Date(year, month, 0).getDate();
  const firstDayOfMonth = new Date(year, month - 1, 1).getDay();
  
  const calendarDays = [];
  
  for (let i = 0; i < firstDayOfMonth; i++) {
    calendarDays.push(null);
  }
  
  for (let day = 1; day <= daysInMonth; day++) {
    calendarDays.push(day);
  }

  const getCompletionsForDay = (day) => {
    const dateStr = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
    return completions.filter(c => c.date === dateStr);
  };

  const getDayProgress = (day) => {
    if (habits.length === 0) return { completed: 0, total: 0, percentage: 0 };
    
    const dayCompletions = getCompletionsForDay(day);
    const completedCount = dayCompletions.filter(c => c.completed).length;
    
    return {
      completed: completedCount,
      total: habits.length,
      percentage: (completedCount / habits.length) * 100
    };
  };

  const handleDayClick = (day) => {
    if (!day) return;
    setSelectedDay(day);
    setIsDialogOpen(true);
  };

  const handleToggle = async (habitId) => {
    const dateStr = `${year}-${String(month).padStart(2, '0')}-${String(selectedDay).padStart(2, '0')}`;
    await onToggleCompletion(habitId, dateStr);
  };

  const isHabitCompletedOnDay = (habitId, day) => {
    const dateStr = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
    const completion = completions.find(c => c.habit_id === habitId && c.date === dateStr);
    return completion?.completed || false;
  };

  return (
    <>
      <motion.div 
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.4 }}
        className="glass-card overflow-hidden"
      >
        {/* Week days header */}
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

        {/* Calendar grid */}
        <div className="grid grid-cols-7 gap-px bg-white/5" data-testid="calendar-grid">
          {calendarDays.map((day, index) => {
            if (!day) {
              return <div key={`empty-${index}`} className="bg-background-paper aspect-square"></div>;
            }

            const progress = getDayProgress(day);
            const isComplete = progress.percentage === 100 && progress.total > 0;
            const isPartial = progress.percentage > 0 && progress.percentage < 100;

            return (
              <motion.button
                key={day}
                data-testid={`calendar-day-${day}`}
                onClick={() => handleDayClick(day)}
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                className={`
                  bg-background-paper aspect-square p-2 relative hover:bg-background-subtle transition-all cursor-pointer group
                  ${isComplete ? 'bg-gradient-to-br from-primary/20 to-primary/5 shadow-glow' : ''}
                  ${isPartial ? 'bg-white/5' : ''}
                `}
              >
                {/* Day number */}
                <div className={`
                  text-xs font-body font-medium mb-1.5 text-right
                  ${isComplete ? 'text-primary font-bold' : 'text-slate-400'}
                `}>
                  {day}
                </div>

                {/* Habit list with names */}
                <div className="space-y-0.5 text-left overflow-hidden">
                  {habits.slice(0, 4).map((habit) => {
                    const completed = isHabitCompletedOnDay(habit.habit_id, day);
                    return (
                      <div
                        key={habit.habit_id}
                        className="flex items-center gap-1 text-[10px] leading-tight"
                      >
                        <div
                          className="w-1.5 h-1.5 rounded-full flex-shrink-0"
                          style={{
                            backgroundColor: completed ? habit.color : 'rgba(255,255,255,0.15)',
                            boxShadow: completed ? `0 0 6px ${habit.color}` : 'none'
                          }}
                        />
                        <span className={`truncate ${completed ? 'text-slate-300' : 'text-slate-600'}`}>
                          {habit.name}
                        </span>
                      </div>
                    );
                  })}
                  {habits.length > 4 && (
                    <div className="text-[9px] text-slate-600 text-center">
                      +{habits.length - 4}
                    </div>
                  )}
                </div>

                {/* Victory glow */}
                {isComplete && (
                  <motion.div 
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    className="absolute inset-0 border-2 border-primary/50 pointer-events-none rounded-sm"
                  ></motion.div>
                )}
              </motion.button>
            );
          })}
        </div>
      </motion.div>

      {/* Day Dialog */}
      <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
        <DialogContent className="sm:max-w-md glass-card-heavy border-white/10">
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="font-heading text-3xl font-medium text-white" data-testid="day-dialog-title">
                Dia <span className="text-primary">{selectedDay}</span>
              </h3>
              <button
                onClick={() => setIsDialogOpen(false)}
                data-testid="close-day-dialog"
                className="p-2 hover:bg-white/5 rounded-lg transition-colors text-slate-400 hover:text-white"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {habits.length === 0 ? (
              <p className="text-slate-400 font-body text-center py-12">
                Nenhum hábito criado ainda.
              </p>
            ) : (
              <div className="space-y-3" data-testid="habits-list">
                <AnimatePresence>
                  {habits.map((habit, index) => {
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
                          ${completed 
                            ? 'border-primary/50 bg-primary/10 shadow-glow' 
                            : 'border-white/10 hover:border-white/20 bg-white/5'
                          }
                        `}
                      >
                        <div
                          className="w-8 h-8 rounded-full flex items-center justify-center transition-all relative overflow-hidden"
                          style={{
                            backgroundColor: completed ? habit.color : 'transparent',
                            border: completed ? 'none' : `2px solid ${habit.color}`,
                            boxShadow: completed ? `0 0 20px ${habit.color}` : 'none'
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
                        
                        <span className="font-body font-medium text-white flex-1 text-left">
                          {habit.name}
                        </span>
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
