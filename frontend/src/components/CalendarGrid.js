import { useState } from "react";
import { X } from "lucide-react";
import { Dialog, DialogContent } from "./ui/dialog";

export default function CalendarGrid({ year, month, habits, completions, onToggleCompletion }) {
  const [selectedDay, setSelectedDay] = useState(null);
  const [isDialogOpen, setIsDialogOpen] = useState(false);

  // Get days in month
  const daysInMonth = new Date(year, month, 0).getDate();
  const firstDayOfMonth = new Date(year, month - 1, 1).getDay();
  
  // Create calendar grid
  const calendarDays = [];
  
  // Empty cells before first day
  for (let i = 0; i < firstDayOfMonth; i++) {
    calendarDays.push(null);
  }
  
  // Days of month
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
      <div className="bg-white border border-[#E5E7EB] rounded-sm shadow-sm overflow-hidden">
        {/* Week days header */}
        <div className="grid grid-cols-7 bg-paper border-b border-[#E5E7EB]">
          {['Dom', 'Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb'].map((day, i) => (
            <div 
              key={i} 
              className="py-3 text-center text-xs font-body font-medium text-[#8A8F98] uppercase tracking-wider"
            >
              {day}
            </div>
          ))}
        </div>

        {/* Calendar grid */}
        <div className="grid grid-cols-7 gap-px bg-[#E5E7EB]" data-testid="calendar-grid">
          {calendarDays.map((day, index) => {
            if (!day) {
              return <div key={`empty-${index}`} className="bg-white aspect-square"></div>;
            }

            const progress = getDayProgress(day);
            const isComplete = progress.percentage === 100 && progress.total > 0;
            const isPartial = progress.percentage > 0 && progress.percentage < 100;

            return (
              <button
                key={day}
                data-testid={`calendar-day-${day}`}
                onClick={() => handleDayClick(day)}
                className={`
                  bg-white aspect-square p-2 relative hover:bg-gray-50 transition-all cursor-pointer group
                  ${isComplete ? 'bg-victory-gold/30 hover:bg-victory-gold/40' : ''}
                  ${isPartial ? 'bg-victory-gold/10' : ''}
                `}
              >
                {/* Day number */}
                <div className="text-sm font-body font-medium text-navy mb-1">
                  {day}
                </div>

                {/* Habit indicators */}
                <div className="flex flex-wrap gap-1 justify-center">
                  {habits.slice(0, 6).map((habit) => {
                    const completed = isHabitCompletedOnDay(habit.habit_id, day);
                    return (
                      <div
                        key={habit.habit_id}
                        className="w-1.5 h-1.5 rounded-full transition-colors"
                        style={{
                          backgroundColor: completed ? habit.color : '#E5E7EB'
                        }}
                      />
                    );
                  })}
                </div>

                {/* Victory indicator */}
                {isComplete && (
                  <div className="absolute inset-0 border-2 border-victory-gold pointer-events-none"></div>
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* Day Dialog */}
      <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
        <DialogContent className="sm:max-w-md bg-white">
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="font-heading text-2xl text-navy" data-testid="day-dialog-title">
                Dia {selectedDay}
              </h3>
              <button
                onClick={() => setIsDialogOpen(false)}
                data-testid="close-day-dialog"
                className="p-1 hover:bg-paper rounded-sm transition-colors"
              >
                <X className="w-5 h-5 text-navy" />
              </button>
            </div>

            {habits.length === 0 ? (
              <p className="text-[#8A8F98] font-body text-center py-8">
                Nenhum hábito criado ainda.
              </p>
            ) : (
              <div className="space-y-2" data-testid="habits-list">
                {habits.map((habit) => {
                  const completed = selectedDay ? isHabitCompletedOnDay(habit.habit_id, selectedDay) : false;
                  
                  return (
                    <button
                      key={habit.habit_id}
                      data-testid={`habit-toggle-${habit.habit_id}`}
                      onClick={() => handleToggle(habit.habit_id)}
                      className={`
                        w-full p-4 rounded-sm border-2 transition-all flex items-center gap-3
                        ${completed 
                          ? 'border-navy bg-navy/5' 
                          : 'border-[#E5E7EB] hover:border-navy/30'
                        }
                      `}
                    >
                      <div
                        className="w-6 h-6 rounded-full flex items-center justify-center transition-all"
                        style={{
                          backgroundColor: completed ? habit.color : 'transparent',
                          border: completed ? 'none' : `2px solid ${habit.color}`
                        }}
                      >
                        {completed && (
                          <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                          </svg>
                        )}
                      </div>
                      
                      <span className="font-body font-medium text-navy flex-1 text-left">
                        {habit.name}
                      </span>
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
