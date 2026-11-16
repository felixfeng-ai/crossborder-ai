import { describe, expect, it } from 'vitest'

import {
  IMAGE_GENERATION_MODES,
  IMAGE_QUALITY_TIERS,
  buildImageGenerationRequest,
  effectiveImageGenerationMode,
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

  it('allows a text-only product scene but caps references at four', () => {
    expect(
      validateImageGeneration({
        mode: 'product_scene',
        prompt: '生成圣诞商品场景',
        referenceAssetIds: [],
        qualityTier: 'standard',
      }),
    ).toBe('')
    expect(
      validateImageGeneration({
        mode: 'product_scene',
        prompt: '保持商品一致，生成圣诞场景',
        referenceAssetIds: ['a', 'b'],
        qualityTier: 'standard',
      }),
    ).toBe('')
  })

  it('bills a text-only product scene at free-creation rates', () => {
    expect(effectiveImageGenerationMode('product_scene', 0)).toBe(
      'free_creation',
    )
    expect(imageGenerationCredits('product_scene', 'standard', 1, 0)).toBe(5)
    expect(imageGenerationCredits('product_scene', 'standard', 1, 1)).toBe(10)
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
    expect(IMAGE_QUALITY_TIERS.hd.resolution).toBe('1440x1440')
    expect(IMAGE_QUALITY_TIERS.hd.credits.free_creation).toBe(8)
  })

  it('keeps the direct Seedream provider in the request', () => {
    const request = buildImageGenerationRequest({
      mode: 'product_scene',
      prompt: '保持商品一致，生成冬季客厅',
      referenceAssetIds: ['asset-1'],
      qualityTier: 'standard',
      provider: 'seedream',
      idempotencyKey: 'request-seedream',
    })

    expect(request.provider).toBe('seedream')
    expect(request.reference_asset_ids).toEqual(['asset-1'])
  })

  it('allows direct Seedream for free creation without references', () => {
    const request = buildImageGenerationRequest({
      mode: 'free_creation',
      prompt: '黑白电影感女团海报',
      referenceAssetIds: ['ignored-asset'],
      qualityTier: 'standard',
      provider: 'seedream',
      idempotencyKey: 'request-seedream-free',
    })

    expect(request.provider).toBe('seedream')
    expect(request.reference_asset_ids).toEqual([])
  })
})
