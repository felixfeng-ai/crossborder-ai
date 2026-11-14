import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import ErrorBoundary from '@/components/common/ErrorBoundary'
import { TelemetryTracker } from '@/components/telemetry/TelemetryTracker'
import './styles/globals.css'
import './i18n'
import { initTheme } from '@/utils/themes'

initTheme() // 加载主题

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <TelemetryTracker />
      <ErrorBoundary>
        <App />
      </ErrorBoundary>
    </BrowserRouter>
  </React.StrictMode>,
)
