import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import 'sonner/dist/styles.css'
import './styles/mobile-enhancements.css'
import App from './App.tsx'
import { I18nextProvider } from 'react-i18next'
import i18n, { ensureLocale } from './i18n/index'

// The default locale (es) is bundled; the detected secondary locale (en) is
// code-split. Wait for it before the first render so English users never see
// a Spanish flash of unstyled content.
// Never let a failed chunk fetch blank the app: the bundled Spanish fallback
// still renders, so mount anyway and keep the failure in the console.
try {
  await ensureLocale(i18n.language || 'es')
} catch (error) {
  console.error('Failed to load the requested locale; using the bundled default', error)
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <I18nextProvider i18n={i18n}>
      <App />
    </I18nextProvider>
  </StrictMode>,
)
