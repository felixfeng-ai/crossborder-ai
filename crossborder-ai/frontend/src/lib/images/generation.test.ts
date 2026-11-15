import { describe, expect, it } from 'vitest'

import {
  IMAGE_GENERATION_MODES,
  IMAGE_QUALITY_TIERS,
  buildImageGenerationRequest,
  imageGenerationCredits,
  validateImageGeneration,
} from './generation'

describe('image generation modes', () => {
  it('exposes product scene and free creation modes', () => {
    expect(IMAGE_GENERATION_MODES.map((item) => item.id)).toEqual(
      expect.arrayContaining(['product_scene', 'free_creation']),
    )
  })

  it('uses explicit quality credit tiers', () => {
    expect(imageGenerationCredits('free_creation', 'fast', 1)).toBe(3)
    expect(imageGenerationCredits('free_creation', 'hd', 2)).toBe(16)
    expect(imageGenerationCredits('product_scene', 'hd', 1)).toBe(12)
  })

  it('requires one to four product references in product scene mode', () => {
    expect(
      validateImageGeneration({
        mode: 'product_scene',
        prompt: '保持商品一致，生成圣诞场景',
        referenceAssetIds: [],
        qualityTier: 'standard',
      }),
    ).toContain('参考图')
    expect(
      validateImageGeneration({
        mode: 'product_scene',
        prompt: '保持商品一致，生成圣诞场景',
        referenceAssetIds: ['a', 'b'],
        qualityTier: 'standard',
      }),
    ).toBe('')
  })

  it('allows local platform white processing without an AI prompt', () => {
    expect(
      validateImageGeneration({
        mode: 'platform_white',
        prompt: '',
        referenceAssetIds: ['asset-1'],
        qualityTier: 'fast',
      }),
    ).toBe('')
  })

  it('disables brand persona by default for free creation', () => {
    const request = buildImageGenerationRequest({
      mode: 'free_creation',
      prompt: '黑白电影感抽象海报',
      referenceAssetIds: [],
      qualityTier: 'fast',
    })
    expect(request.use_brand_persona).toBe(false)
  })

  it('keeps quality and ratio available to the request', () => {
    const request = buildImageGenerationRequest({
      mode: 'product_scene',
      prompt: '商品放入暖色节日客厅',
      referenceAssetIds: ['asset-1'],
      qualityTier: 'hd',
      aspectRatio: '4:5',
      negativePrompt: '变形、错误 logo',
      idempotencyKey: 'request-1',
    })
    expect(request.quality_tier).toBe('hd')
    expect(request.aspect_ratio).toBe('4:5')
    expect(request.negative_prompt).toContain('logo')
    expect(request.idempotency_key).toBe('request-1')
    expect(IMAGE_QUALITY_TIERS.hd.credits.free_creation).toBe(8)
  })
})
