import { motion } from "framer-motion";
import { Trophy, TrendingUp, Circle } from "lucide-react";

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
    <motion.div 
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      className="space-y-6"
    >
      {/* Progress Overview */}
      <div className="glass-card p-6">
        <h3 className="font-heading text-xl font-bold text-white mb-6 flex items-center gap-2" data-testid="progress-title">
          <TrendingUp className="w-5 h-5 text-primary" />
          Progresso
        </h3>

        {/* Completion Rate */}
        <div className="mb-6">
          <div className="flex items-baseline gap-2 mb-3">
            <motion.span 
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              transition={{ type: "spring", stiffness: 200 }}
              className="font-heading text-5xl font-bold text-primary" 
              data-testid="completion-rate"
            >
              {stats.completionRate}%
            </motion.span>
            <span className="text-sm text-slate-400 font-body">
              de dias perfeitos
            </span>
          </div>
          
          <div className="w-full bg-white/5 h-3 rounded-full overflow-hidden relative">
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${stats.completionRate}%` }}
              transition={{ duration: 1, ease: "easeOut" }}
              className="h-full bg-gradient-red relative"
            >
              <div className="absolute inset-0 bg-white/20 animate-pulse"></div>
            </motion.div>
          </div>
        </div>

        {/* Stats Grid */}
        <div className="space-y-3">
          <motion.div 
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="flex items-center justify-between py-3 border-b border-white/5"
            data-testid="perfect-days-stat"
          >
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-primary/10 rounded-xl flex items-center justify-center">
                <Trophy className="w-5 h-5 text-primary" strokeWidth={2} />
              </div>
              <span className="font-body text-slate-300">Dias perfeitos</span>
            </div>
            <span className="font-heading text-2xl font-bold text-primary">{stats.perfectDays}</span>
          </motion.div>

          <motion.div 
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
            className="flex items-center justify-between py-3 border-b border-white/5"
            data-testid="incomplete-days-stat"
          >
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-white/5 rounded-xl flex items-center justify-center">
                <Circle className="w-4 h-4 text-slate-400" fill="currentColor" />
              </div>
              <span className="font-body text-slate-300">Dias parciais</span>
            </div>
            <span className="font-heading text-2xl font-bold text-slate-400">{stats.incompleteDays}</span>
          </motion.div>

          <motion.div 
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
            className="flex items-center justify-between py-3"
            data-testid="empty-days-stat"
          >
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-white/5 rounded-xl flex items-center justify-center">
                <Circle className="w-4 h-4 text-slate-600" />
              </div>
              <span className="font-body text-slate-300">Dias vazios</span>
            </div>
            <span className="font-heading text-2xl font-bold text-slate-600">
              {stats.totalDays - stats.perfectDays - stats.incompleteDays}
            </span>
          </motion.div>
        </div>
      </div>

      {/* Habits List */}
      <div className="glass-card p-6">
        <h3 className="font-heading text-xl font-bold text-white mb-4" data-testid="habits-overview-title">
          Seus Hábitos
        </h3>
        
        {habits.length === 0 ? (
          <p className="text-slate-400 font-body text-sm text-center py-8">
            Nenhum hábito criado
          </p>
        ) : (
          <div className="space-y-3" data-testid="habits-list-sidebar">
            {habits.map((habit, index) => (
              <motion.div 
                key={habit.habit_id}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: index * 0.05 }}
                className="flex items-center gap-3 p-3 rounded-lg hover:bg-white/5 transition-colors"
              >
                <div
                  className="w-3 h-3 rounded-full"
                  style={{ 
                    backgroundColor: habit.color,
                    boxShadow: `0 0 10px ${habit.color}`
                  }}
                />
                <span className="font-body text-sm text-slate-300 flex-1">
                  {habit.name}
                </span>
              </motion.div>
            ))}
          </div>
        )}
      </div>
    </motion.div>
  );
}
