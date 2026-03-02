import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { useNavigate } from "react-router-dom";
import {
  ArrowLeft,
  Plus,
  TrendingUp,
  TrendingDown,
  DollarSign,
  Trash2,
  Pencil,
  Calendar,
  ShoppingBag,
  Car,
  Home,
  Utensils,
  HeartPulse,
  Briefcase,
  GraduationCap,
  Wallet,
  Shirt,
  Plane,
  Receipt,
  Landmark,
  Target,
} from "lucide-react";
import { PieChart, Pie, Cell, ResponsiveContainer, Legend, Tooltip } from "recharts";
import { toast } from "sonner";
import { apiRequest, checkApiHealth } from "@/lib/api";

const CATEGORY_ICONS = {
  shoppingBag: ShoppingBag,
  car: Car,
  home: Home,
  utensils: Utensils,
  heartPulse: HeartPulse,
  briefcase: Briefcase,
  graduationCap: GraduationCap,
  wallet: Wallet,
  shirt: Shirt,
  plane: Plane,
  receipt: Receipt,
  landmark: Landmark,
};

const CATEGORY_ICON_OPTIONS = [
  { value: "shoppingBag", label: "Compras" },
  { value: "car", label: "Transporte" },
  { value: "home", label: "Casa" },
  { value: "utensils", label: "Alimentação" },
  { value: "heartPulse", label: "Saúde" },
  { value: "briefcase", label: "Trabalho" },
  { value: "graduationCap", label: "Educação" },
  { value: "wallet", label: "Carteira" },
  { value: "shirt", label: "Vestuário" },
  { value: "plane", label: "Viagem" },
  { value: "receipt", label: "Contas" },
  { value: "landmark", label: "Impostos" },
];

const getCategoryIcon = (iconName) => CATEGORY_ICONS[iconName] || Receipt;

const formatCurrencyInput = (value) => {
  const digits = String(value || "").replace(/\D/g, "");
  const cents = Number(digits || 0) / 100;
  return cents.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
};

const parseCurrencyInput = (value) => {
  const normalized = String(value || "").replace(/\./g, "").replace(",", ".");
  const amount = Number(normalized);
  return Number.isFinite(amount) ? amount : 0;
};

const getErrorMessage = (error, fallback) => {
  if (error?.name === "TypeError") {
    return "Erro de conexão. Tente novamente em instantes.";
  }
  return error?.message || fallback;
};

