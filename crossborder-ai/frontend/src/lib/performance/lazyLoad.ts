import {
  lazy,
  type ComponentType,
  type LazyExoticComponent,
} from 'react'

const RELOAD_AT_KEY = 'veya-chunk-reload-at'
const RELOAD_COOLDOWN_MS = 30_000

interface ChunkStorage {
  getItem: (key: string) => string | null
  setItem: (key: string, value: string) => void
  removeItem: (key: string) => void
}

interface ChunkRecoveryOptions {
  reload?: () => void
  storage?: ChunkStorage | null
  now?: () => number
  wait?: () => Promise<void>
}

function getSessionStorage(): ChunkStorage | null {
  if (typeof window === 'undefined') return null
  try {
    return window.sessionStorage
  } catch {
    return null
  }
}

function reloadPage(): void {
  if (typeof window !== 'undefined') {
    window.location.reload()
  }
}

function waitForRetry(): Promise<void> {
  if (typeof window === 'undefined') return Promise.resolve()
  return new Promise((resolve) => window.setTimeout(resolve, 350))
}

/** 识别 Vite 分包加载失败，避免把普通业务异常误判成部署版本变化。 */
export function isChunkLoadError(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error || '')
  return [
    'failed to fetch dynamically imported module',
    'importing a module script failed',
    'chunkloaderror',
    'loading chunk',
  ].some((keyword) => message.toLowerCase().includes(keyword))
}

/**
 * 动态 import 短暂失败时重试一次；版本切换导致持续 404 时自动刷新一次。
 * sessionStorage 冷却窗口用于阻止发布异常时形成无限刷新循环。
 */
export async function loadChunkWithRecovery<T>(
  loader: () => Promise<T>,
  options: ChunkRecoveryOptions = {},
): Promise<T> {
  try {
    return await loader()
  } catch (firstError) {
    if (!isChunkLoadError(firstError)) throw firstError
  }

  const storage = options.storage ?? getSessionStorage()
  await (options.wait ?? waitForRetry)()

  try {
    const module = await loader()
    storage?.removeItem(RELOAD_AT_KEY)
    return module
  } catch (secondError) {
    if (!isChunkLoadError(secondError)) throw secondError

    const now = (options.now ?? Date.now)()
    const lastReloadAt = Number(storage?.getItem(RELOAD_AT_KEY) || 0)
    if (!lastReloadAt || now - lastReloadAt > RELOAD_COOLDOWN_MS) {
      storage?.setItem(RELOAD_AT_KEY, String(now))
      ;(options.reload ?? reloadPage)()
    }
    throw secondError
  }
}

/** 给 React.lazy 增加部署切换期间的 chunk 恢复能力。 */
export function lazyWithRetry<T extends ComponentType<any>>(
  loader: () => Promise<{ default: T }>,
): LazyExoticComponent<T> {
  return lazy(() => loadChunkWithRecovery(loader))
}
