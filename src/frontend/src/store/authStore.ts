import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import api from '../lib/api';
import type { User } from '../types';
// Remove duplicate import if present or keep only one
import { useLocaleStore } from './localeStore';
import { useThemeStore } from './themeStore';

interface AuthState {
  user: User | null;
  token: string | null;
  refreshToken: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;
  sessionExpiresAt: number | null;
  
  login: (username: string, password: string) => Promise<void>;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  register: (userData: any) => Promise<void>;
  updateProfile: (data: Partial<User>) => Promise<void>;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  updatePreferences: (preferences: any) => Promise<void>;
  logout: () => void;
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
  } catch (e) {
    console.error('Failed to decode JWT:', e);
    return null;
  }
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      token: null,
      refreshToken: null,
      isAuthenticated: false,
      isLoading: false,
      error: null,
      sessionExpiresAt: null,

      login: async (username: string, password: string) => {
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
          const user = userResponse.data;
          
          // Update locale if user has a preference
          if (user.settings?.ui_language) {
            // Strip region code if present (e.g. en-US -> en) to match i18n configuration
            const locale = user.settings.ui_language.split('-')[0];
            useLocaleStore.getState().setLocale(locale);
          }

          // Update theme if user has a preference
          if (user.settings?.dark_mode !== undefined) {
            useThemeStore.getState().setDarkMode(user.settings.dark_mode);
          }
          
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
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          const r = e as { response?: { data?: { detail?: any } } };
          const d = r.response?.data?.detail;
          let errorMsg = 'Login failed';
          if (Array.isArray(d)) {
             // eslint-disable-next-line @typescript-eslint/no-explicit-any
             errorMsg = d.map((err: any) => err.msg).join(', ');
          } else if (typeof d === 'string') {
             errorMsg = d;
          } else if (d) {
             errorMsg = JSON.stringify(d);
          }
          set({ error: errorMsg, isLoading: false });
          throw e;
        }
      },

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      register: async (userData: any) => {
        set({ isLoading: true, error: null });
        try {
          await api.post('/auth/register', userData);
          set({ isLoading: false });
        } catch (error: unknown) {
          const detail = (() => {
            if (typeof error === 'object' && error && 'response' in error) {
              // eslint-disable-next-line @typescript-eslint/no-explicit-any
              const r = error as { response?: { data?: { detail?: any } } };
              const d = r.response?.data?.detail;
              if (Array.isArray(d)) {
                  // eslint-disable-next-line @typescript-eslint/no-explicit-any
                  return d.map((e: any) => e.msg).join(', ');
              }
              return typeof d === 'string' ? d : JSON.stringify(d) || 'Registration failed';
            }
            return (error as Error).message || 'Registration failed';
          })();
          set({ error: detail, isLoading: false });
          throw error;
        }
      },

      updateProfile: async (data) => {
        set({ isLoading: true, error: null });
        try {
          const response = await api.put('/users/me', data);
          set({ user: response.data, isLoading: false });
        } catch (error: unknown) {
          set({ error: 'Failed to update profile', isLoading: false });
          throw error;
        }
      },

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      updatePreferences: async (preferences: any) => {
        set({ isLoading: true, error: null });
        try {
          await api.put('/auth/preferences', preferences);
          // Refresh user data to get updated preferences
          const response = await api.get('/users/me');
          const user = response.data;

          // Update locale if user has a preference
          if (user.settings?.ui_language) {
            // Strip region code if present (e.g. en-US -> en) to match i18n configuration
            const locale = user.settings.ui_language.split('-')[0];
            useLocaleStore.getState().setLocale(locale);
          }

          // Update theme if user has a preference
          if (user.settings?.dark_mode !== undefined) {
            useThemeStore.getState().setDarkMode(user.settings.dark_mode);
          }

          set({ user, isLoading: false });
        } catch (error: unknown) {
          set({ error: 'Failed to update preferences', isLoading: false });
          throw error;
        }
      },

      logout: () => {
        set({
          user: null,
          token: null,
          refreshToken: null,
          isAuthenticated: false,
          sessionExpiresAt: null,
          error: null,
        });
        // Clear any manual token overrides if they exist
        localStorage.removeItem('token');
      },

      checkAuth: async () => {
        const { token, refreshAccessToken, user } = get();
        if (!token) {
          set({ isAuthenticated: false });
          return;
        }
        
        // Decode to check expiration without call
        const payload = decodeJwtPayload(token);
        if (!payload || !payload.exp) {
          set({ isAuthenticated: false, token: null, user: null });
          return;
        }
        
        const now = Date.now() / 1000;
        if (payload.exp < now) {
          // Token expired, try refresh
          const refreshed = await refreshAccessToken();
          if (!refreshed) {
            set({ isAuthenticated: false, token: null, user: null });
          }
          return;
        }
        
        // Token valid, ensure user data is loaded if missing
        if (!user && payload.user_id) {
          try {
            const userResponse = await api.get(`/auth/users/${payload.user_id}`);
            const fetchedUser = userResponse.data;
            
            // Sync settings
            if (fetchedUser.settings?.ui_language) {
              const locale = fetchedUser.settings.ui_language.split('-')[0];
              useLocaleStore.getState().setLocale(locale);
            }
            if (fetchedUser.settings?.dark_mode !== undefined) {
              useThemeStore.getState().setDarkMode(fetchedUser.settings.dark_mode);
            }

            set({ user: fetchedUser, isAuthenticated: true });
          } catch (error: unknown) {
            // If offline, don't log out
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            if ((error as any)?.code === 'ERR_OFFLINE' || (error as any)?.message === 'offline') {
              return;
            }
            // If we can't get user details, token might be invalid on server side
            set({ isAuthenticated: false, token: null, user: null });
          }
        } else {
          // Sync settings from existing user state
          if (user?.settings?.dark_mode !== undefined) {
            useThemeStore.getState().setDarkMode(user.settings.dark_mode);
          }
          if (user?.settings?.ui_language) {
             const locale = user.settings.ui_language.split('-')[0];
             useLocaleStore.getState().setLocale(locale);
          }
          set({ isAuthenticated: true });
        }
      },
      
      refreshAccessToken: async () => {
        const { refreshToken } = get();
        if (!refreshToken) return false;
        
        try {
          // Use URLSearchParams for form data
          const params = new URLSearchParams();
          params.append('refresh_token', refreshToken);
          
          const response = await api.post('/auth/refresh', null, {
            params: { refresh_token: refreshToken } // Some backends might want query param or body
          });
          
          const newToken = response.data.access_token;
          if (newToken) {
            const payload = decodeJwtPayload(newToken);
            const expiresAt = payload?.exp ? payload.exp * 1000 : Date.now() + 2 * 60 * 60 * 1000;
            
            set({ 
              token: newToken, 
              sessionExpiresAt: expiresAt 
            });
            return true;
          }
          return false;
        } catch (error: unknown) {
          // If offline, don't clear session, just return false (failed to refresh)
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          if ((error as any)?.code === 'ERR_OFFLINE' || (error as any)?.message === 'offline') {
            return false;
          }
          // Refresh failed
          set({ 
            user: null, 
            token: null, 
            refreshToken: null, 
            isAuthenticated: false, 
            sessionExpiresAt: null 
          });
          return false;
        }
      }
    }),
    {
      name: 'auth-storage',
      partialize: (state) => ({ 
        token: state.token, 
        refreshToken: state.refreshToken,
        user: state.user,
        isAuthenticated: state.isAuthenticated,
        sessionExpiresAt: state.sessionExpiresAt
      }),
    }
  )
);
