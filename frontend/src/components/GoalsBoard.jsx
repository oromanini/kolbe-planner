import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Check, Maximize2, Minimize2, Plus } from "lucide-react";

const WEEKDAY_LABELS = ["Seg", "Ter", "Qua", "Qui", "Sex"];

const hexToRgb = (hex) => {
  const normalized = hex?.replace('#', '') || "CD1C33";
  const full = normalized.length === 3
    ? normalized.split('').map((char) => char + char).join('')
    : normalized;
  return {
    r: parseInt(full.slice(0, 2), 16) || 0,
    g: parseInt(full.slice(2, 4), 16) || 0,
    b: parseInt(full.slice(4, 6), 16) || 0,
  };
};

const mix = (hex, target, amount) => {
  const color = hexToRgb(hex);
  const blend = (channel, targetChannel) => Math.round(channel + (targetChannel - channel) * amount);
  return `rgb(${blend(color.r, target.r)}, ${blend(color.g, target.g)}, ${blend(color.b, target.b)})`;
};

const PAPER = { r: 255, g: 251, b: 230 };
const INK = { r: 26, g: 18, b: 6 };

// Paper tinted by the goal color, dark ink of the same hue: keeps each note
// readable from across a room while still reading as "that goal's color".
const paperColor = (hex) => mix(hex, PAPER, 0.86);
const paperShade = (hex) => mix(hex, PAPER, 0.7);
const inkColor = (hex) => mix(hex, INK, 0.72);

// Deterministic tilt so a note keeps the same angle between renders.
const tiltFor = (id) => {
  const seed = String(id)
    .split('')
    .reduce((acc, char) => acc + char.charCodeAt(0), 0);
  return ((seed % 7) - 3) * 0.9;
};

const frequencyLabel = (habit) => {
  if (habit.frequency === "custom") {
    const days = (habit.selected_weekdays || [])
      .filter((value) => value >= 0 && value < WEEKDAY_LABELS.length)
      .map((value) => WEEKDAY_LABELS[value]);
    return days.length ? days.join(', ') : 'Dias úteis';
  }
  if (habit.frequency === "weekdays") return 'Dias úteis';
  return 'Todos os dias';
};

const shortDate = (dateString) => {
  if (!dateString) return '';
  const [, month, day] = dateString.split('-');
  return `${day}/${month}`;
};

const isScheduledToday = (habit, todayKey) => {
  if (!habit.start_date || !habit.end_date) return false;
  if (todayKey < habit.start_date || todayKey > habit.end_date) return false;

  const [year, month, day] = todayKey.split('-').map(Number);
  const weekday = new Date(year, month - 1, day).getDay();

  if (habit.frequency === "weekdays") return weekday >= 1 && weekday <= 5;
  if (habit.frequency === "custom") {
    // selected_weekdays uses 0 = Seg, while getDay() uses 0 = Dom.
    return (habit.selected_weekdays || []).map((value) => value + 1).includes(weekday);
  }
  return true;
};

