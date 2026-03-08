import { useEffect, useMemo, useRef, useState } from "react";
import { Bell } from "lucide-react";
import { toast } from "sonner";
import { apiRequest } from "@/lib/api";

const toneClasses = {
  info: "border-blue-400/30 bg-blue-500/10 text-blue-100",
  warning: "border-amber-400/30 bg-amber-500/10 text-amber-100",
  danger: "border-red-400/30 bg-red-500/10 text-red-100",
};

export default function NotificationBell() {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [items, setItems] = useState([]);
  const wrapperRef = useRef(null);

  const unreadCount = useMemo(() => items.length, [items.length]);

  const loadNotifications = async ({ refresh = false } = {}) => {
    try {
      setLoading(true);
      if (refresh) {
        await apiRequest(`/notifications/refresh`, { method: "POST" });
      }

      const response = await apiRequest(`/notifications?limit=20`);
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail || "Erro ao carregar notificações");
      }
      const data = await response.json();
      setItems(data);
    } catch (error) {
      toast.error(error.message || "Erro ao carregar notificações");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadNotifications({ refresh: true });
  }, []);

  useEffect(() => {
    const onOutsideClick = (event) => {
      if (wrapperRef.current && !wrapperRef.current.contains(event.target)) {
        setOpen(false);
      }
    };

    document.addEventListener("mousedown", onOutsideClick);
    return () => document.removeEventListener("mousedown", onOutsideClick);
  }, []);

  return (
    <div className="relative" ref={wrapperRef}>
      <button
        type="button"
        onClick={() => {
          setOpen((prev) => !prev);
          if (!open) {
            loadNotifications();
          }
        }}
        className="relative p-2.5 hover:bg-white/5 rounded-lg transition-all text-slate-300 hover:text-white"
        title="Notificações"
      >
        <Bell className="w-5 h-5" />
        {unreadCount > 0 && (
          <span className="absolute -top-1 -right-1 min-w-[1.1rem] h-[1.1rem] px-1 rounded-full bg-primary text-[10px] leading-[1.1rem] text-center text-white font-semibold">
            {unreadCount > 9 ? "9+" : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 mt-2 w-80 max-h-96 overflow-y-auto rounded-xl border border-white/10 bg-slate-950/95 shadow-2xl backdrop-blur-xl z-[70] p-3 space-y-2">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-semibold text-white">Notificações</h3>
            <button
              type="button"
              onClick={() => loadNotifications({ refresh: true })}
              className="text-xs text-primary hover:underline"
            >
              Atualizar
            </button>
          </div>

          {loading && <p className="text-xs text-slate-400">Carregando...</p>}

          {!loading && items.length === 0 && (
            <p className="text-xs text-slate-400">Sem alertas no momento.</p>
          )}

          {!loading && items.map((item) => (
            <div
              key={item.id}
              className={`p-2.5 rounded-lg border text-xs ${toneClasses[item.tone] || toneClasses.info}`}
            >
              {item.message}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
