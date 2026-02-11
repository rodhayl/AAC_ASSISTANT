/**
 * Frontend configuration for AAC Assistant.
 * Values are loaded from the backend /api/config endpoint or use defaults.
 */

// Default configuration (should match env.properties)
const defaults = {
  BACKEND_PORT: Number(import.meta.env.VITE_BACKEND_PORT) || 8090,
  FRONTEND_PORT: Number(import.meta.env.VITE_FRONTEND_PORT) || 5176,
  API_BASE_URL: import.meta.env.VITE_API_BASE_URL || '',
  OLLAMA_BASE_URL: import.meta.env.VITE_OLLAMA_BASE_URL || 'http://localhost:11434',
  APP_NAME: import.meta.env.VITE_APP_NAME || 'AAC Assistant',
  APP_VERSION: import.meta.env.VITE_APP_VERSION || '1.0.0',
};

function getDefaultApiBaseUrl() {
  // Prefer same-origin `/api` so Vite proxy or reverse proxy can avoid CORS.
  if (typeof window !== 'undefined') return '/api';
  return `http://127.0.0.1:${defaults.BACKEND_PORT}/api`;
}

function getWsBaseUrl() {
  // Same-origin WS when possible (works with Vite proxy).
  if (typeof window !== 'undefined') {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${protocol}//${window.location.host}/api`;
  }
  return `ws://127.0.0.1:${defaults.BACKEND_PORT}/api`;
}

// Configuration object
export const config = {
  // Server
  BACKEND_PORT: defaults.BACKEND_PORT,
  FRONTEND_PORT: defaults.FRONTEND_PORT,
  
  // AI
  OLLAMA_BASE_URL: defaults.OLLAMA_BASE_URL,
  
  // App
  APP_NAME: defaults.APP_NAME,
  APP_VERSION: defaults.APP_VERSION,
  DEFAULT_LOCALE: 'es-ES',
  
  // Computed URLs
  get API_BASE_URL() {
    return defaults.API_BASE_URL || getDefaultApiBaseUrl();
  },
  
  get WS_BASE_URL() {
    return getWsBaseUrl();
  },
  
  get BACKEND_URL() {
    return '';
  },
};

// Load configuration from backend (call this on app init if needed)
export async function loadConfig(): Promise<void> {
  try {
    const configUrl = `${(defaults.API_BASE_URL || '/api').replace(/\/$/, '')}/config`;
    const response = await fetch(configUrl);
    if (response.ok) {
      const data = await response.json();
      if (data.backend_port) config.BACKEND_PORT = data.backend_port;
      if (data.frontend_port) config.FRONTEND_PORT = data.frontend_port;
      if (data.ollama_base_url) config.OLLAMA_BASE_URL = data.ollama_base_url;
      if (data.app_name) config.APP_NAME = data.app_name;
      if (data.app_version) config.APP_VERSION = data.app_version;
      if (data.default_locale) config.DEFAULT_LOCALE = data.default_locale;
    }
  } catch {
    // Use defaults if config endpoint unavailable
  }
}

export default config;
