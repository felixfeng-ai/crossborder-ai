import { describe, expect, it } from 'vitest'

import { createIdempotencyKey } from './idempotency'

describe('createIdempotencyKey', () => {
  it('生成非空且不重复的幂等键', () => {
    const first = createIdempotencyKey()
    const second = createIdempotencyKey()
    expect(first.length).toBeGreaterThan(8)
    expect(second.length).toBeGreaterThan(8)
    expect(first).not.toBe(second)
  })
})
