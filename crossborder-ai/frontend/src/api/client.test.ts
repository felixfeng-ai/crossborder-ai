import {
  AxiosError,
  AxiosHeaders,
  type AxiosResponse,
  type InternalAxiosRequestConfig,
} from 'axios'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import apiClient, {
  ACCESS_TOKEN_STORAGE_KEY,
  REFRESH_TOKEN_STORAGE_KEY,
  clearStoredAuthTokens,
  normalizeFormDataHeaders,
} from './client'

const originalAdapter = apiClient.defaults.adapter

describe('multipart request headers', () => {
  it('API 客户端不再全局强制 JSON Content-Type', () => {
    expect(apiClient.defaults.headers.common['Content-Type']).toBeUndefined()
  })

  it('FormData 请求移除全局 JSON Content-Type', () => {
    const headers = new AxiosHeaders({ 'Content-Type': 'application/json' })
    const config = {
      data: new FormData(),
      headers,
    }

    normalizeFormDataHeaders(config as never)

    expect(headers.get('Content-Type')).toBeUndefined()
  })

  it('普通 JSON 请求保留 Content-Type', () => {
    const headers = new AxiosHeaders({ 'Content-Type': 'application/json' })
    const config = {
      data: { title: '商品' },
      headers,
    }

    normalizeFormDataHeaders(config as never)

    expect(headers.get('Content-Type')).toBe('application/json')
  })
})

describe('authentication refresh', () => {
  beforeEach(() => {
    const values = new Map<string, string>()
    const storage = {
      clear: () => values.clear(),
      getItem: (key: string) => values.get(key) ?? null,
      removeItem: (key: string) => values.delete(key),
      setItem: (key: string, value: string) => values.set(key, value),
    }
    vi.stubGlobal('localStorage', storage)
    vi.stubGlobal('window', {
      localStorage: storage,
      location: { pathname: '/app', href: '' },
      dispatchEvent: vi.fn(),
      addEventListener: vi.fn(),
    })
    vi.stubGlobal(
      'CustomEvent',
      class CustomEvent<T> {
        detail: T

        constructor(
          public type: string,
          init?: { detail?: T },
        ) {
          this.detail = init?.detail as T
        }
      },
    )
    localStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, 'expired-access')
    localStorage.setItem(REFRESH_TOKEN_STORAGE_KEY, 'valid-refresh')
  })

  afterEach(() => {
    apiClient.defaults.adapter = originalAdapter
    vi.unstubAllGlobals()
  })

  it('并发 401 只轮换一次 refresh token，并重放原请求', async () => {
    let protectedCalls = 0
    apiClient.defaults.adapter = async (config) => {
      protectedCalls += 1
      const authorization = String(
        config.headers.get('Authorization') || '',
      )
      if (authorization === 'Bearer expired-access') {
        const unauthorized: AxiosResponse = {
          config,
          data: { detail: 'expired' },
          headers: new AxiosHeaders(),
          status: 401,
          statusText: 'Unauthorized',
        }
        throw new AxiosError(
          'expired',
          'ERR_BAD_REQUEST',
          config,
          undefined,
          unauthorized,
        )
      }
      return {
        config,
        data: { ok: true },
        headers: new AxiosHeaders(),
        status: 200,
        statusText: 'OK',
      }
    }

    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        access_token: 'fresh-access',
        refresh_token: 'rotated-refresh',
      }),
    }))
    vi.stubGlobal('fetch', fetchMock)

    const responses = await Promise.all([
      apiClient.get<{ ok: boolean }>('/billing/wallet'),
      apiClient.get<{ ok: boolean }>('/billing/wallet'),
    ])

    expect(responses.map((response) => response.data.ok)).toEqual([true, true])
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(protectedCalls).toBe(4)
    expect(localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY)).toBe('fresh-access')
    expect(localStorage.getItem(REFRESH_TOKEN_STORAGE_KEY)).toBe(
      'rotated-refresh',
    )
  })

  it('刷新接口不携带旧访问令牌', async () => {
    const fetchMock = vi.fn(async () => ({
      ok: false,
      json: async () => ({ detail: 'rejected' }),
    }))
    vi.stubGlobal('fetch', fetchMock)

    apiClient.defaults.adapter = async (
      config: InternalAxiosRequestConfig,
    ) => {
      const unauthorized: AxiosResponse = {
        config,
        data: { detail: 'expired' },
        headers: new AxiosHeaders(),
        status: 401,
        statusText: 'Unauthorized',
      }
      throw new AxiosError(
        'expired',
        'ERR_BAD_REQUEST',
        config,
        undefined,
        unauthorized,
      )
    }

    await expect(apiClient.get('/billing/wallet')).rejects.toBeTruthy()

    const [, options] = fetchMock.mock.calls[0] as unknown as [
      string,
      RequestInit,
    ]
    expect(new Headers(options.headers).get('Authorization')).toBeNull()
  })

  it('退出后到达的刷新结果不会重新写回旧账号会话', async () => {
    apiClient.defaults.adapter = async (
      config: InternalAxiosRequestConfig,
    ) => {
      const unauthorized: AxiosResponse = {
        config,
        data: { detail: 'expired' },
        headers: new AxiosHeaders(),
        status: 401,
        statusText: 'Unauthorized',
      }
      throw new AxiosError(
        'expired',
        'ERR_BAD_REQUEST',
        config,
        undefined,
        unauthorized,
      )
    }

    let resolveRefresh: ((value: unknown) => void) | undefined
    const refreshResponse = new Promise((resolve) => {
      resolveRefresh = resolve
    })
    const fetchMock = vi.fn(async () => refreshResponse)
    vi.stubGlobal('fetch', fetchMock)

    const request = apiClient.get('/billing/wallet')
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    clearStoredAuthTokens()
    resolveRefresh?.({
      ok: true,
      json: async () => ({
        access_token: 'late-access',
        refresh_token: 'late-refresh',
      }),
    })

    await expect(request).rejects.toBeTruthy()
    expect(localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY)).toBeNull()
    expect(localStorage.getItem(REFRESH_TOKEN_STORAGE_KEY)).toBeNull()
  })
})
