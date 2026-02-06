import { useState, useEffect, useRef } from "react";
import { BrowserRouter, Routes, Route, useLocation, useNavigate } from "react-router-dom";
import "@/App.css";
import LandingPage from "./pages/LandingPage";
import Hub from "./pages/Hub";
import Dashboard from "./pages/Dashboard";
import HabitManager from "./pages/HabitManager";
import AdminDashboard from "./pages/AdminDashboard";
import FinancialPlanner from "./pages/FinancialPlanner";
import { Toaster } from "./components/ui/sonner";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

// AuthCallback Component
function AuthCallback() {
  const navigate = useNavigate();
  const location = useLocation();
  const hasProcessed = useRef(false);

  useEffect(() => {
    if (hasProcessed.current) return;
    hasProcessed.current = true;

    const processSessionId = async () => {
      const hash = location.hash;
      const params = new URLSearchParams(hash.substring(1));
      const sessionId = params.get('session_id');

      if (!sessionId) {
        navigate('/');
        return;
      }

      try {
        const response = await fetch(`${API}/auth/session`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ session_id: sessionId }),
          credentials: 'include'
        });

        if (!response.ok) throw new Error('Auth failed');

        const user = await response.json();
        
        // Navigate to dashboard with user data
        navigate('/dashboard', { 
          replace: true, 
          state: { user } 
        });
      } catch (error) {
        console.error('Auth error:', error);
        navigate('/');
      }
    };

    processSessionId();
  }, [location, navigate]);

  return (
    <div className="min-h-screen bg-paper flex items-center justify-center">
      <div className="text-center">
        <div className="w-16 h-16 border-4 border-navy border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
        <p className="text-navy font-body">Autenticando...</p>
      </div>
    </div>
  );
}

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
      <div className="min-h-screen bg-paper flex items-center justify-center">
        <div className="w-16 h-16 border-4 border-navy border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  return isAuthenticated ? children : null;
}

// AppRouter Component
function AppRouter() {
  const location = useLocation();
  
  // CRITICAL: Check session_id synchronously during render
  if (location.hash?.includes('session_id=')) {
    return <AuthCallback />;
  }

  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route 
        path="/dashboard" 
        element={
          <ProtectedRoute>
            <Dashboard />
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

function App() {
  return (
    <div className="App">
      <BrowserRouter>
        <AppRouter />
      </BrowserRouter>
      <Toaster />
    </div>
  );
}

export default App;
