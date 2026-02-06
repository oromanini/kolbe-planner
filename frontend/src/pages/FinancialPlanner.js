import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, Plus, TrendingUp, TrendingDown, PiggyBank, DollarSign, Trash2 } from "lucide-react";
import { PieChart, Pie, Cell, ResponsiveContainer, Legend, Tooltip } from 'recharts';
import { toast } from "sonner";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function FinancialPlanner() {
  const navigate = useNavigate();
  const [currentMonth, setCurrentMonth] = useState(new Date().toISOString().slice(0, 7));
  const [summary, setSummary] = useState(null);
  const [expenses, setExpenses] = useState([]);
  const [incomes, setIncomes] = useState([]);
  const [savings, setSavings] = useState([]);
  const [methods, setMethods] = useState([]);
  const [categories, setCategories] = useState([]);
  const [showExpenseForm, setShowExpenseForm] = useState(false);
  const [showIncomeForm, setShowIncomeForm] = useState(false);
  const [newExpense, setNewExpense] = useState({ name: "", amount: 0, method_id: "", category: "", subcategory: "" });
  const [newIncome, setNewIncome] = useState({ name: "", amount: 0 });

  useEffect(() => {
    loadData();
  }, [currentMonth]);

  const loadData = async () => {
    try {
      const [summaryRes, expensesRes, incomesRes, savingsRes, methodsRes, categoriesRes] = await Promise.all([
        fetch(`${API}/finance/summary?month=${currentMonth}`, { credentials: 'include' }),
        fetch(`${API}/finance/expenses?month=${currentMonth}`, { credentials: 'include' }),
        fetch(`${API}/finance/incomes?month=${currentMonth}`, { credentials: 'include' }),
        fetch(`${API}/finance/savings`, { credentials: 'include' }),
        fetch(`${API}/finance/methods`, { credentials: 'include' }),
        fetch(`${API}/finance/categories`, { credentials: 'include' })
      ]);
      
      setSummary(await summaryRes.json());
      setExpenses(await expensesRes.json());
      setIncomes(await incomesRes.json());
      setSavings(await savingsRes.json());
      setMethods(await methodsRes.json());
      setCategories(await categoriesRes.json());
    } catch (error) {
      console.error('Error loading data:', error);
    }
  };

  const handleAddExpense = async (e) => {
    e.preventDefault();
    try {
      await fetch(`${API}/finance/expenses`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ ...newExpense, month: currentMonth })
      });
      toast.success('Gasto adicionado');
      setShowExpenseForm(false);
      setNewExpense({ name: "", amount: 0, method_id: "", category: "", subcategory: "" });
      loadData();
    } catch (error) {
      toast.error('Erro ao adicionar gasto');
    }
  };

  const handleAddIncome = async (e) => {
    e.preventDefault();
    try {
      await fetch(`${API}/finance/incomes`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ ...newIncome, month: currentMonth })
      });
      toast.success('Entrada adicionada');
      setShowIncomeForm(false);
      setNewIncome({ name: "", amount: 0 });
      loadData();
    } catch (error) {
      toast.error('Erro ao adicionar entrada');
    }
  };

  const chartData = summary?.category_breakdown ? 
    Object.entries(summary.category_breakdown).map(([name, value]) => ({ name, value })) : [];
  
  const COLORS = ['#CD1C33', '#D4AF37', '#3B82F6', '#10B981', '#8B5CF6', '#F59E0B'];

  return (
    <div className="min-h-screen bg-background text-white">
      <header className="border-b border-white/5 bg-background-paper/50 backdrop-blur-xl sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button onClick={() => navigate('/hub')} className="p-2.5 hover:bg-white/5 rounded-lg transition-all text-slate-400 hover:text-white">
              <ArrowLeft className="w-5 h-5" />
            </button>
            <h1 className="font-heading text-2xl font-medium text-white">Planner Financeiro</h1>
          </div>
          <input type="month" value={currentMonth} onChange={(e) => setCurrentMonth(e.target.value)} 
            className="px-4 py-2 bg-slate-950/50 border border-white/10 rounded-lg text-white" />
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Summary Cards */}
        <div className="grid md:grid-cols-3 gap-6 mb-8">
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="glass-card p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-12 h-12 bg-primary/10 rounded-xl flex items-center justify-center">
                <TrendingUp className="w-6 h-6 text-primary" />
              </div>
              <span className="text-sm text-slate-400 uppercase tracking-wider">Entradas</span>
            </div>
            <p className="font-heading text-4xl font-medium text-white">
              R$ {summary?.total_income?.toFixed(2) || '0.00'}
            </p>
          </motion.div>

          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="glass-card p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-12 h-12 bg-secondary/10 rounded-xl flex items-center justify-center">
                <TrendingDown className="w-6 h-6 text-secondary" />
              </div>
              <span className="text-sm text-slate-400 uppercase tracking-wider">Saídas</span>
            </div>
            <p className="font-heading text-4xl font-medium text-white">
              R$ {summary?.total_expenses?.toFixed(2) || '0.00'}
            </p>
          </motion.div>

          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }} 
            className={`glass-card p-6 ${summary?.balance >= 0 ? 'border-primary/30' : 'border-secondary/30'}`}>
            <div className="flex items-center gap-3 mb-4">
              <div className={`w-12 h-12 rounded-xl flex items-center justify-center ${summary?.balance >= 0 ? 'bg-primary/10' : 'bg-secondary/10'}`}>
                <DollarSign className={`w-6 h-6 ${summary?.balance >= 0 ? 'text-primary' : 'text-secondary'}`} />
              </div>
              <span className="text-sm text-slate-400 uppercase tracking-wider">Saldo</span>
            </div>
            <p className={`font-heading text-4xl font-medium ${summary?.balance >= 0 ? 'text-primary' : 'text-secondary'}`}>
              R$ {summary?.balance?.toFixed(2) || '0.00'}
            </p>
          </motion.div>
        </div>

        <div className="grid lg:grid-cols-2 gap-8">
          {/* Expenses Section */}
          <div>
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-heading text-2xl font-medium text-white">Gastos</h2>
              <button onClick={() => setShowExpenseForm(!showExpenseForm)} 
                className="p-2 bg-primary/10 hover:bg-primary/20 rounded-lg transition-all">
                <Plus className="w-5 h-5 text-primary" />
              </button>
            </div>

            {showExpenseForm && (
              <form onSubmit={handleAddExpense} className="glass-card p-6 mb-6 space-y-4">
                <input placeholder="Nome" value={newExpense.name} onChange={(e) => setNewExpense({...newExpense, name: e.target.value})} 
                  className="w-full px-4 py-3 bg-slate-950/50 border border-white/10 rounded-lg text-white" required />
                <input type="number" placeholder="Valor" value={newExpense.amount} onChange={(e) => setNewExpense({...newExpense, amount: parseFloat(e.target.value)})} 
                  className="w-full px-4 py-3 bg-slate-950/50 border border-white/10 rounded-lg text-white" required />
                <input placeholder="Categoria" value={newExpense.category} onChange={(e) => setNewExpense({...newExpense, category: e.target.value})} 
                  className="w-full px-4 py-3 bg-slate-950/50 border border-white/10 rounded-lg text-white" required />
                <div className="flex gap-3">
                  <button type="submit" className="flex-1 bg-primary text-white px-6 py-3 rounded-full font-medium">Adicionar</button>
                  <button type="button" onClick={() => setShowExpenseForm(false)} className="px-6 py-3 border border-white/20 rounded-full">Cancelar</button>
                </div>
              </form>
            )}

            <div className="space-y-3">
              {expenses.map(exp => (
                <div key={exp.expense_id} className="glass-card p-4 flex items-center justify-between">
                  <div>
                    <p className="font-medium text-white">{exp.name}</p>
                    <p className="text-sm text-slate-400">{exp.category}</p>
                  </div>
                  <p className="font-heading text-xl text-white">R$ {exp.amount.toFixed(2)}</p>
                </div>
              ))}
            </div>
          </div>

          {/* Chart Section */}
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
    </div>
  );
}
