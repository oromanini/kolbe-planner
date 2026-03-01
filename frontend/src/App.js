import { useState, useEffect } from "react";
import { BrowserRouter, Routes, Route, useLocation, useNavigate } from "react-router-dom";
import "@/App.css";
import LandingPage from "./pages/LandingPage";
import Hub from "./pages/Hub";
import Dashboard from "./pages/Dashboard";
import HabitManager from "./pages/HabitManager";
import AdminDashboard from "./pages/AdminDashboard";
import FinancialPlanner from "./pages/FinancialPlanner";
import SettingsPage from "./pages/SettingsPage";
import AdminQuotes from "./pages/AdminQuotes";
import { Toaster } from "./components/ui/sonner";
import PlannerTipsAssistant from "./components/PlannerTipsAssistant";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

// ProtectedRoute Component
function ProtectedRoute({ children }) {
  const [isAuthenticated, setIsAuthenticated] = useState(
    useLocation().state?.user ? true : null
  );
  const [user, setUser] = useState(useLocation().state?.user || null);
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    // Skip auth check if user data was passed from AuthCallback
    if (location.state?.user) return;

    const checkAuth = async () => {
      try {
        const response = await fetch(`${API}/auth/me`, {
          credentials: 'include'
        });
        
        if (!response.ok) throw new Error('Not authenticated');
        
        const userData = await response.json();
        setUser(userData);
        setIsAuthenticated(true);
      } catch (error) {
        setIsAuthenticated(false);
        navigate('/');
      }
    };

    checkAuth();
  }, [navigate, location.state]);

  if (isAuthenticated === null) {
    return (
      <div className="min-h-screen bg-paper flex flex-col items-center justify-center gap-4 px-6 text-center">
        <div className="w-16 h-16 border-4 border-navy border-t-transparent rounded-full animate-spin"></div>
        <p className="text-slate-300 font-body max-w-md">Conferindo seu acesso e preparando a próxima tela...</p>
      </div>
    );
  }

  return isAuthenticated ? children : null;
}

// AppRouter Component
function AppRouter() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route 
        path="/hub" 
        element={
          <ProtectedRoute>
            <Hub />
          </ProtectedRoute>
        } 
      />
      <Route 
        path="/dashboard" 
        element={
          <ProtectedRoute>
            <Dashboard />
          </ProtectedRoute>
        } 
      />
      <Route 
        path="/finance" 
        element={
          <ProtectedRoute>
            <FinancialPlanner />
          </ProtectedRoute>
        } 
      />
      <Route 
        path="/habits" 
        element={
          <ProtectedRoute>
            <HabitManager />
          </ProtectedRoute>
        } 
      />
      <Route 
        path="/settings" 
        element={
          <ProtectedRoute>
            <SettingsPage />
          </ProtectedRoute>
        } 
      />
      <Route 
        path="/admin/quotes" 
        element={
          <ProtectedRoute>
            <AdminQuotes />
          </ProtectedRoute>
        } 
      />
      <Route 
        path="/admin" 
        element={
          <ProtectedRoute>
            <AdminDashboard />
          </ProtectedRoute>
        } 
      />
    </Routes>
  );
}

function AppShell() {
  return (
    <>
      <AppRouter />
      <PlannerTipsAssistant />
      <Toaster />
    </>
  );
}

function App() {
  return (
    <div className="App">
      <BrowserRouter>
        <AppShell />
      </BrowserRouter>
    </div>
  );
}

export default App;
