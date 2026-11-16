import { describe, expect, it, vi } from 'vitest'

import {
  isChunkLoadError,
  lazyWithRetry,
  loadChunkWithRecovery,
} from './lazyLoad'

function createStorage() {
  const values = new Map<string, string>()
  return {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => {
      values.set(key, value)
    },
    removeItem: (key: string) => {
      values.delete(key)
    },
  }
}

describe('loadChunkWithRecovery', () => {
  it('recognizes common chunk errors and ignores ordinary exceptions', () => {
    expect(isChunkLoadError(new Error('ChunkLoadError: Loading chunk 12 failed'))).toBe(true)
    expect(isChunkLoadError('Importing a module script failed')).toBe(true)
    expect(isChunkLoadError(new Error('API request failed'))).toBe(false)
  })

  it('retries a transient dynamic import failure', async () => {
    const loader = vi
      .fn()
      .mockRejectedValueOnce(new TypeError('Failed to fetch dynamically imported module'))
      .mockResolvedValueOnce({ default: 'page' })
    const reload = vi.fn()

    await expect(
      loadChunkWithRecovery(loader, {
        reload,
        storage: createStorage(),
        wait: async () => {},
      }),
    ).resolves.toEqual({ default: 'page' })
    expect(loader).toHaveBeenCalledTimes(2)
    expect(reload).not.toHaveBeenCalled()
  })

  it('reloads once when the chunk remains unavailable', async () => {
    const error = new TypeError('Failed to fetch dynamically imported module')
    const loader = vi.fn().mockRejectedValue(error)
    const reload = vi.fn()
    const storage = createStorage()

    await expect(
      loadChunkWithRecovery(loader, {
        reload,
        storage,
        now: () => 1_000_000,
        wait: async () => {},
      }),
    ).rejects.toBe(error)
    expect(loader).toHaveBeenCalledTimes(2)
    expect(reload).toHaveBeenCalledTimes(1)
  })

  it('does not create a reload loop after a recent recovery attempt', async () => {
    const error = new TypeError('Importing a module script failed')
    const loader = vi.fn().mockRejectedValue(error)
    const reload = vi.fn()
    const storage = createStorage()
    storage.setItem('veya-chunk-reload-at', '995000')

    await expect(
      loadChunkWithRecovery(loader, {
        reload,
        storage,
        now: () => 1_000_000,
        wait: async () => {},
      }),
    ).rejects.toBe(error)
    expect(reload).not.toHaveBeenCalled()
  })

  it('uses safe defaults when storage and reload hooks are unavailable', async () => {
    const transientLoader = vi
      .fn()
      .mockRejectedValueOnce(new TypeError('Failed to fetch dynamically imported module'))
      .mockResolvedValueOnce({ default: 'page' })
    await expect(loadChunkWithRecovery(transientLoader)).resolves.toEqual({
      default: 'page',
    })

    const persistentLoader = vi
      .fn()
      .mockRejectedValue(new TypeError('Failed to fetch dynamically imported module'))
    await expect(
      loadChunkWithRecovery(persistentLoader, { wait: async () => {} }),
    ).rejects.toThrow('Failed to fetch dynamically imported module')
  })

  it('creates a React lazy component that keeps the recovery wrapper', () => {
    const Page = lazyWithRetry(async () => ({
      default: () => null,
    }))
    expect(Page).toBeDefined()
  })
})
