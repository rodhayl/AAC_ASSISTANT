import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import './styles/mobile-enhancements.css'
import App from './App.tsx'
import { I18nextProvider } from 'react-i18next'
import i18n, { ensureLocale } from './i18n/index'

// The default locale (es) is bundled; the detected secondary locale (en) is
// code-split. Wait for it before the first render so English users never see
// a Spanish flash of unstyled content.
await ensureLocale(i18n.language || 'es')

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <I18nextProvider i18n={i18n}>
      <App />
    </I18nextProvider>
  </StrictMode>,
)

if (import.meta.env.DEV || import.meta.env.VITE_ENABLE_PERF === 'true') {
  void import('./lib/perf').then(({ initPerfMetrics }) => initPerfMetrics())
}
