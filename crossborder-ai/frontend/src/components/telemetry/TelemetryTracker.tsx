import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import type { Metric } from 'web-vitals'

import apiClient from '@/api/client'
import {
  classifyDevice,
  createTelemetryQueue,
  normalizePath,
  type TelemetryEvent,
} from '@/lib/telemetry/client'

let vitalsBound = false
let lastPageKey = ''
let currentReportPath = '/'

function randomId(): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID()
  }
  return `v-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function getOrCreateId(storage: Storage, key: string): string {
  try {
    const existing = storage.getItem(key)
    if (existing) return existing
    const value = randomId()
    storage.setItem(key, value)
    return value
  } catch {
    return randomId()
  }
}

function getVisitorId(): string {
  return getOrCreateId(window.localStorage, 'veyaship_visitor_id')
}

function getSessionId(): string {
  return getOrCreateId(window.sessionStorage, 'veyaship_session_id')
}

function connectionType(): string | undefined {
  const connection = (
    navigator as Navigator & { connection?: { effectiveType?: string } }
  ).connection
  return connection?.effectiveType
}

function countryHint(): string | undefined {
  try {
    if ('Locale' in Intl) {
      const locale = new Intl.Locale(navigator.language)
      return locale.region || undefined
    }
  } catch {
    // 浏览器不支持 Locale 时留空，由服务端标记 unknown。
  }
  return navigator.language.includes('-')
    ? navigator.language.split('-')[1]?.toUpperCase()
    : undefined
}

const queue = createTelemetryQueue({
  batchSize: 10,
  send: async (events) => {
    await apiClient.post('/telemetry/events', { events })
  },
})

function enqueuePageView(path: string) {
  if (path.startsWith('/admin')) return
  const pathname = normalizePath(path)
  const pageKey = `${getSessionId()}:${pathname}`
  if (pageKey === lastPageKey) return
  lastPageKey = pageKey
  queue.enqueue({
    event_type: 'page_view',
    visitor_id: getVisitorId(),
    session_id: getSessionId(),
    path: pathname,
    referrer_host: (() => {
      try {
        return document.referrer ? new URL(document.referrer).hostname : ''
      } catch {
        return ''
      }
    })(),
    country_hint: countryHint(),
    device_type: classifyDevice(window.innerWidth),
    viewport_width: window.innerWidth,
    connection_type: connectionType(),
    release: import.meta.env.VITE_RELEASE || 'web',
  })
}

function bindWebVitals() {
  if (vitalsBound || typeof window === 'undefined') return
  vitalsBound = true
  const report = (metric: Metric) => {
    const path = normalizePath(currentReportPath)
    if (path.startsWith('/admin')) return
    queue.enqueue({
      event_type: 'web_vital',
      visitor_id: getVisitorId(),
      session_id: getSessionId(),
      path,
      device_type: classifyDevice(window.innerWidth),
      viewport_width: window.innerWidth,
      connection_type: connectionType(),
      metric_name: metric.name,
      metric_value: metric.value,
      metric_rating: metric.rating,
      release: import.meta.env.VITE_RELEASE || 'web',
    })
  }
  void import('web-vitals').then(({ onCLS, onFCP, onINP, onLCP, onTTFB }) => {
    onLCP(report)
    onFCP(report)
    onINP(report)
    onCLS(report)
    onTTFB(report)
  })
}

/**
 * 全局匿名遥测挂载点，不阻塞首屏渲染。
 */
export function TelemetryTracker() {
  const location = useLocation()
  currentReportPath = location.pathname

  useEffect(() => {
    enqueuePageView(location.pathname)
  }, [location.pathname])

  useEffect(() => {
    bindWebVitals()
    const interval = window.setInterval(() => {
      if (document.visibilityState === 'visible') {
        void queue.flush()
      }
    }, 10000)
    const handleHide = () => {
      if (document.visibilityState === 'hidden') {
        void queue.flush()
      }
    }
    window.addEventListener('pagehide', handleHide)
    document.addEventListener('visibilitychange', handleHide)
    return () => {
      window.clearInterval(interval)
      window.removeEventListener('pagehide', handleHide)
      document.removeEventListener('visibilitychange', handleHide)
    }
  }, [])

  return null
}
