/**
 * Frontend configuration for AAC Assistant.
 * Values are loaded from the backend /api/config endpoint or use defaults.
 */

// Default configuration (should match .env.example and backend release metadata)
const defaults = {
  BACKEND_PORT: Number(import.meta.env.VITE_BACKEND_PORT) || 8086,
  FRONTEND_PORT: Number(import.meta.env.VITE_FRONTEND_PORT) || 5176,
  API_BASE_URL: import.meta.env.VITE_API_BASE_URL || '',
  OLLAMA_BASE_URL: import.meta.env.VITE_OLLAMA_BASE_URL || 'http://localhost:11434',
  LMSTUDIO_BASE_URL: import.meta.env.VITE_LMSTUDIO_BASE_URL || 'http://localhost:1234/v1',
  AI_MAX_TOKENS: Number(import.meta.env.VITE_AI_MAX_TOKENS) || 1024,
  AI_TEMPERATURE: import.meta.env.VITE_AI_TEMPERATURE
    ? Number(import.meta.env.VITE_AI_TEMPERATURE)
    : 0.5,
  APP_NAME: import.meta.env.VITE_APP_NAME || 'AAC Assistant',
  APP_VERSION: import.meta.env.VITE_APP_VERSION || '2.0.0',
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
  LMSTUDIO_BASE_URL: defaults.LMSTUDIO_BASE_URL,
  AI_MAX_TOKENS: defaults.AI_MAX_TOKENS,
  AI_TEMPERATURE: defaults.AI_TEMPERATURE,
  
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
    if (typeof window === 'undefined') {
      return `http://127.0.0.1:${defaults.BACKEND_PORT}`;
    }

    // Vite does not proxy /docs, so point the navbar link at the backend in
    // development. Production serves the SPA and docs from the same origin.
    if (window.location.port === String(defaults.FRONTEND_PORT)) {
      return `${window.location.protocol}//${window.location.hostname}:${defaults.BACKEND_PORT}`;
    }
    return '';
  },
};

export default config;
