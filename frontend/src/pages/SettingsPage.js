import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { toast } from "sonner";
import { authFetch } from "../lib/api";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function SettingsPage() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [kolbeModeEnabled, setKolbeModeEnabled] = useState(false);

  useEffect(() => {
    const load = async () => {
      try {
        const res = await authFetch(`${API}/auth/me`, { credentials: "include" });
        const user = await res.json();
        const enabled = Boolean(user?.settings?.kolbe_mode_enabled);
        setKolbeModeEnabled(enabled);
        localStorage.setItem("kolbe_mode_enabled", enabled ? "1" : "0");
      } catch (error) {
        toast.error("Erro ao carregar configurações");
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  const updateToggle = async (nextValue) => {
    const previous = kolbeModeEnabled;
    setKolbeModeEnabled(nextValue);

    try {
      const res = await authFetch(`${API}/users/settings`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ kolbe_mode_enabled: nextValue }),
      });

      if (!res.ok) throw new Error("Falha ao salvar");
      localStorage.setItem("kolbe_mode_enabled", nextValue ? "1" : "0");
      window.dispatchEvent(new Event("kolbe-mode-changed"));
      toast.success("Preferência atualizada");
    } catch (error) {
      setKolbeModeEnabled(previous);
      toast.error("Não foi possível atualizar. Tente novamente.");
    }
  };

  if (loading) return <div className="min-h-screen bg-background" />;

  return (
    <div className="min-h-screen bg-background text-white">
      <header className="border-b border-white/5 bg-background-paper/50 backdrop-blur-xl sticky top-0 z-50">
        <div className="max-w-4xl mx-auto px-4 py-4 flex items-center gap-4">
          <button onClick={() => navigate('/dashboard')} className="p-2.5 hover:bg-white/5 rounded-lg text-slate-400 hover:text-white">
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div className="h-10 w-10 rounded-xl border border-white/10 p-1.5 bg-white/5 flex items-center justify-center overflow-hidden">
            <img src="/kp-logo.png" alt="Kolbe Planner" className="h-full w-full object-contain" />
          </div>
          <h1 className="font-heading text-2xl">Configurações</h1>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 py-8">
        <div className="glass-card p-6">
          <p className="text-sm uppercase tracking-widest text-slate-400 mb-4">Experiência</p>
          <div className="flex items-start justify-between gap-6">
            <div>
              <h2 className="font-heading text-xl">Modo Kolbe</h2>
              <p className="text-slate-400 mt-2 max-w-xl">
                Ative frases bíblicas e de santos sobre disciplina, e um tom mais contemplativo no app.
              </p>
            </div>
            <button
              onClick={() => updateToggle(!kolbeModeEnabled)}
              className={`w-16 h-9 rounded-full p-1 transition ${kolbeModeEnabled ? "bg-primary" : "bg-white/20"}`}
            >
              <span className={`block h-7 w-7 rounded-full bg-white transition ${kolbeModeEnabled ? "translate-x-7" : "translate-x-0"}`} />
            </button>
          </div>
        </div>

        <div className="glass-card p-6 mt-6">
          <h2 className="font-heading text-xl mb-2">Atalhos</h2>
          <button onClick={() => navigate('/habits')} className="px-4 py-2 rounded-lg bg-white/10 hover:bg-white/20">Gerenciar Hábitos</button>
        </div>
      </main>
    </div>
  );
}
