import { describe, expect, it } from 'vitest'

import {
  IMAGE_EDIT_OPERATIONS,
  buildImageEditRequest,
  imageEditCredits,
  validateImageEdit,
} from './editing'

describe('image editing', () => {
  it('exposes the four supported edit operations', () => {
    expect(IMAGE_EDIT_OPERATIONS.map((item) => item.id)).toEqual([
      'inpaint',
      'outpaint',
      'remove_object',
      'upscale',
    ])
  })

  it('requires a mask for inpaint and object removal', () => {
    expect(
      validateImageEdit({
        operation: 'inpaint',
        sourceAssetId: 'source',
        maskAssetId: '',
        prompt: '替换桌面',
      }),
    ).toContain('蒙版')
    expect(
      validateImageEdit({
        operation: 'outpaint',
        sourceAssetId: 'source',
        maskAssetId: '',
        prompt: '向右侧扩展场景',
      }),
    ).toBe('')
  })

  it('uses operation-specific credits', () => {
    expect(imageEditCredits('upscale', 1)).toBe(2)
    expect(imageEditCredits('inpaint', 1)).toBe(6)
    expect(imageEditCredits('remove_object', 1)).toBe(5)
  })

  it('builds a durable edit request with scale and idempotency key', () => {
    const request = buildImageEditRequest({
      operation: 'upscale',
      sourceAssetId: 'source',
      maskAssetId: '',
      prompt: '',
      scale: 4,
      idempotencyKey: 'edit-request-1',
    })

    expect(request).toMatchObject({
      source_asset_id: 'source',
      operation: 'upscale',
      scale: 4,
      idempotency_key: 'edit-request-1',
    })
  })
})
