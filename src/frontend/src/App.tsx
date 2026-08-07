import React, { Suspense, useEffect, useRef, useState } from 'react';
import { RouterProvider } from 'react-router/dom';
import { createBrowserRouter, Route, createRoutesFromElements, Navigate, useParams, Outlet } from 'react-router';
import { Layout } from './components/Layout';
import { ErrorBoundary } from './components/ErrorBoundary';
import { Login } from './pages/Login';
import { useAuthStore } from './store/authStore';
import { useBoardStore } from './store/boardStore';
import { useLearningStore } from './store/learningStore';
import { ToastContainer } from './components/ui/ToastContainer';
import { SettingsManager } from './components/SettingsManager';
import { lazyWithRetry } from './lib/lazyWithRetry';
import { LoadingState } from './components/ui/LoadingState';

// Expose stores for local E2E testing only. Production builds require the
// explicit VITE_ENABLE_E2E_HOOKS flag; normal production builds expose nothing.
if (import.meta.env.DEV || import.meta.env.VITE_ENABLE_E2E_HOOKS === 'true') {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (window as any).useAuthStore = useAuthStore;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (window as any).useBoardStore = useBoardStore;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (window as any).useLearningStore = useLearningStore;
}

const Dashboard = lazyWithRetry(() => import('./pages/Dashboard').then(m => ({ default: m.Dashboard })), 'dashboard');
const Communication = lazyWithRetry(() => import('./pages/Communication').then(m => ({ default: m.Communication })), 'communication');
const Boards = lazyWithRetry(() => import('./pages/Boards').then(m => ({ default: m.Boards })), 'boards');
const BoardEditor = lazyWithRetry(() => import('./pages/BoardEditor').then(m => ({ default: m.BoardEditor })), 'board-editor');
const Learning = lazyWithRetry(() => import('./pages/Learning').then(m => ({ default: m.Learning })), 'learning');
const Settings = lazyWithRetry(() => import('./pages/Settings').then(m => ({ default: m.Settings })), 'settings');
const Achievements = lazyWithRetry(() => import('./pages/Achievements').then(m => ({ default: m.Achievements })), 'achievements');
const Students = lazyWithRetry(() => import('./pages/Students').then(m => ({ default: m.Students })), 'students');
const UserManagementPage = lazyWithRetry(() => import('./pages/UserManagement').then(m => ({ default: m.UserManagementPage })), 'user-management');
const Register = lazyWithRetry(() => import('./pages/Register').then(m => ({ default: m.Register })), 'register');
const Symbols = lazyWithRetry(() => import('./pages/Symbols').then(m => ({ default: m.Symbols })), 'symbols');
const SymbolHunt = lazyWithRetry(() => import('./pages/SymbolHunt').then(m => ({ default: m.SymbolHunt })), 'symbol-hunt');
const NotFound = lazyWithRetry(() => import('./pages/NotFound').then(m => ({ default: m.NotFound })), 'not-found');

function LoadingSpinner() {
  return <LoadingState size="lg" fullHeight />;
}

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const sessionExpiresAt = useAuthStore((state) => state.sessionExpiresAt);
  const logout = useAuthStore((state) => state.logout);
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
        <Route path="teachers" element={<ErrorBoundary><Suspense fallback={<LoadingSpinner />}><UserManagementPage role="teacher" /></Suspense></ErrorBoundary>} />
        <Route path="admins" element={<ErrorBoundary><Suspense fallback={<LoadingSpinner />}><UserManagementPage role="admin" /></Suspense></ErrorBoundary>} />
      </Route>
      <Route path="*" element={<Suspense fallback={<LoadingSpinner />}><NotFound /></Suspense>} />
    </Route>
  )
);

function App() {
  const checkAuth = useAuthStore((state) => state.checkAuth);
  const authCheckStarted = useRef(false);
  const [authReady, setAuthReady] = useState(
    () => typeof navigator === 'undefined' || !navigator.onLine,
  );

  useEffect(() => {
    if (authCheckStarted.current) return;
    authCheckStarted.current = true;

    // Keep the persisted session available while the app is offline. The
    // auth store deliberately preserves it on offline refresh failures.
    if (typeof navigator !== 'undefined' && !navigator.onLine) return;

    void checkAuth().then(
      () => setAuthReady(true),
      () => setAuthReady(true),
    );
  }, [checkAuth]);

  if (!authReady) return <LoadingSpinner />;
  return <RouterProvider router={router} />;
}

export default App;
