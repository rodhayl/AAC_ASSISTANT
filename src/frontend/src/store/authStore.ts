import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import api, { extractError } from '../lib/api';
import { registerAuthStateReader } from '../lib/authState';
import { isOfflineError } from '../lib/httpErrors';
import type { AuthSetupData, RegistrationData, User } from '../types';
import { useLocaleStore } from './localeStore';
import { useThemeStore } from './themeStore';
import i18n from '../i18n/index';

interface AuthState {
  user: User | null;
  token: string | null;
  refreshToken: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;
  sessionExpiresAt: number | null;
  
  login: (username: string, password: string) => Promise<void>;
  setupAdmin: (setupData: AuthSetupData) => Promise<void>;
  register: (userData: RegistrationData) => Promise<void>;
  logout: () => Promise<void>;
  checkAuth: () => Promise<void>;
  refreshAccessToken: () => Promise<boolean>;
}

interface JwtPayload {
  sub: string;
  exp: number;
  user_id?: number;
  user_type?: string;
  [key: string]: unknown;
}

/**
 * Decode JWT token payload without verification (client-side only).
 * Server validates the signature - this is just for extracting user info.
 */
function decodeJwtPayload(token: string): JwtPayload | null {
  try {
    const base64Url = token.split('.')[1];
    const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
    const jsonPayload = decodeURIComponent(
      atob(base64)
        .split('')
        .map(c => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2))
        .join('')
    );
    return JSON.parse(jsonPayload);
  } catch {
    // Persisted access tokens can be malformed; callers decide whether to refresh or clear.
    return null;
  }
}

