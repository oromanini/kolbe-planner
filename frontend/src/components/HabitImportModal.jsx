import { useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Download, Upload, X, CheckCircle2, AlertTriangle } from "lucide-react";
import { toast } from "sonner";
import { authFetch } from "../lib/api";

export default function HabitImportModal({ open, onClose, onImported, apiBase }) {
  const [downloading, setDownloading] = useState(false);
  const [importing, setImporting] = useState(false);
  const [selectedFile, setSelectedFile] = useState(null);
  const [report, setReport] = useState(null);
  const fileInputRef = useRef(null);

  if (!open) return null;

  const resetAndClose = () => {
    setSelectedFile(null);
    setReport(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
    onClose();
  };

  const handleDownloadTemplate = async () => {
    try {
      setDownloading(true);
      const res = await authFetch(`${apiBase}/habits/import-template`, {
        credentials: "include",
      });
      if (!res.ok) throw new Error("Falha ao baixar modelo");

      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "modelo-metas.csv";
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.URL.revokeObjectURL(url);
    } catch (error) {
      console.error("Error downloading template:", error);
      toast.error("Erro ao baixar o modelo de CSV");
    } finally {
      setDownloading(false);
    }
  };

  const handleFileChange = (e) => {
    setSelectedFile(e.target.files?.[0] || null);
    setReport(null);
  };

  const handleImport = async () => {
    if (!selectedFile || importing) return;

    try {
      setImporting(true);
      const formData = new FormData();
      formData.append("file", selectedFile);

      const res = await authFetch(`${apiBase}/habits/import`, {
        method: "POST",
        credentials: "include",
        body: formData,
      });

      const result = await res.json();
      if (!res.ok) throw new Error(result.detail || "Falha ao importar CSV");

      setReport(result);
      if (result.criadas > 0) {
        toast.success(`${result.criadas} meta(s) importada(s) com sucesso!`);
        await onImported();
      } else {
        toast.error("Nenhuma meta foi importada. Confira os erros abaixo.");
      }
    } catch (error) {
      console.error("Error importing habits:", error);
      toast.error(error.message || "Erro ao importar CSV");
    } finally {
      setImporting(false);
    }
  };

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-[100] bg-black/70 backdrop-blur-sm flex items-center justify-center p-4"
        onClick={resetAndClose}
      >
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 0.95 }}
          onClick={(e) => e.stopPropagation()}
          className="glass-card w-full max-w-lg p-8 max-h-[85vh] overflow-y-auto"
        >
          <div className="flex items-center justify-between mb-6">
            <h3 className="font-heading text-2xl font-medium text-white flex items-center gap-2">
              <Upload className="w-6 h-6 text-primary" />
              Importar metas via CSV
            </h3>
            <button onClick={resetAndClose} className="p-2 hover:bg-white/5 rounded-lg text-slate-400 hover:text-white">
              <X className="w-5 h-5" />
            </button>
          </div>

          <div className="space-y-6">
            <div>
              <p className="text-sm text-slate-400 font-body mb-3">
                Baixe o modelo, preencha uma linha por meta (você pode pedir para uma IA gerar o
                CSV a partir da sua descrição) e envie o arquivo abaixo.
              </p>
              <button
                type="button"
                onClick={handleDownloadTemplate}
                disabled={downloading}
                data-testid="download-habit-import-template"
                className="w-full px-5 py-3 rounded-xl border border-white/10 text-slate-200 hover:bg-white/5 flex items-center justify-center gap-2 disabled:opacity-60"
              >
                <Download className="w-4 h-4" />
                {downloading ? "Baixando..." : "Baixar modelo CSV"}
              </button>
            </div>

            <div>
              <label className="block text-sm font-body font-medium text-slate-300 mb-3">
                Arquivo CSV
              </label>
              <input
                ref={fileInputRef}
                type="file"
                accept=".csv,text/csv"
                onChange={handleFileChange}
                data-testid="habit-import-file-input"
                className="w-full text-sm text-slate-300 file:mr-4 file:py-3 file:px-5 file:rounded-xl file:border-0 file:bg-primary/20 file:text-primary hover:file:bg-primary/30 file:cursor-pointer cursor-pointer bg-slate-950/50 border border-white/10 rounded-xl"
              />
            </div>

            {report && (
              <div className="space-y-3 border-t border-white/10 pt-4">
                <div className="flex items-center gap-2 text-emerald-400 text-sm font-body">
                  <CheckCircle2 className="w-4 h-4" />
                  {report.criadas} meta(s) criada(s)
                </div>
                {report.ignoradas_limite > 0 && (
                  <div className="flex items-center gap-2 text-amber-400 text-sm font-body">
                    <AlertTriangle className="w-4 h-4" />
                    {report.ignoradas_limite} linha(s) ignorada(s) por exceder o limite de 10 metas
                  </div>
                )}
                {report.invalidas.length > 0 && (
                  <div>
                    <p className="flex items-center gap-2 text-secondary text-sm font-body mb-2">
                      <AlertTriangle className="w-4 h-4" />
                      {report.invalidas.length} linha(s) inválida(s)
                    </p>
                    <ul className="space-y-1 max-h-40 overflow-y-auto text-xs text-slate-400 font-body">
                      {report.invalidas.map((item) => (
                        <li key={item.linha} className="px-3 py-2 bg-white/5 rounded-lg">
                          Linha {item.linha}{item.name ? ` (${item.name})` : ""}: {item.motivo}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}

            <div className="flex gap-3 pt-2">
              <button
                type="button"
                onClick={handleImport}
                disabled={!selectedFile || importing}
                data-testid="submit-habit-import"
                className="flex-1 bg-primary text-primary-foreground px-8 py-4 rounded-full font-body font-bold hover:bg-primary/90 transition-all shadow-lg shadow-primary/20 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {importing ? "Importando..." : "Importar"}
              </button>
              <button
                type="button"
                onClick={resetAndClose}
                className="px-8 py-4 border border-white/20 rounded-full font-body hover:bg-white/5 transition-all text-white"
              >
                Fechar
              </button>
            </div>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