export default function GoalsBoard({
  habits,
  completions,
  todayKey,
  onToggleCompletion,
  onCreateGoal,
}) {
  const boardRef = useRef(null);
  const wakeLockRef = useRef(null);
  const [isNativeFullscreen, setIsNativeFullscreen] = useState(false);
  // Fallback for browsers that block or don't implement the Fullscreen API
  // (iOS Safari, embedded webviews): fill the viewport with CSS instead.
  const [isExpanded, setIsExpanded] = useState(false);
  const [pendingHabitId, setPendingHabitId] = useState(null);

  const isFullscreen = isNativeFullscreen || isExpanded;

  const todayHabits = useMemo(
    () => habits.filter((habit) => isScheduledToday(habit, todayKey)),
    [habits, todayKey],
  );

  const isCompleted = useCallback(
    (habitId) => completions.some(
      (completion) => completion.habit_id === habitId
        && completion.date === todayKey
        && completion.completed,
    ),
    [completions, todayKey],
  );

  const completedCount = todayHabits.filter((habit) => isCompleted(habit.habit_id)).length;
  const progress = todayHabits.length ? (completedCount / todayHabits.length) * 100 : 0;

  const todayLabel = useMemo(() => {
    const [year, month, day] = todayKey.split('-').map(Number);
    const label = new Date(year, month - 1, day).toLocaleDateString('pt-BR', {
      weekday: 'long',
      day: 'numeric',
      month: 'long',
    });
    return label.charAt(0).toUpperCase() + label.slice(1);
  }, [todayKey]);

  useEffect(() => {
    const handleFullscreenChange = () => {
      setIsNativeFullscreen(document.fullscreenElement === boardRef.current);
    };

    document.addEventListener('fullscreenchange', handleFullscreenChange);
    return () => document.removeEventListener('fullscreenchange', handleFullscreenChange);
  }, []);

  // The native Escape shortcut only exists in real fullscreen.
  useEffect(() => {
    if (!isExpanded) return undefined;

    const handleKeyDown = (event) => {
      if (event.key === 'Escape') setIsExpanded(false);
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isExpanded]);

  // Keep the TV/projector awake while the board is on screen.
  useEffect(() => {
    let released = false;

    const requestWakeLock = async () => {
      if (!isFullscreen || !navigator.wakeLock) return;
      try {
        const sentinel = await navigator.wakeLock.request('screen');
        if (released) {
          sentinel.release().catch(() => {});
          return;
        }
        wakeLockRef.current = sentinel;
      } catch {
        // Wake lock is a nice-to-have; ignore denials.
      }
    };

    requestWakeLock();

    return () => {
      released = true;
      wakeLockRef.current?.release?.().catch(() => {});
      wakeLockRef.current = null;
    };
  }, [isFullscreen]);

  const toggleFullscreen = async () => {
    if (document.fullscreenElement) {
      try {
        await document.exitFullscreen();
      } catch (error) {
        console.error('Fullscreen error:', error);
      }
      return;
    }

    if (isExpanded) {
      setIsExpanded(false);
      return;
    }

    try {
      if (!boardRef.current?.requestFullscreen) throw new Error('unsupported');
      await boardRef.current.requestFullscreen();
    } catch {
      setIsExpanded(true);
    }
  };

  const handleToggle = async (habitId) => {
    if (pendingHabitId) return;
    try {
      setPendingHabitId(habitId);
      await onToggleCompletion(habitId, todayKey);
    } finally {
      setPendingHabitId(null);
    }
  };

  const columns = useMemo(() => {
    const total = todayHabits.length;
    if (total <= 1) return 1;
    if (isFullscreen) {
      if (total <= 2) return 2;
      if (total <= 6) return 3;
      return 4;
    }
    if (total <= 4) return 2;
    return 3;
  }, [todayHabits.length, isFullscreen]);

  return (
    <div
      ref={boardRef}
      data-testid="goals-board"
      className={`cork-board overflow-hidden ${
        isExpanded ? 'fixed inset-0 z-[100]' : 'relative'
      } ${
        isFullscreen
          ? 'h-screen w-screen flex flex-col p-6 sm:p-10'
          : 'rounded-3xl border-[10px] border-[#4a2f1b] shadow-2xl p-5 sm:p-8'
      }`}
    >
      <div className={`relative z-10 flex flex-wrap items-center justify-between gap-4 ${isFullscreen ? 'mb-6' : 'mb-6'}`}>
        <div>
          <p
            className="font-heading text-[#fff6dd] drop-shadow-[0_2px_6px_rgba(0,0,0,0.5)]"
            style={{ fontSize: isFullscreen ? 'clamp(1.75rem, 3vw, 3.25rem)' : '1.5rem' }}
            data-testid="board-date"
          >
            {todayLabel}
          </p>
          <p
            className="font-body text-[#f0dcae]/80"
            style={{ fontSize: isFullscreen ? 'clamp(0.95rem, 1.4vw, 1.5rem)' : '0.875rem' }}
          >
            {todayHabits.length === 0
              ? 'Nenhuma meta programada para hoje'
              : `${completedCount} de ${todayHabits.length} ${todayHabits.length === 1 ? 'meta concluída' : 'metas concluídas'}`}
          </p>
        </div>

        <div className="flex items-center gap-3">
          {todayHabits.length > 0 && (
            <div className={`hidden sm:flex items-center gap-3 ${isFullscreen ? 'min-w-[260px]' : 'min-w-[160px]'}`}>
              <div className={`flex-1 rounded-full bg-black/30 overflow-hidden ${isFullscreen ? 'h-3' : 'h-2'}`}>
                <motion.div
                  className="h-full rounded-full bg-[#D4AF37]"
                  initial={false}
                  animate={{ width: `${progress}%` }}
                  transition={{ type: 'spring', stiffness: 120, damping: 20 }}
                />
              </div>
              <span className="font-body text-sm text-[#f0dcae] tabular-nums">{Math.round(progress)}%</span>
            </div>
          )}

          <button
            type="button"
            onClick={toggleFullscreen}
            data-testid="board-fullscreen-toggle"
            title={isFullscreen ? 'Sair da tela cheia' : 'Exibir em tela cheia (TV ou projetor)'}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-black/35 hover:bg-black/50 border border-white/10 text-[#fff6dd] font-body text-sm transition-all"
          >
            {isFullscreen ? <Minimize2 className="w-5 h-5" /> : <Maximize2 className="w-5 h-5" />}
            <span className="hidden sm:inline">{isFullscreen ? 'Sair da tela cheia' : 'Tela cheia'}</span>
          </button>
        </div>
      </div>

      {todayHabits.length === 0 ? (
        <div className={`relative z-10 flex items-center justify-center ${isFullscreen ? 'flex-1' : 'py-16'}`}>
          <div
            className="relative max-w-sm w-full text-center px-8 py-10 shadow-[0_18px_35px_-15px_rgba(0,0,0,0.8)]"
            style={{ background: paperColor('#D4AF37'), color: inkColor('#D4AF37'), transform: 'rotate(-1.5deg)' }}
          >
            <span className="board-pin" style={{ '--pin-color': '#CD1C33' }} />
            <p className="font-heading text-2xl mb-2">Quadro vazio hoje</p>
            <p className="font-body text-sm opacity-80 mb-6">
              Nenhuma meta está programada para hoje. Crie um objetivo e ele aparecerá aqui no dia certo.
            </p>
            <button
              type="button"
              onClick={onCreateGoal}
              data-testid="board-create-goal"
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-full bg-primary text-white font-body font-medium hover:opacity-90 transition-opacity"
            >
              <Plus className="w-4 h-4" />
              Criar meta
            </button>
          </div>
        </div>
      ) : (
        <div
          className={`relative z-10 grid gap-6 sm:gap-8 ${isFullscreen ? 'flex-1 min-h-0 auto-rows-fr' : ''}`}
          style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}
          data-testid="board-notes"
        >
          <AnimatePresence initial={false}>
            {todayHabits.map((habit, index) => {
              const completed = isCompleted(habit.habit_id);
              const color = habit.color || '#CD1C33';

              return (
                <motion.button
                  key={habit.habit_id}
                  type="button"
                  layout
                  initial={{ opacity: 0, y: -20, rotate: tiltFor(habit.habit_id) }}
                  animate={{ opacity: 1, y: 0, rotate: tiltFor(habit.habit_id) }}
                  exit={{ opacity: 0, scale: 0.9 }}
                  transition={{ delay: index * 0.04, type: 'spring', stiffness: 140, damping: 18 }}
                  whileHover={{ scale: 1.03, rotate: 0 }}
                  whileTap={{ scale: 0.98 }}
                  onClick={() => handleToggle(habit.habit_id)}
                  disabled={pendingHabitId === habit.habit_id}
                  data-testid={`board-note-${habit.habit_id}`}
                  title={completed ? 'Clique para desmarcar' : 'Clique para marcar como concluída'}
                  className={`post-it relative flex flex-col justify-between text-left px-6 pt-10 pb-6 ${
                    isFullscreen ? 'h-full' : 'aspect-square'
                  } ${completed ? 'is-done' : ''} disabled:cursor-wait`}
                  style={{
                    background: `linear-gradient(160deg, ${paperColor(color)} 0%, ${paperShade(color)} 100%)`,
                    color: inkColor(color),
                  }}
                >
                  <span className="board-pin" style={{ '--pin-color': color }} />

                  <div className={`min-w-0 ${isFullscreen ? 'flex-1 flex flex-col justify-center' : ''}`}>
                    <p
                      className={`font-heading leading-tight break-words ${completed ? 'line-through opacity-60' : ''}`}
                      style={{ fontSize: isFullscreen ? 'clamp(1.5rem, 2.4vw, 3rem)' : 'clamp(1.15rem, 2.2vw, 1.75rem)' }}
                    >
                      {habit.name}
                    </p>
                    <p
                      className="font-body opacity-70 mt-2"
                      style={{ fontSize: isFullscreen ? 'clamp(0.85rem, 1.1vw, 1.25rem)' : '0.75rem' }}
                    >
                      {frequencyLabel(habit)}
                    </p>
                    <p
                      className="font-body opacity-55 mt-1"
                      style={{ fontSize: isFullscreen ? 'clamp(0.8rem, 1vw, 1.15rem)' : '0.7rem' }}
                    >
                      Prazo até {shortDate(habit.end_date)}
                    </p>
                  </div>

                  <div className="flex items-center gap-3">
                    <span
                      className="rounded-full flex items-center justify-center shrink-0 transition-all"
                      style={{
                        width: isFullscreen ? '3rem' : '2.25rem',
                        height: isFullscreen ? '3rem' : '2.25rem',
                        backgroundColor: completed ? color : 'transparent',
                        border: completed ? 'none' : `3px solid ${color}`,
                        boxShadow: completed ? `0 0 18px ${color}66` : 'none',
                      }}
                    >
                      {completed && <Check className="w-2/3 h-2/3 text-white" strokeWidth={3} />}
                    </span>
                    <span
                      className="font-body font-bold uppercase tracking-widest"
                      style={{ fontSize: isFullscreen ? 'clamp(0.75rem, 1vw, 1.05rem)' : '0.7rem' }}
                    >
                      {completed ? 'Concluída' : 'Marcar'}
                    </span>
                  </div>

                  {completed && (
                    <motion.span
                      initial={{ scale: 1.4, opacity: 0, rotate: -18 }}
                      animate={{ scale: 1, opacity: 1, rotate: -14 }}
                      transition={{ type: 'spring', stiffness: 200, damping: 12 }}
                      className="absolute bottom-5 right-5 px-4 py-1 border-4 rounded-xl font-heading font-bold uppercase tracking-[0.3em] pointer-events-none"
                      style={{
                        borderColor: `${color}`,
                        color,
                        opacity: 0.6,
                        fontSize: isFullscreen ? 'clamp(1.35rem, 2.2vw, 2.75rem)' : '1.35rem',
                      }}
                    >
                      Feito
                    </motion.span>
                  )}
                </motion.button>
              );
            })}
          </AnimatePresence>
        </div>
      )}
    </div>
  );
}
