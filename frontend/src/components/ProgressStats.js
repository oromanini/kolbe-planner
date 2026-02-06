import { Check, X } from "lucide-react";

export default function ProgressStats({ year, month, habits, completions }) {
  const daysInMonth = new Date(year, month, 0).getDate();
  
  const calculateStats = () => {
    if (habits.length === 0) {
      return {
        perfectDays: 0,
        completionRate: 0,
        incompleteDays: 0,
        totalDays: daysInMonth
      };
    }

    let perfectDays = 0;
    let incompleteDays = 0;

    for (let day = 1; day <= daysInMonth; day++) {
      const dateStr = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
      const dayCompletions = completions.filter(c => c.date === dateStr && c.completed);
      
      if (dayCompletions.length === habits.length) {
        perfectDays++;
      } else if (dayCompletions.length > 0) {
        incompleteDays++;
      }
    }

    const completionRate = Math.round((perfectDays / daysInMonth) * 100);

    return {
      perfectDays,
      completionRate,
      incompleteDays,
      totalDays: daysInMonth
    };
  };

  const stats = calculateStats();

  return (
    <div className="space-y-6">
      {/* Progress Overview */}
      <div className="bg-white border border-[#E5E7EB] rounded-sm p-6 shadow-sm">
        <h3 className="font-heading text-xl text-navy mb-6" data-testid="progress-title">
          Progresso do Mês
        </h3>

        {/* Completion Rate */}
        <div className="mb-6">
          <div className="flex items-baseline gap-2 mb-2">
            <span className="font-heading text-4xl text-navy" data-testid="completion-rate">
              {stats.completionRate}%
            </span>
            <span className="text-sm text-[#8A8F98] font-body">
              de dias perfeitos
            </span>
          </div>
          
          <div className="w-full bg-[#E5E7EB] h-2 rounded-full overflow-hidden">
            <div
              className="h-full bg-navy transition-all duration-500"
              style={{ width: `${stats.completionRate}%` }}
            />
          </div>
        </div>

        {/* Stats Grid */}
        <div className="space-y-3">
          <div 
            className="flex items-center justify-between py-3 border-b border-[#E5E7EB]"
            data-testid="perfect-days-stat"
          >
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 bg-victory-gold/30 rounded-sm flex items-center justify-center">
                <Check className="w-5 h-5 text-navy" strokeWidth={2.5} />
              </div>
              <span className="font-body text-navy">Dias perfeitos</span>
            </div>
            <span className="font-heading text-2xl text-navy">{stats.perfectDays}</span>
          </div>

          <div 
            className="flex items-center justify-between py-3 border-b border-[#E5E7EB]"
            data-testid="incomplete-days-stat"
          >
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 bg-paper rounded-sm flex items-center justify-center border border-[#E5E7EB]">
                <div className="w-2 h-2 rounded-full bg-[#8A8F98]"></div>
              </div>
              <span className="font-body text-navy">Dias parciais</span>
            </div>
            <span className="font-heading text-2xl text-navy">{stats.incompleteDays}</span>
          </div>

          <div 
            className="flex items-center justify-between py-3"
            data-testid="empty-days-stat"
          >
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 bg-paper rounded-sm flex items-center justify-center border border-[#E5E7EB]">
                <X className="w-5 h-5 text-[#8A8F98]" strokeWidth={2} />
              </div>
              <span className="font-body text-navy">Dias vazios</span>
            </div>
            <span className="font-heading text-2xl text-navy">
              {stats.totalDays - stats.perfectDays - stats.incompleteDays}
            </span>
          </div>
        </div>
      </div>

      {/* Habits List */}
      <div className="bg-white border border-[#E5E7EB] rounded-sm p-6 shadow-sm">
        <h3 className="font-heading text-xl text-navy mb-4" data-testid="habits-overview-title">
          Seus Hábitos
        </h3>
        
        {habits.length === 0 ? (
          <p className="text-[#8A8F98] font-body text-sm text-center py-4">
            Nenhum hábito criado
          </p>
        ) : (
          <div className="space-y-3" data-testid="habits-list-sidebar">
            {habits.map((habit) => (
              <div key={habit.habit_id} className="flex items-center gap-3">
                <div
                  className="w-4 h-4 rounded-full"
                  style={{ backgroundColor: habit.color }}
                />
                <span className="font-body text-sm text-navy flex-1">
                  {habit.name}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
