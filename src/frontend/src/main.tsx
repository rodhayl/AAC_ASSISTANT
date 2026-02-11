import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import './styles/mobile-enhancements.css'
import App from './App.tsx'
import { initPerfMetrics } from './lib/perf'
import './i18n/index'
import { I18nextProvider } from 'react-i18next'
import i18n from './i18n/index'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <I18nextProvider i18n={i18n}>
      <App />
    </I18nextProvider>
  </StrictMode>,
)
initPerfMetrics()