function syncUserPreferences(user: User | null | undefined) {
  if (user?.settings?.ui_language) {
    const locale = user.settings.ui_language.split('-')[0];
    useLocaleStore.getState().setLocale(locale);
  }

  if (user?.settings?.dark_mode !== undefined) {
    useThemeStore.getState().setDarkMode(user.settings.dark_mode);
  }

  if (user?.settings?.high_contrast !== undefined) {
    useThemeStore.getState().setHighContrast(user.settings.high_contrast);
  }
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => {
      const emptyAuthState = () => ({
        user: null,
        token: null,
        refreshToken: null,
        isAuthenticated: false,
        sessionExpiresAt: null,
        error: null,
      });

      const notifySessionEnd = () => {
        // Notify feature stores without importing them here. This avoids a
        // circular auth -> API -> learning-store dependency while ensuring
        // explicit logout and API-triggered 401 logout share cleanup.
        if (typeof window !== 'undefined') {
          window.dispatchEvent(new Event('aac:auth-logout'));
        }
      };

      const clearSession = () => {
        // Invalidate any in-flight checkAuth publish for the ended session.
        checkAuthEpoch += 1;
        notifySessionEnd();
        set(emptyAuthState());
      };

      // Monotonic epoch for checkAuth/refresh: any newer session change invalidates in-flight publishes.
      let checkAuthEpoch = 0;
      // Per-token coalescing: each distinct refresh token gets its own
      // in-flight promise. A single-slot variable would let a second token
      // overwrite the first and prematurely clear it on settle.
      const refreshInFlightByToken = new Map<string, Promise<boolean>>();

      return {
        user: null,
        token: null,
        refreshToken: null,
        isAuthenticated: false,
        isLoading: false,
        error: null,
        sessionExpiresAt: null,

      login: async (username: string, password: string) => {
        const loginEpoch = ++checkAuthEpoch;
        const isStillCurrentLogin = () => loginEpoch === checkAuthEpoch;
        set({ isLoading: true, error: null });
        try {
          // Use OAuth2 token endpoint which returns JWT
          // Use URLSearchParams for application/x-www-form-urlencoded
          const params = new URLSearchParams();
          params.append('username', username);
          params.append('password', password);
          
          const tokenResponse = await api.post('/auth/token', params, {
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
          });
          
          const token = tokenResponse.data.access_token;
          const refreshToken = tokenResponse.data.refresh_token;
          
          // Decode JWT to extract user info and expiration
          const payload = decodeJwtPayload(token);
          if (!payload) {
            throw new Error('Invalid token received from server');
          }
          
          // Set token immediately so api interceptor can use it for the subsequent user request
          // We need to temporarily store it or use api.defaults.headers (but api.ts uses interceptors)
          // Best approach: update the state partially or pass header manually (which we do below)
          
          // Fetch full user details
          const userResponse = await api.get(`/auth/users/${payload.user_id}`, {
            headers: { 'Authorization': `Bearer ${token}` }
          });
          if (!isStillCurrentLogin()) return;
          const user = userResponse.data;
          const previousUser = get().user;
          if (previousUser && previousUser.id !== user.id && typeof window !== 'undefined') {
            // Invalidate session-scoped feature work before switching identities.
            window.dispatchEvent(new Event('aac:auth-context-changed'));
          }
          
          syncUserPreferences(user);
          
          // Extract expiration from JWT (exp is in seconds, convert to ms)
          const expiresAt = payload.exp ? payload.exp * 1000 : Date.now() + 2 * 60 * 60 * 1000;
          
          set({
            user,
            token,
            refreshToken,
            isAuthenticated: true,
            isLoading: false,
            sessionExpiresAt: expiresAt,
            error: null,
          });
        } catch (e: unknown) {
          set({ error: extractError(e, i18n.t('common:errors.loginFailed')), isLoading: false });
          throw e;
        }
      },

      setupAdmin: async (setupData: AuthSetupData) => {
        const setupEpoch = ++checkAuthEpoch;
        const isStillCurrentSetup = () => setupEpoch === checkAuthEpoch;
        set({ isLoading: true, error: null });
        try {
          const response = await api.post('/auth/setup', setupData);
          if (!isStillCurrentSetup()) return;
          const token = response.data.access_token;
          const refreshToken = response.data.refresh_token;
          const user = response.data.user;
          const payload = decodeJwtPayload(token);
          const expiresAt = payload?.exp ? payload.exp * 1000 : Date.now() + 2 * 60 * 60 * 1000;
          syncUserPreferences(user);
          set({
            user,
            token,
            refreshToken,
            isAuthenticated: true,
            isLoading: false,
            sessionExpiresAt: expiresAt,
            error: null,
          });
        } catch (e: unknown) {
          set({ error: extractError(e, i18n.t('common:errors.setupFailed')), isLoading: false });
          throw e;
        }
      },

      register: async (userData: RegistrationData) => {
        set({ isLoading: true, error: null });
        try {
          await api.post('/auth/register', userData);
          set({ isLoading: false });
        } catch (error: unknown) {
          set({ error: extractError(error, i18n.t('common:errors.registrationFailed')), isLoading: false });
          throw error;
        }
      },

      logout: async () => {
        const token = get().token;
        // Clear session-scoped feature state synchronously so offline
        // mutations and conflicts cannot leak into the next session, even
        // while the revocation request is still in flight.
        checkAuthEpoch += 1;
        notifySessionEnd();
        if (token) {
          // Wait for server-side revocation to finish before flipping
          // isAuthenticated, so a token captured before logout is rejected by
          // the time the UI reaches the login screen. Revocation is
          // best-effort: a failure still clears the local session.
          try {
            await api.post('/auth/logout', null, {
              headers: { Authorization: `Bearer ${token}` },
            });
          } catch {
            // Ignore revocation errors; local session is still cleared below.
          }
        }
        set(emptyAuthState());
      },

      checkAuth: async () => {
        const { token, refreshAccessToken, user } = get();
        if (!token) {
          clearSession();
          return;
        }

        // Generation guard: a fetch started here must never publish into a
        // session that changed while the request was in flight (logout, a
        // new login, or a 401-triggered clear).
        const requestEpoch = ++checkAuthEpoch;
        const isCurrentRequest = () => requestEpoch === checkAuthEpoch;

        // Decode to check expiration without call
        const payload = decodeJwtPayload(token);
        const now = Date.now() / 1000;
        if (!payload?.exp || payload.exp < now) {
          // The refresh token is the source of truth when access validation fails.
          const refreshed = await refreshAccessToken();
          if (!isCurrentRequest()) return;
          if (!refreshed && navigator.onLine !== false) {
            clearSession();
          }
          return;
        }
        
        // Token valid, ensure user data is loaded if missing
        if (!user && payload.user_id) {
          try {
            const userResponse = await api.get(`/auth/users/${payload.user_id}`);
            if (!isCurrentRequest()) return;
            const fetchedUser = userResponse.data;
            syncUserPreferences(fetchedUser);
            set({ user: fetchedUser, isAuthenticated: true });
          } catch (error: unknown) {
            // If offline, don't log out. A stale request must not clear the
            // newer session either — one guard covers both.
            if (isOfflineError(error) || !isCurrentRequest()) return;
            // If we can't get user details, token might be invalid on server side
            clearSession();
          }
        } else {
          if (!isCurrentRequest()) return;
          // Sync settings from existing user state
          syncUserPreferences(user);
          set({ isAuthenticated: true });
        }
      },
      
      refreshAccessToken: async () => {
        const capturedRefreshToken = get().refreshToken;
        const capturedUserId = get().user?.id ?? null;
        const generationAtStart = checkAuthEpoch;
        if (!capturedRefreshToken) return false;
        // Coalesce concurrent refreshes, but only for the SAME token:
        // an in-flight refresh bound to another session's token must never
        // be awaited by a new session (its result is discarded internally,
        // and the new session needs its own request). Per-token map prevents
        // a single-slot overwrite from clearing the wrong entry on settle.
        const existing = refreshInFlightByToken.get(capturedRefreshToken);
        if (existing) return existing;
        const inFlight: Promise<boolean> = (async () => {
        try {
          const response = await api.post('/auth/refresh', { refresh_token: capturedRefreshToken });
          
          const newToken = response.data.access_token;
          if (newToken) {
            // Discard stale success if session changed during the request
            if (generationAtStart !== checkAuthEpoch || get().user?.id !== capturedUserId) return false;
            // Also discard if refresh token was rotated/changed
            if (get().refreshToken !== capturedRefreshToken) return false;
            const payload = decodeJwtPayload(newToken);
            const expiresAt = payload?.exp ? payload.exp * 1000 : Date.now() + 2 * 60 * 60 * 1000;
            set({ token: newToken, sessionExpiresAt: expiresAt });
            return true;
          }
          return false;
        } catch (error: unknown) {
          if (isOfflineError(error)) return false;
          // Discard stale failure if session already changed
          if (generationAtStart !== checkAuthEpoch || get().user?.id !== capturedUserId) return false;
          if (get().refreshToken !== capturedRefreshToken) return false;
          clearSession();
          return false;
        } finally {
          // The map can only hold OUR entry for this token while we are in
          // flight: concurrent callers coalesce on the entry above, and a new
          // entry for the same token cannot be created until this delete runs.
          refreshInFlightByToken.delete(capturedRefreshToken);
        }
        })();
        refreshInFlightByToken.set(capturedRefreshToken, inFlight);
        return inFlight;
      }
      };
    },
    {
      name: 'auth-storage',
      partialize: (state) => ({ 
        token: state.token, 
        refreshToken: state.refreshToken,
        user: state.user,
        isAuthenticated: state.isAuthenticated,
        sessionExpiresAt: state.sessionExpiresAt
      }),
      onRehydrateStorage: () => () => {
        if (typeof window !== 'undefined') {
          window.dispatchEvent(new Event('aac:auth-ready'));
        }
      },
    }
  )
);

registerAuthStateReader(() => useAuthStore.getState());