export default function FinancialPlanner() {
  const navigate = useNavigate();
  const [currentMonth, setCurrentMonth] = useState(new Date().toISOString().slice(0, 7));
  const [summary, setSummary] = useState(null);
  const [expenses, setExpenses] = useState([]);
  const [incomes, setIncomes] = useState([]);
  const [savings, setSavings] = useState([]);
  const [methods, setMethods] = useState([]);
  const [categories, setCategories] = useState([]);
  const [isLoadingFinanceData, setIsLoadingFinanceData] = useState(true);
  const [isLoadingCategories, setIsLoadingCategories] = useState(true);
  const [isLoadingExpenses, setIsLoadingExpenses] = useState(true);
  const [showExpenseForm, setShowExpenseForm] = useState(false);
  const [showIncomeForm, setShowIncomeForm] = useState(false);
  const [showCategoryForm, setShowCategoryForm] = useState(false);
  const [isSubmittingExpense, setIsSubmittingExpense] = useState(false);
  const [isSubmittingCategory, setIsSubmittingCategory] = useState(false);
  const [expenseToDelete, setExpenseToDelete] = useState(null);
  const [expenseAmountInput, setExpenseAmountInput] = useState("0,00");
  const [categoryToDelete, setCategoryToDelete] = useState(null);
  const [newCategory, setNewCategory] = useState({ name: "", icon: "shoppingBag" });
  const [editingCategoryId, setEditingCategoryId] = useState(null);
  const [newExpense, setNewExpense] = useState({ name: "", amount: 0, method_id: "", category: "", subcategory: "" });
  const [editingExpenseId, setEditingExpenseId] = useState(null);
  const [newIncome, setNewIncome] = useState({ name: "", amount: 0 });

  useEffect(() => {
    loadData();
  }, [currentMonth]);

  const loadData = async () => {
    setIsLoadingFinanceData(true);
    setIsLoadingCategories(true);
    setIsLoadingExpenses(true);

    try {
      await checkApiHealth();
    } catch (error) {
      toast.error(getErrorMessage(error, "Serviço indisponível no momento"));
      setIsLoadingFinanceData(false);
      setIsLoadingCategories(false);
      setIsLoadingExpenses(false);
      return;
    }

    const loadCategories = apiRequest(`/finance/categories`)
      .then(async (response) => {
        if (!response.ok) {
          const errorPayload = await response.json().catch(() => null);
          throw new Error(errorPayload?.detail || "Erro ao carregar categorias");
        }
        return response.json();
      })
      .then((data) => setCategories(data))
      .catch((error) => {
        toast.error(getErrorMessage(error, "Erro ao carregar categorias"));
      })
      .finally(() => setIsLoadingCategories(false));

    const loadExpenses = apiRequest(`/finance/expenses?month=${currentMonth}`)
      .then(async (response) => {
        if (!response.ok) {
          const errorPayload = await response.json().catch(() => null);
          throw new Error(errorPayload?.detail || "Erro ao carregar gastos");
        }
        return response.json();
      })
      .then((data) => setExpenses(data))
      .catch((error) => {
        toast.error(getErrorMessage(error, "Erro ao carregar gastos"));
      })
      .finally(() => setIsLoadingExpenses(false));

    const loadFinanceOverview = Promise.all([
      apiRequest(`/finance/summary?month=${currentMonth}`),
      apiRequest(`/finance/incomes?month=${currentMonth}`),
      apiRequest(`/finance/savings`),
      apiRequest(`/finance/methods`),
    ])
      .then(async ([summaryRes, incomesRes, savingsRes, methodsRes]) => {
        const responses = [summaryRes, incomesRes, savingsRes, methodsRes];
        const labels = ["resumo", "entradas", "economias", "métodos de pagamento"];

        for (let i = 0; i < responses.length; i += 1) {
          if (!responses[i].ok) {
            const errorPayload = await responses[i].json().catch(() => null);
            throw new Error(errorPayload?.detail || `Erro ao carregar ${labels[i]}`);
          }
        }

        const [summaryData, incomesData, savingsData, methodsData] = await Promise.all(responses.map((res) => res.json()));
        setSummary(summaryData);
        setIncomes(incomesData);
        setSavings(savingsData);
        setMethods(methodsData);
      })
      .catch((error) => {
        toast.error(getErrorMessage(error, "Erro ao carregar dados financeiros"));
      });

    try {
      await Promise.all([loadCategories, loadExpenses, loadFinanceOverview]);
    } finally {
      setIsLoadingFinanceData(false);
    }
  };

  const handleSaveExpense = async (e) => {
    e.preventDefault();
    if (isSubmittingExpense) return;

    const isEditing = Boolean(editingExpenseId);

    setIsSubmittingExpense(true);
    try {
      const response = await apiRequest(
        isEditing ? `/finance/expenses/${editingExpenseId}` : `/finance/expenses`,
        {
          method: isEditing ? "PUT" : "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ...newExpense, month: currentMonth }),
        },
      );

      if (!response.ok) {
        const errorPayload = await response.json().catch(() => null);
        const message = errorPayload?.detail?.message || errorPayload?.detail || "Erro ao salvar gasto";
        throw new Error(message);
      }

      const savedExpense = await response.json();
      toast.success(isEditing ? "Gasto atualizado" : "Gasto adicionado");
      setShowExpenseForm(false);
      setEditingExpenseId(null);
      setNewExpense({ name: "", amount: 0, method_id: "", category: "", subcategory: "" });
      setExpenseAmountInput("0,00");
      if (isEditing) {
        setExpenses((prev) => prev.map((expense) => (
          expense.expense_id === editingExpenseId ? savedExpense : expense
        )));
      } else {
        setExpenses((prev) => [savedExpense, ...prev]);
      }
      loadData();
    } catch (error) {
      toast.error(getErrorMessage(error, "Erro ao salvar gasto"));
    } finally {
      setIsSubmittingExpense(false);
    }
  };

  const handleStartEditExpense = (expense) => {
    setShowExpenseForm(true);
    setEditingExpenseId(expense.expense_id);
    setNewExpense({
      name: expense.name,
      amount: expense.amount,
      method_id: expense.method_id,
      category: expense.category,
      subcategory: expense.subcategory || "",
    });
    setExpenseAmountInput(formatCurrencyInput(expense.amount));
  };

  const requestExpenseDelete = (expense) => {
    setExpenseToDelete(expense);
  };

  const confirmDeleteExpense = async () => {
    if (!expenseToDelete) return;

    try {
      const response = await apiRequest(`/finance/expenses/${expenseToDelete.expense_id}`, {
        method: "DELETE",
      });

      if (!response.ok) {
        throw new Error("Erro ao excluir gasto");
      }

      toast.success("Gasto excluído");
      if (editingExpenseId === expenseToDelete.expense_id) {
        setEditingExpenseId(null);
        setShowExpenseForm(false);
        setNewExpense({ name: "", amount: 0, method_id: "", category: "", subcategory: "" });
        setExpenseAmountInput("0,00");
      }
      setExpenseToDelete(null);
      loadData();
    } catch (error) {
      toast.error("Erro ao excluir gasto");
    }
  };

  const handleAddIncome = async (e) => {
    e.preventDefault();
    try {
      await apiRequest(`/finance/incomes`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...newIncome, month: currentMonth }),
      });
      toast.success("Entrada adicionada");
      setShowIncomeForm(false);
      setNewIncome({ name: "", amount: 0 });
      loadData();
    } catch (error) {
      toast.error("Erro ao adicionar entrada");
    }
  };

  const handleSaveCategory = async (e) => {
    e.preventDefault();
    if (isSubmittingCategory) return;

    if (!newCategory.name.trim()) {
      toast.error("Informe o nome da categoria");
      return;
    }

    const isEditing = Boolean(editingCategoryId);
    const endpoint = isEditing ? `/finance/categories/${editingCategoryId}` : `/finance/categories`;
    const method = isEditing ? "PUT" : "POST";

    setIsSubmittingCategory(true);
    try {
      const response = await apiRequest(endpoint, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...newCategory, name: newCategory.name.trim() }),
      });

      if (!response.ok) {
        const errorPayload = await response.json().catch(() => null);
        const message = errorPayload?.detail?.message || errorPayload?.detail || "Erro ao salvar categoria";
        throw new Error(message);
      }

      const savedCategory = await response.json();
      toast.success(isEditing ? "Categoria atualizada" : "Categoria criada");
      setShowCategoryForm(false);
      setEditingCategoryId(null);
      setNewCategory({ name: "", icon: "shoppingBag" });
      if (isEditing) {
        setCategories((prev) => prev.map((category) => (
          category.category_id === editingCategoryId ? savedCategory : category
        )));
      } else {
        setCategories((prev) => [...prev, savedCategory]);
      }
    } catch (error) {
      toast.error(error?.message || "Erro ao salvar categoria");
    } finally {
      setIsSubmittingCategory(false);
    }
  };

  const handleStartEditCategory = (category) => {
    setShowCategoryForm(true);
    setEditingCategoryId(category.category_id);
    setNewCategory({ name: category.name, icon: category.icon || "receipt" });
  };

  const requestCategoryDelete = async (category) => {
    try {
      const response = await apiRequest(`/finance/categories/${category.category_id}`, {
        method: "DELETE",
      });

      if (response.status === 409) {
        const payload = await response.json();
        setCategoryToDelete({ ...category, linkedItemsCount: payload?.detail?.linked_items_count || 0 });
        return;
      }

      if (!response.ok) {
        throw new Error("Erro ao excluir categoria");
      }

      toast.success("Categoria excluída");
      setCategories((prev) => prev.filter((item) => item.category_id !== category.category_id));
      loadData();
    } catch (error) {
      toast.error("Erro ao excluir categoria");
    }
  };

  const confirmDeleteCategory = async () => {
    if (!categoryToDelete) return;

    try {
      const response = await apiRequest(`/finance/categories/${categoryToDelete.category_id}?force=true`, {
        method: "DELETE",
      });

      if (!response.ok) {
        throw new Error("Erro ao excluir categoria");
      }

      toast.success("Categoria e itens associados excluídos");
      setCategories((prev) => prev.filter((item) => item.category_id !== categoryToDelete.category_id));
      setExpenses((prev) => prev.filter((expense) => expense.category !== categoryToDelete.name));
      setCategoryToDelete(null);
      loadData();
    } catch (error) {
      toast.error("Erro ao excluir categoria");
    }
  };

  const chartData = summary?.category_breakdown ? Object.entries(summary.category_breakdown).map(([name, value]) => ({ name, value })) : [];

  const COLORS = ["#CD1C33", "#D4AF37", "#3B82F6", "#10B981", "#8B5CF6", "#F59E0B"];

  return (
    <div className="min-h-screen bg-background text-white">
      <header className="border-b border-white/5 bg-background-paper/50 backdrop-blur-xl sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button onClick={() => navigate("/hub")} className="p-2.5 hover:bg-white/5 rounded-lg transition-all text-slate-400 hover:text-white">
              <ArrowLeft className="w-5 h-5" />
            </button>
            <div className="h-10 w-10 rounded-xl border border-white/10 p-1.5 bg-white/5 flex items-center justify-center overflow-hidden">
              <img src="/kp-logo.png" alt="Kolbe Planner" className="h-full w-full object-contain" />
            </div>
            <div>
              <h1 className="font-heading text-2xl font-medium text-white">Planner Financeiro</h1>
              <p className="text-xs text-slate-400">Kolbe Planner</p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <div className="hidden md:flex items-center gap-2 bg-white/5 border border-white/10 rounded-xl p-1">
              <button
                onClick={() => navigate('/dashboard')}
                className="px-3 py-2 rounded-lg text-slate-300 hover:text-white hover:bg-white/5 text-sm font-medium flex items-center gap-2 transition-all"
              >
                <Target className="w-4 h-4" />
                Planner de Metas
              </button>
              <button
                onClick={() => navigate('/finance')}
                className="px-3 py-2 rounded-lg bg-primary/20 text-primary text-sm font-medium flex items-center gap-2"
              >
                <Landmark className="w-4 h-4" />
                Planner Financeiro
              </button>
            </div>

            <div className="relative">
              <Calendar className="w-4 h-4 text-white absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
              <input
                type="month"
                value={currentMonth}
                onChange={(e) => setCurrentMonth(e.target.value)}
                className="calendar-white pl-10 px-4 py-2 bg-slate-950/50 border border-white/10 rounded-lg text-white"
              />
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {isLoadingFinanceData && (
          <div className="mb-6 glass-card p-4 border border-white/10 flex items-center gap-3">
            <motion.div
              animate={{ rotate: 360 }}
              transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
              className="w-5 h-5 border-2 border-primary/30 border-t-primary rounded-full"
            />
            <p className="text-sm text-slate-300">Carregando categorias e gastos...</p>
          </div>
        )}

        <div className="grid md:grid-cols-3 gap-6 mb-8">
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="glass-card p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-12 h-12 bg-primary/10 rounded-xl flex items-center justify-center">
                <TrendingUp className="w-6 h-6 text-primary" />
              </div>
              <span className="text-sm text-slate-400 uppercase tracking-wider">Entradas</span>
            </div>
            <p className="font-heading text-4xl font-medium text-white">R$ {summary?.total_income?.toFixed(2) || "0.00"}</p>
          </motion.div>

          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="glass-card p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-12 h-12 bg-secondary/10 rounded-xl flex items-center justify-center">
                <TrendingDown className="w-6 h-6 text-secondary" />
              </div>
              <span className="text-sm text-slate-400 uppercase tracking-wider">Saídas</span>
            </div>
            <p className="font-heading text-4xl font-medium text-white">R$ {summary?.total_expenses?.toFixed(2) || "0.00"}</p>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
            className={`glass-card p-6 ${summary?.balance >= 0 ? "border-primary/30" : "border-secondary/30"}`}
          >
            <div className="flex items-center gap-3 mb-4">
              <div className={`w-12 h-12 rounded-xl flex items-center justify-center ${summary?.balance >= 0 ? "bg-primary/10" : "bg-secondary/10"}`}>
                <DollarSign className={`w-6 h-6 ${summary?.balance >= 0 ? "text-primary" : "text-secondary"}`} />
              </div>
              <span className="text-sm text-slate-400 uppercase tracking-wider">Saldo</span>
            </div>
            <p className={`font-heading text-4xl font-medium ${summary?.balance >= 0 ? "text-primary" : "text-secondary"}`}>
              R$ {summary?.balance?.toFixed(2) || "0.00"}
            </p>
          </motion.div>
        </div>

        <div className="grid lg:grid-cols-3 gap-8">
          <div>
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-heading text-2xl font-medium text-white">Categorias</h2>
              <button
                onClick={() => {
                  setShowCategoryForm(!showCategoryForm);
                  setEditingCategoryId(null);
                  setNewCategory({ name: "", icon: "shoppingBag" });
                }}
                className="p-2 bg-primary/10 hover:bg-primary/20 rounded-lg transition-all"
              >
                <Plus className="w-5 h-5 text-primary" />
              </button>
            </div>

            {showCategoryForm && (
              <form onSubmit={handleSaveCategory} className="glass-card p-4 mb-4 space-y-3">
                <input
                  placeholder="Nome da categoria"
                  value={newCategory.name}
                  onChange={(e) => setNewCategory({ ...newCategory, name: e.target.value })}
                  className="w-full px-4 py-2 bg-slate-950/50 border border-white/10 rounded-lg text-white"
                  required
                />
                <select
                  value={newCategory.icon}
                  onChange={(e) => setNewCategory({ ...newCategory, icon: e.target.value })}
                  className="w-full px-4 py-2 bg-slate-950/50 border border-white/10 rounded-lg text-white"
                >
                  {CATEGORY_ICON_OPTIONS.map((iconOption) => (
                    <option key={iconOption.value} value={iconOption.value}>
                      {iconOption.label}
                    </option>
                  ))}
                </select>
                <div className="flex gap-2">
                  <button
                    type="submit"
                    disabled={isSubmittingCategory}
                    className="flex-1 bg-primary text-white px-4 py-2 rounded-full font-medium disabled:opacity-60 disabled:cursor-not-allowed"
                  >
                    {isSubmittingCategory ? "Salvando..." : editingCategoryId ? "Atualizar" : "Criar"}
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setShowCategoryForm(false);
                      setEditingCategoryId(null);
                      setNewCategory({ name: "", icon: "shoppingBag" });
                    }}
                    className="px-4 py-2 border border-white/20 rounded-full"
                  >
                    Cancelar
                  </button>
                </div>
              </form>
            )}

            <div className="space-y-3">
              {isLoadingCategories ? (
                <div className="glass-card p-4 flex items-center gap-3 text-slate-300">
                  <motion.div
                    animate={{ rotate: 360 }}
                    transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
                    className="w-4 h-4 border-2 border-primary/30 border-t-primary rounded-full"
                  />
                  <span>Carregando categorias...</span>
                </div>
              ) : categories.map((category) => {
                const Icon = getCategoryIcon(category.icon);
                return (
                  <div key={category.category_id} className="glass-card p-4 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <Icon className="w-4 h-4 text-primary" />
                      <p className="font-medium text-white">{category.name}</p>
                    </div>
                    <div className="flex items-center gap-2">
                      <button onClick={() => handleStartEditCategory(category)} className="p-1.5 rounded-md hover:bg-white/5">
                        <Pencil className="w-4 h-4 text-slate-300" />
                      </button>
                      <button onClick={() => requestCategoryDelete(category)} className="p-1.5 rounded-md hover:bg-secondary/20">
                        <Trash2 className="w-4 h-4 text-secondary" />
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-heading text-2xl font-medium text-white">Gastos</h2>
              <button
                onClick={() => {
                  if (!showExpenseForm) {
                    setEditingExpenseId(null);
                    setNewExpense({ name: "", amount: 0, method_id: "", category: "", subcategory: "" });
                    setExpenseAmountInput("0,00");
                  }
                  setShowExpenseForm(!showExpenseForm);
                }}
                className="p-2 bg-primary/10 hover:bg-primary/20 rounded-lg transition-all"
              >
                <Plus className="w-5 h-5 text-primary" />
              </button>
            </div>

            {showExpenseForm && (
              <form onSubmit={handleSaveExpense} className="glass-card p-6 mb-6 space-y-4">
                <input
                  placeholder="Nome"
                  value={newExpense.name}
                  onChange={(e) => setNewExpense({ ...newExpense, name: e.target.value })}
                  className="w-full px-4 py-3 bg-slate-950/50 border border-white/10 rounded-lg text-white"
                  required
                />
                <input
                  type="text"
                  inputMode="numeric"
                  placeholder="Valor"
                  value={expenseAmountInput}
                  onChange={(e) => {
                    const formatted = formatCurrencyInput(e.target.value);
                    setExpenseAmountInput(formatted);
                    setNewExpense({ ...newExpense, amount: parseCurrencyInput(formatted) });
                  }}
                  className="w-full px-4 py-3 bg-slate-950/50 border border-white/10 rounded-lg text-white"
                  required
                />
                <select
                  value={newExpense.method_id}
                  onChange={(e) => setNewExpense({ ...newExpense, method_id: e.target.value })}
                  className="w-full px-4 py-3 bg-slate-950/50 border border-white/10 rounded-lg text-white"
                  required
                >
                  <option value="">Selecione um método de pagamento</option>
                  {methods.map((method) => (
                    <option key={method.method_id} value={method.method_id}>
                      {method.name}
                    </option>
                  ))}
                </select>
                <select
                  value={newExpense.category}
                  onChange={(e) => setNewExpense({ ...newExpense, category: e.target.value })}
                  className="w-full px-4 py-3 bg-slate-950/50 border border-white/10 rounded-lg text-white"
                  required
                  disabled={!categories.length}
                >
                  <option value="">Selecione uma categoria</option>
                  {categories.map((category) => (
                    <option key={category.category_id} value={category.name}>
                      {category.name}
                    </option>
                  ))}
                </select>
                {!categories.length && (
                  <p className="text-sm text-amber-300">Cadastre uma categoria antes de adicionar gastos.</p>
                )}
                <div className="flex gap-3">
                  <button
                    type="submit"
                    disabled={isSubmittingExpense || !categories.length || !methods.length}
                    className="flex-1 bg-primary text-white px-6 py-3 rounded-full font-medium disabled:opacity-60 disabled:cursor-not-allowed"
                  >
                    {isSubmittingExpense ? "Salvando..." : editingExpenseId ? "Atualizar" : "Adicionar"}
                  </button>
                  <button
                    type="button"
                    disabled={isSubmittingExpense}
                    onClick={() => {
                      setShowExpenseForm(false);
                      setEditingExpenseId(null);
                      setNewExpense({ name: "", amount: 0, method_id: "", category: "", subcategory: "" });
                      setExpenseAmountInput("0,00");
                    }}
                    className="px-6 py-3 border border-white/20 rounded-full disabled:opacity-60 disabled:cursor-not-allowed"
                  >
                    Cancelar
                  </button>
                </div>
              </form>
            )}

            <div className="space-y-3">
              {isLoadingExpenses ? (
                <div className="glass-card p-4 flex items-center gap-3 text-slate-300">
                  <motion.div
                    animate={{ rotate: 360 }}
                    transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
                    className="w-4 h-4 border-2 border-primary/30 border-t-primary rounded-full"
                  />
                  <span>Carregando gastos...</span>
                </div>
              ) : expenses.map((exp) => {
                const category = categories.find((cat) => cat.name === exp.category);
                const Icon = getCategoryIcon(category?.icon);
                return (
                  <div key={exp.expense_id} className="glass-card p-4 flex items-center justify-between">
                    <div>
                      <p className="font-medium text-white">{exp.name}</p>
                      <p className="text-sm text-slate-400 flex items-center gap-2">
                        <Icon className="w-3.5 h-3.5" />
                        {exp.category}
                      </p>
                    </div>
                    <div className="flex items-center gap-3">
                      <p className="font-heading text-xl text-white">R$ {exp.amount.toFixed(2)}</p>
                      <button onClick={() => handleStartEditExpense(exp)} className="p-1.5 rounded-md hover:bg-white/5">
                        <Pencil className="w-4 h-4 text-slate-300" />
                      </button>
                      <button onClick={() => requestExpenseDelete(exp)} className="p-1.5 rounded-md hover:bg-secondary/20">
                        <Trash2 className="w-4 h-4 text-secondary" />
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="glass-card p-6">
            <h2 className="font-heading text-2xl font-medium text-white mb-6">Distribuição por Categoria</h2>
            {chartData.length > 0 ? (
              <ResponsiveContainer width="100%" height={300}>
                <PieChart>
                  <Pie data={chartData} cx="50%" cy="50%" outerRadius={100} fill="#8884d8" dataKey="value" label>
                    {chartData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <p className="text-slate-400 text-center py-12">Nenhum gasto cadastrado</p>
            )}
          </div>
        </div>
      </main>

      {expenseToDelete && (
        <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4">
          <div className="glass-card w-full max-w-lg p-6">
            <h3 className="text-xl font-heading mb-3">Excluir gasto</h3>
            <p className="text-slate-300 mb-6">
              Tem certeza que deseja excluir o gasto <span className="font-semibold text-white">{expenseToDelete.name}</span>?
            </p>
            <div className="flex justify-end gap-3">
              <button onClick={() => setExpenseToDelete(null)} className="px-5 py-2 border border-white/20 rounded-full">
                Cancelar
              </button>
              <button onClick={confirmDeleteExpense} className="px-5 py-2 rounded-full bg-secondary text-white">
                Excluir gasto
              </button>
            </div>
          </div>
        </div>
      )}

      {categoryToDelete && (
        <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4">
          <div className="glass-card w-full max-w-lg p-6">
            <h3 className="text-xl font-heading mb-3">Excluir categoria</h3>
            <p className="text-slate-300 mb-6">
              Todos os itens associados a essa categoria serão excluídos ({categoryToDelete.linkedItemsCount} itens). Deseja excluir mesmo assim ou editar os itens antes?
            </p>
            <div className="flex justify-end gap-3">
              <button onClick={() => setCategoryToDelete(null)} className="px-5 py-2 border border-white/20 rounded-full">
                Editar itens antes
              </button>
              <button onClick={confirmDeleteCategory} className="px-5 py-2 rounded-full bg-secondary text-white">
                Excluir categoria
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
