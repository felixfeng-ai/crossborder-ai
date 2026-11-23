import { describe, expect, it } from 'vitest'

import { retryDelay, shouldRetryQuery } from './queryClient'

describe('query retry policy', () => {
  it('网络错误和 5xx 最多退避重试两次', () => {
    expect(shouldRetryQuery(0, new Error('network'))).toBe(true)
    expect(shouldRetryQuery(2, new Error('network'))).toBe(false)
    expect(
      shouldRetryQuery(1, { response: { status: 503 } }),
    ).toBe(true)
  })

  it('4xx 不进行无意义重试', () => {
    expect(
      shouldRetryQuery(0, { response: { status: 401 } }),
    ).toBe(false)
    expect(
      shouldRetryQuery(0, { response: { status: 404 } }),
    ).toBe(false)
  })

  it('重试延迟按指数增长并封顶', () => {
    expect(retryDelay(0)).toBe(1_000)
    expect(retryDelay(1)).toBe(2_000)
    expect(retryDelay(10)).toBe(8_000)
  })
})
