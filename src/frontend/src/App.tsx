import React, { Suspense, lazy, useEffect, useState } from 'react';
import { createBrowserRouter, RouterProvider, Route, createRoutesFromElements, Navigate, useParams, Outlet } from 'react-router-dom';
import { Layout } from './components/Layout';
import { ErrorBoundary } from './components/ErrorBoundary';
import { Login } from './pages/Login';
import { useAuthStore } from './store/authStore';
import { useBoardStore } from './store/boardStore';
import { useLearningStore } from './store/learningStore';
import { ToastContainer } from './components/ui/ToastContainer';
import { SettingsManager } from './components/SettingsManager';

// Expose stores for E2E testing
if (import.meta.env.DEV) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (window as any).useAuthStore = useAuthStore;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (window as any).useBoardStore = useBoardStore;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (window as any).useLearningStore = useLearningStore;
}

const Dashboard = lazy(() => import('./pages/Dashboard').then(m => ({ default: m.Dashboard })));
const Communication = lazy(() => import('./pages/Communication').then(m => ({ default: m.Communication })));
const Boards = lazy(() => import('./pages/Boards').then(m => ({ default: m.Boards })));
const BoardEditor = lazy(() => import('./pages/BoardEditor').then(m => ({ default: m.BoardEditor })));
const Learning = lazy(() => import('./pages/Learning').then(m => ({ default: m.Learning })));
const Settings = lazy(() => import('./pages/Settings').then(m => ({ default: m.Settings })));
const Achievements = lazy(() => import('./pages/Achievements').then(m => ({ default: m.Achievements })));
const Students = lazy(() => import('./pages/Students').then(m => ({ default: m.Students })));
const Teachers = lazy(() => import('./pages/Teachers').then(m => ({ default: m.Teachers })));
const Admins = lazy(() => import('./pages/Admins').then(m => ({ default: m.Admins })));
const Register = lazy(() => import('./pages/Register').then(m => ({ default: m.Register })));
const Symbols = lazy(() => import('./pages/Symbols').then(m => ({ default: m.Symbols })));
const SymbolHunt = lazy(() => import('./pages/SymbolHunt').then(m => ({ default: m.SymbolHunt })));
const NotFound = lazy(() => import('./pages/NotFound').then(m => ({ default: m.NotFound })));

function LoadingSpinner() {
  return (
    <div className="flex items-center justify-center min-h-screen">
      <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600"></div>
    </div>
  );
}

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, sessionExpiresAt, logout } = useAuthStore();
  const [isExpired, setIsExpired] = useState(false);

  useEffect(() => {
    if (!sessionExpiresAt) return;

    const checkExpiration = () => {
      if (Date.now() > sessionExpiresAt) {
        setIsExpired(true);
        logout();
      }
    };

    checkExpiration();
    const interval = setInterval(checkExpiration, 60000);
    return () => clearInterval(interval);
  }, [sessionExpiresAt, logout]);

  if (!isAuthenticated || isExpired) return <Navigate to="/login" />;
  return <>{children}</>;
}

function PlayRedirect() {
  const { id } = useParams();
  const boardId = Number(id);
  const to = Number.isFinite(boardId) ? `/communication?boardId=${boardId}` : '/communication';
  return <Navigate to={to} replace />;
}

function RootLayout() {
  return (
    <>
      <SettingsManager />
      <ToastContainer />
      <Outlet />
    </>
  );
}

const router = createBrowserRouter(
  createRoutesFromElements(
    <Route element={<RootLayout />}>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Suspense fallback={<LoadingSpinner />}><Register /></Suspense>} />
      <Route
        path="/play/:id"
        element={
          <ProtectedRoute>
            <PlayRedirect />
          </ProtectedRoute>
        }
      />
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route index element={<ErrorBoundary><Suspense fallback={<LoadingSpinner />}><Dashboard /></Suspense></ErrorBoundary>} />
        <Route path="communication" element={<ErrorBoundary><Suspense fallback={<LoadingSpinner />}><Communication /></Suspense></ErrorBoundary>} />
        <Route path="boards" element={<ErrorBoundary><Suspense fallback={<LoadingSpinner />}><Boards /></Suspense></ErrorBoundary>} />
        <Route path="boards/:id" element={<ErrorBoundary><Suspense fallback={<LoadingSpinner />}><BoardEditor /></Suspense></ErrorBoundary>} />
        <Route path="learning" element={<ErrorBoundary><Suspense fallback={<LoadingSpinner />}><Learning /></Suspense></ErrorBoundary>} />
        <Route path="symbol-hunt" element={<ErrorBoundary><Suspense fallback={<LoadingSpinner />}><SymbolHunt /></Suspense></ErrorBoundary>} />
        <Route path="symbols" element={<ErrorBoundary><Suspense fallback={<LoadingSpinner />}><Symbols /></Suspense></ErrorBoundary>} />
        <Route path="settings" element={<ErrorBoundary><Suspense fallback={<LoadingSpinner />}><Settings /></Suspense></ErrorBoundary>} />
        <Route path="achievements" element={<ErrorBoundary><Suspense fallback={<LoadingSpinner />}><Achievements /></Suspense></ErrorBoundary>} />
        <Route path="students" element={<ErrorBoundary><Suspense fallback={<LoadingSpinner />}><Students /></Suspense></ErrorBoundary>} />
        <Route path="teachers" element={<ErrorBoundary><Suspense fallback={<LoadingSpinner />}><Teachers /></Suspense></ErrorBoundary>} />
        <Route path="admins" element={<ErrorBoundary><Suspense fallback={<LoadingSpinner />}><Admins /></Suspense></ErrorBoundary>} />
      </Route>
      <Route path="*" element={<Suspense fallback={<LoadingSpinner />}><NotFound /></Suspense>} />
    </Route>
  )
);

function App() {
  return <RouterProvider router={router} />;
}

export default App;
