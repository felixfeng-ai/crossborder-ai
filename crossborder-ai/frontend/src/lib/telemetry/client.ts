export type TelemetryEvent = {
  event_type: 'page_view' | 'web_vital'
  visitor_id: string
  session_id: string
  path: string
  referrer_host?: string
  country_hint?: string
  device_type: 'desktop' | 'tablet' | 'mobile' | 'unknown'
  viewport_width?: number
  connection_type?: string
  metric_name?: string
  metric_value?: number
  metric_rating?: string
  release?: string
  request_id?: string
}

type TelemetryQueueOptions = {
  batchSize?: number
  send: (events: TelemetryEvent[]) => Promise<void>
}

/**
 * 根据视口宽度做稳定设备分类，服务端不依赖 User-Agent 猜测设备。
 */
export function classifyDevice(width: number): TelemetryEvent['device_type'] {
  if (width < 640) return 'mobile'
  if (width < 1024) return 'tablet'
  return 'desktop'
}

/**
 * 页面路径只保留路由部分，避免 token、搜索词和 hash 进入分析表。
 */
export function normalizePath(value: string): string {
  return (value.split(/[?#]/, 1)[0] || '/').slice(0, 500)
}

/**
 * 批量遥测队列：控制请求数量，并在页面隐藏时允许主动补发。
 */
export function createTelemetryQueue({
  batchSize = 10,
  send,
}: TelemetryQueueOptions) {
  let events: TelemetryEvent[] = []
  let flushPromise: Promise<void> | null = null

  const flush = (): Promise<void> => {
    if (flushPromise) return flushPromise
    if (events.length === 0) return Promise.resolve()
    const batch = events.splice(0, events.length)
    flushPromise = send(batch).finally(() => {
      flushPromise = null
    })
    return flushPromise
  }

  return {
    enqueue(event: TelemetryEvent) {
      events.push(event)
      if (events.length >= batchSize) {
        void flush()
      }
    },
    flush,
  }
}
