import { afterEach, describe, expect, it, vi } from 'vitest'

import { authApi } from './auth'

type MockFetchResponse = {
  ok: boolean
  status: number
  json?: () => Promise<unknown>
}

describe('auth logout', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('访问令牌仍有效时只撤销当前 Web 会话', async () => {
    const fetchMock = vi.fn(
      async (
        _input: RequestInfo | URL,
        _init?: RequestInit,
      ): Promise<MockFetchResponse> => ({
        ok: true,
        status: 204,
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await authApi.logout('valid-access', 'stored-refresh')

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(String(fetchMock.mock.calls[0][0])).toContain('/auth/logout')
  })

  it('访问令牌过期时先轮换再撤销同一设备会话', async () => {
    const fetchMock = vi
      .fn(
        async (
          _input: RequestInfo | URL,
          _init?: RequestInit,
        ): Promise<MockFetchResponse> => ({
          ok: true,
          status: 204,
        }),
      )
      .mockResolvedValueOnce({ ok: false, status: 401 })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ access_token: 'rotated-access' }),
      })
      .mockResolvedValueOnce({ ok: true, status: 204 })
    vi.stubGlobal('fetch', fetchMock)

    await authApi.logout('expired-access', 'stored-refresh')

    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(String(fetchMock.mock.calls[1][0])).toContain('/auth/refresh')
    expect(String(fetchMock.mock.calls[2][0])).toContain('/auth/logout')
    expect(fetchMock.mock.calls[2][1]?.headers).toMatchObject({
      Authorization: 'Bearer rotated-access',
    })
  })
})
