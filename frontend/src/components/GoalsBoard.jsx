import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Check, Maximize2, Minimize2, Plus } from "lucide-react";

const WEEKDAY_LABELS = ["Seg", "Ter", "Qua", "Qui", "Sex"];

// "205 28 51" — space separated so it can feed rgb(var(--goal-rgb) / <alpha>).
const rgbChannels = (hex) => {
  const normalized = (hex || "#CD1C33").replace('#', '');
  const full = normalized.length === 3
    ? normalized.split('').map((char) => char + char).join('')
    : normalized;
  const r = parseInt(full.slice(0, 2), 16) || 0;
  const g = parseInt(full.slice(2, 4), 16) || 0;
  const b = parseInt(full.slice(4, 6), 16) || 0;
  return `${r} ${g} ${b}`;
};

// Deterministic tilt so a card keeps the same angle between renders — just
// enough to read as pinned to the board rather than laid out by a grid.
const tiltFor = (id) => {
  const seed = String(id)
    .split('')
    .reduce((acc, char) => acc + char.charCodeAt(0), 0);
  return ((seed % 5) - 2) * 0.35;
};

const frequencyLabel = (habit) => {
  if (habit.frequency === "custom") {
    const days = (habit.selected_weekdays || [])
      .filter((value) => value >= 0 && value < WEEKDAY_LABELS.length)
      .map((value) => WEEKDAY_LABELS[value]);
    return days.length ? days.join(' · ') : 'Dias úteis';
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
  const [viewportWidth, setViewportWidth] = useState(() => (
    typeof window === 'undefined' ? 1280 : window.innerWidth
  ));

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
    const handleResize = () => setViewportWidth(window.innerWidth);
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

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

  // Cards want to be big on a TV and single-column on a phone, so the count
  // sets the ideal number of columns and the viewport caps it.
  const columns = useMemo(() => {
    const total = todayHabits.length;
    const byCount = isFullscreen
      ? (total <= 2 ? total : total <= 6 ? 3 : 4)
      : (total <= 2 ? total : 3);
    const byWidth = viewportWidth < 640
      ? 1
      : viewportWidth < 1024
        ? 2
        : viewportWidth < 1440
          ? 3
          : 4;
    return Math.max(1, Math.min(byCount, byWidth));
  }, [todayHabits.length, isFullscreen, viewportWidth]);

  return (
    <div
      ref={boardRef}
      data-testid="goals-board"
      className={`goal-board overflow-hidden ${
        isExpanded ? 'fixed inset-0 z-[100]' : 'relative'
      } ${
        isFullscreen
          ? 'h-screen w-screen flex flex-col p-5 sm:p-10'
          : 'rounded-3xl p-4 sm:p-8'
      }`}
    >
      <div className="relative z-10 flex flex-wrap items-end justify-between gap-4 mb-6 sm:mb-8">
        <div className="min-w-0">
          <p className="goal-board__eyebrow">Painel do dia</p>
          <p
            className="font-heading text-white leading-none mt-1.5"
            style={{ fontSize: isFullscreen ? 'clamp(1.6rem, 3vw, 3.25rem)' : 'clamp(1.35rem, 4vw, 1.75rem)' }}
            data-testid="board-date"
          >
            {todayLabel}
          </p>
        </div>

        <div className="flex items-center gap-3 sm:gap-4 ml-auto">
          {todayHabits.length > 0 && (
            <div className="flex items-center gap-3">
              <div className="text-right leading-none">
                <span
                  className="font-heading text-white tabular-nums"
                  style={{ fontSize: isFullscreen ? 'clamp(1.4rem, 2.2vw, 2.5rem)' : '1.35rem' }}
                >
                  {completedCount}
                  <span className="text-slate-500">/{todayHabits.length}</span>
                </span>
                <p className="goal-board__eyebrow mt-1.5">concluídas</p>
              </div>
              <div className={`goal-board__meter ${isFullscreen ? 'w-40 sm:w-56' : 'w-20 sm:w-32'}`}>
                <motion.span
                  initial={false}
                  animate={{ width: `${progress}%` }}
                  transition={{ type: 'spring', stiffness: 120, damping: 20 }}
                />
              </div>
            </div>
          )}

          <button
            type="button"
            onClick={toggleFullscreen}
            data-testid="board-fullscreen-toggle"
            title={isFullscreen ? 'Sair da tela cheia' : 'Exibir em tela cheia (TV ou projetor)'}
            className="goal-board__action"
          >
            {isFullscreen ? <Minimize2 className="w-5 h-5" /> : <Maximize2 className="w-5 h-5" />}
            <span className="hidden sm:inline">{isFullscreen ? 'Sair' : 'Tela cheia'}</span>
          </button>
        </div>
      </div>

      {todayHabits.length === 0 ? (
        <div className={`relative z-10 flex items-center justify-center ${isFullscreen ? 'flex-1' : 'py-14'}`}>
          <div className="goal-note goal-note--empty max-w-sm w-full text-center px-8 py-10" style={{ '--goal-rgb': rgbChannels('#D4AF37') }}>
            <span className="goal-note__led" />
            <p className="font-heading text-2xl text-white mb-2">Nada programado para hoje</p>
            <p className="font-body text-sm text-slate-400 mb-6">
              O painel mostra só as metas de hoje. Crie um objetivo e ele aparece aqui no dia certo.
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
          className={`relative z-10 grid gap-4 sm:gap-6 ${isFullscreen ? 'flex-1 min-h-0 auto-rows-fr' : ''}`}
          style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}
          data-testid="board-notes"
        >
          <AnimatePresence initial={false}>
            {todayHabits.map((habit, index) => {
              const completed = isCompleted(habit.habit_id);
              const channels = rgbChannels(habit.color);

              return (
                <motion.button
                  key={habit.habit_id}
                  type="button"
                  layout
                  initial={{ opacity: 0, y: -16, rotate: tiltFor(habit.habit_id) }}
                  animate={{ opacity: 1, y: 0, rotate: tiltFor(habit.habit_id) }}
                  exit={{ opacity: 0, scale: 0.95 }}
                  transition={{ delay: index * 0.04, type: 'spring', stiffness: 150, damping: 20 }}
                  whileHover={{ y: -4, rotate: 0 }}
                  whileTap={{ scale: 0.985 }}
                  onClick={() => handleToggle(habit.habit_id)}
                  disabled={pendingHabitId === habit.habit_id}
                  data-testid={`board-note-${habit.habit_id}`}
                  title={completed ? 'Clique para desmarcar' : 'Clique para marcar como concluída'}
                  className={`goal-note flex flex-col gap-4 text-left px-5 pt-8 pb-5 sm:px-6 sm:pb-6 ${
                    isFullscreen ? 'h-full' : 'min-h-[170px] sm:min-h-[200px]'
                  } ${completed ? 'is-done' : ''} disabled:cursor-wait`}
                  style={{ '--goal-rgb': channels }}
                >
                  <span className="goal-note__led" />

                  <div className={`min-w-0 ${isFullscreen ? 'flex-1 flex flex-col justify-center' : ''}`}>
                    <p
                      className="font-heading text-white leading-tight break-words text-balance"
                      style={{
                        fontSize: isFullscreen ? 'clamp(1.35rem, 2.2vw, 2.75rem)' : 'clamp(1.05rem, 3.2vw, 1.5rem)',
                        textDecoration: completed ? 'line-through' : 'none',
                        textDecorationColor: `rgb(${channels} / 0.7)`,
                        opacity: completed ? 0.65 : 1,
                      }}
                    >
                      {habit.name}
                    </p>
                    <p
                      className="goal-note__meta mt-2"
                      style={{ fontSize: isFullscreen ? 'clamp(0.7rem, 0.9vw, 1rem)' : '0.6875rem' }}
                    >
                      {frequencyLabel(habit)} <span className="opacity-40">|</span> até {shortDate(habit.end_date)}
                    </p>
                  </div>

                  <div className="mt-auto flex items-center gap-3">
                    <span className={`goal-note__check ${completed ? 'is-on' : ''}`}>
                      {completed && <Check className="w-2/3 h-2/3" strokeWidth={3} />}
                    </span>
                    <span className="goal-note__status">
                      {completed ? 'Concluída' : 'Marcar'}
                    </span>
                  </div>
                </motion.button>
              );
            })}
          </AnimatePresence>
        </div>
      )}
    </div>
  );
}
