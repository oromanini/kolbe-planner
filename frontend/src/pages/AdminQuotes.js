import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { toast } from "sonner";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const emptyForm = { mode: "neutral", text: "", author: "", tags: "", active: true };

export default function AdminQuotes() {
  const navigate = useNavigate();
  const [items, setItems] = useState([]);
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState("");
  const [active, setActive] = useState("");
  const [selected, setSelected] = useState({});
  const [form, setForm] = useState(emptyForm);
  const [editingId, setEditingId] = useState(null);
  const [jsonText, setJsonText] = useState("");
  const [report, setReport] = useState(null);

  const loadQuotes = async () => {
    const params = new URLSearchParams();
    if (query) params.set("q", query);
    if (mode) params.set("mode", mode);
    if (active) params.set("active", active);

    const res = await fetch(`${API}/admin/quotes?${params.toString()}`, { credentials: "include" });
    if (!res.ok) throw new Error("Falha ao carregar frases");
    const data = await res.json();
    setItems(data.items || []);
  };

  useEffect(() => {
    loadQuotes().catch(() => toast.error("Erro ao carregar frases"));
  }, []);

  const selectedIds = useMemo(() => Object.keys(selected).filter((id) => selected[id]), [selected]);

  const submitForm = async (e) => {
    e.preventDefault();
    const payload = {
      mode: form.mode,
      text: form.text,
      author: form.author || "Desconhecido",
      tags: form.tags.split(",").map((t) => t.trim()).filter(Boolean),
      active: form.active,
    };

    const endpoint = editingId ? `${API}/admin/quotes/${editingId}` : `${API}/admin/quotes`;
    const method = editingId ? "PUT" : "POST";
    const res = await fetch(endpoint, {
      method,
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      toast.error("Erro ao salvar frase");
      return;
    }

    toast.success(editingId ? "Frase atualizada" : "Frase criada");
    setForm(emptyForm);
    setEditingId(null);
    loadQuotes();
  };

  const onDeleteOne = async (id) => {
    if (!window.confirm("Confirma exclusão da frase?")) return;
    const res = await fetch(`${API}/admin/quotes/${id}`, { method: "DELETE", credentials: "include" });
    if (!res.ok) return toast.error("Erro ao excluir");
    toast.success("Frase excluída");
    loadQuotes();
  };

  const bulkDelete = async () => {
    if (!selectedIds.length) return;
    if (!window.confirm(`Excluir ${selectedIds.length} frases? Esta ação é irreversível.`)) return;
    const res = await fetch(`${API}/admin/quotes/bulk-delete`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ ids: selectedIds }),
    });
    const data = await res.json();
    toast.success(`${data.deleted?.length || 0} excluídas`);
    if (data.failed?.length) toast.error(`Falha em ${data.failed.length} IDs`);
    setSelected({});
    loadQuotes();
  };

  const importJson = async () => {
    let payload;
    try {
      payload = JSON.parse(jsonText);
    } catch {
      toast.error("JSON inválido");
      return;
    }
    const res = await fetch(`${API}/admin/quotes/import`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) return toast.error("Erro ao importar JSON");
    setReport(data);
    loadQuotes();
  };

  const onFileUpload = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    const text = await file.text();
    setJsonText(text);
  };

  return (
    <div className="min-h-screen bg-background text-white">
      <header className="border-b border-white/5 bg-background-paper/50 backdrop-blur-xl sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 py-4 flex items-center gap-4">
          <button onClick={() => navigate('/admin')} className="p-2.5 hover:bg-white/5 rounded-lg text-slate-400 hover:text-white"><ArrowLeft className="w-5 h-5" /></button>
          <div className="h-10 w-10 rounded-xl border border-white/10 p-1.5 bg-white/5 flex items-center justify-center overflow-hidden">
            <img src="/kp-logo.svg" alt="Kolbe Planner" className="h-full w-full object-contain" />
          </div>
          <h1 className="font-heading text-2xl">Admin &gt; Frases</h1>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 py-8 space-y-6">
        <div className="glass-card p-4 grid md:grid-cols-4 gap-3">
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Buscar texto/autor" className="bg-white/5 border border-white/10 rounded px-3 py-2" />
          <select value={mode} onChange={(e) => setMode(e.target.value)} className="bg-white/5 border border-white/10 rounded px-3 py-2"><option value="">Todos modos</option><option value="neutral">Neutral</option><option value="kolbe">Kolbe</option></select>
          <select value={active} onChange={(e) => setActive(e.target.value)} className="bg-white/5 border border-white/10 rounded px-3 py-2"><option value="">Ativas e inativas</option><option value="true">Ativas</option><option value="false">Inativas</option></select>
          <button onClick={() => loadQuotes()} className="bg-primary text-black rounded px-3 py-2">Filtrar</button>
        </div>

        {selectedIds.length > 0 && <button onClick={bulkDelete} className="bg-red-600 rounded px-3 py-2">Excluir selecionadas ({selectedIds.length})</button>}

        <div className="glass-card p-4 overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="text-left text-slate-400"><th><input type="checkbox" onChange={(e) => setSelected(Object.fromEntries(items.map((i) => [i.id, e.target.checked])))} /></th><th>Mode</th><th>Texto</th><th>Autor</th><th>Tags</th><th>Ativa</th><th>Ações</th></tr></thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id} className="border-t border-white/10">
                  <td><input type="checkbox" checked={Boolean(selected[item.id])} onChange={(e) => setSelected((prev) => ({ ...prev, [item.id]: e.target.checked }))} /></td>
                  <td>{item.mode}</td><td>{item.text}</td><td>{item.author}</td><td>{(item.tags || []).join(", ")}</td><td>{item.active ? "Sim" : "Não"}</td>
                  <td className="space-x-2"><button onClick={() => { setEditingId(item.id); setForm({ ...item, tags: (item.tags || []).join(",") }); }} className="underline">Editar</button><button onClick={() => onDeleteOne(item.id)} className="underline text-red-400">Excluir</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <form onSubmit={submitForm} className="glass-card p-4 space-y-3">
          <h2 className="font-heading text-xl">{editingId ? "Editar frase" : "Nova frase"}</h2>
          <div className="grid md:grid-cols-2 gap-3">
            <select value={form.mode} onChange={(e) => setForm((p) => ({ ...p, mode: e.target.value }))} className="bg-white/5 border border-white/10 rounded px-3 py-2"><option value="neutral">Neutral</option><option value="kolbe">Kolbe</option></select>
            <input value={form.author} onChange={(e) => setForm((p) => ({ ...p, author: e.target.value }))} placeholder="Autor" className="bg-white/5 border border-white/10 rounded px-3 py-2" />
          </div>
          <textarea value={form.text} onChange={(e) => setForm((p) => ({ ...p, text: e.target.value }))} placeholder="Texto" className="w-full bg-white/5 border border-white/10 rounded px-3 py-2" rows={2} />
          <input value={form.tags} onChange={(e) => setForm((p) => ({ ...p, tags: e.target.value }))} placeholder="tags separadas por vírgula" className="w-full bg-white/5 border border-white/10 rounded px-3 py-2" />
          <label className="flex items-center gap-2"><input type="checkbox" checked={form.active} onChange={(e) => setForm((p) => ({ ...p, active: e.target.checked }))} /> Ativa</label>
          <div className="space-x-2"><button type="submit" className="bg-primary text-black rounded px-3 py-2">Salvar</button><button type="button" onClick={() => { setForm(emptyForm); setEditingId(null); }} className="border border-white/20 rounded px-3 py-2">Cancelar</button></div>
        </form>

        <div className="glass-card p-4 space-y-3">
          <h2 className="font-heading text-xl">Importar JSON</h2>
          <input type="file" accept="application/json,.json" onChange={onFileUpload} />
          <textarea value={jsonText} onChange={(e) => setJsonText(e.target.value)} rows={8} className="w-full bg-white/5 border border-white/10 rounded px-3 py-2" placeholder='{"version":1,"items":[]}' />
          <button onClick={importJson} className="bg-primary text-black rounded px-3 py-2">Importar JSON</button>
          {report && <pre className="text-xs bg-black/30 p-3 rounded overflow-auto">{JSON.stringify(report, null, 2)}</pre>}
        </div>
      </main>
    </div>
  );
}
