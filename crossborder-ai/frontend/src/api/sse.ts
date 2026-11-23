// ============================================================================
// VeyaShip - 极简 SSE 客户端
// 原生 EventSource 无法携带 Authorization 头（JWT 放在 header 里），
// 这里用 fetch + ReadableStream 手动解析 text/event-stream：
//   - 支持自定义事件名（event: step / event: done）
//   - 忽略注释行心跳（: ping），长连接不会被误判为结束
//   - 超时走 controller.abort()，用于区分「任务超时」与「连接失败」
//     （超时意味着任务确实没跑完，连接失败则可回退轮询）
// ============================================================================

import {
  ACCESS_TOKEN_STORAGE_KEY,
  API_BASE,
  refreshAccessToken,
} from './client'

export interface SseEvent {
  event: string
  data: unknown
}

/** 任务超时（区别于连接失败）。连接失败可回退轮询，超时不能 */
export class TaskTimeoutError extends Error {}

/**
 * 订阅一条 SSE 流：每个事件都会回调 onEvent，返回 true 表示停止并返回该事件 payload。
 * 超时抛 TaskTimeoutError；连接失败 / 流提前关闭抛普通 Error。
 */
export async function readSseUntil(
  url: string,
  {
    onEvent,
    timeoutMs,
    token = localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY) || '',
  }: {
    onEvent: (ev: SseEvent) => boolean | void
    timeoutMs: number
    token?: string
  },
): Promise<unknown> {
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), timeoutMs)

  try {
    const connect = (accessToken: string) =>
      fetch(url, {
        headers: {
          Authorization: `Bearer ${accessToken}`,
          Accept: 'text/event-stream',
        },
        signal: controller.signal,
      })

    let resp = await connect(token)
    if (resp.status === 401) {
      const refreshedToken = await refreshAccessToken()
      if (refreshedToken) resp = await connect(refreshedToken)
    }
    if (!resp.ok || !resp.body) {
      throw new Error(`SSE 连接失败（HTTP ${resp.status}）`)
    }

    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      // 空行分隔事件块；一次可能读到多个事件，逐个消费
      let idx: number
      while ((idx = buffer.indexOf('\n\n')) !== -1) {
        const chunk = buffer.slice(0, idx)
        buffer = buffer.slice(idx + 2)
        const ev = parseSseChunk(chunk)
        if (ev && onEvent(ev)) return ev.data
      }
    }
    // 流自然结束但没等到目标事件（理论上心跳会续流，此处兜底）
    throw new Error('SSE 流提前关闭')
  } catch (err) {
    if (controller.signal.aborted) {
      throw new TaskTimeoutError('SSE 连接超时')
    }
    throw err
  } finally {
    window.clearTimeout(timer)
  }
}

/** 解析单个 SSE 块（event:/data:/注释行），无有效数据返回 null */
function parseSseChunk(chunk: string): SseEvent | null {
  let event = 'message'
  const dataLines: string[] = []
  for (const line of chunk.split('\n')) {
    const trimmed = line.startsWith(' ') ? line.slice(1) : line
    if (trimmed.startsWith(':')) continue // 心跳/注释
    if (trimmed.startsWith('event:')) {
      event = trimmed.slice(6).trim()
    } else if (trimmed.startsWith('data:')) {
      dataLines.push(trimmed.slice(5).replace(/^ /, ''))
    }
  }
  if (dataLines.length === 0) return null
  const raw = dataLines.join('\n')
  let data: unknown = raw
  try {
    data = JSON.parse(raw)
  } catch {
    // 非 JSON 载荷（理论不发生），保留原文
  }
  return { event, data }
}

export { API_BASE }
