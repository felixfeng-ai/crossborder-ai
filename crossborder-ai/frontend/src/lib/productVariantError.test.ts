import { describe, expect, it } from 'vitest'

import { variantSaveErrorMessage } from './productVariantError'


describe('variantSaveErrorMessage', () => {
  it('shows the readable backend message', () => {
    const error = {
      response: {
        status: 409,
        data: { detail: '该 SKU 已存在' },
      },
    }

    expect(variantSaveErrorMessage(error)).toBe('该 SKU 已存在')
  })

  it('uses a stable fallback for unknown errors', () => {
    expect(variantSaveErrorMessage(new Error('Request failed with status code 500'))).toBe(
      '保存变体失败，请稍后重试',
    )
  })
})
