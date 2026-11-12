import { describe, expect, it } from 'vitest'

import {
  copyPlatformLabel,
  latestCopyByPlatform,
  type MarketingCopyAsset,
} from './marketingCopy'

function asset(
  id: string,
  platform: 'tiktok' | 'amazon' | 'shopify',
  variant: 'A' | 'B',
  batch: string,
  createdAt: string,
): MarketingCopyAsset {
  return {
    id,
    batch_id: batch,
    campaign_id: 'campaign-1',
    platform,
    variant_key: variant,
    language: 'en',
    headline: `${platform}-${variant}`,
    body: 'body',
    cta: 'cta',
    hashtags: [],
    keywords: [],
    metadata: {},
    status: 'ready',
    compliance_status: 'pass',
    violations: [],
    source: 'agent',
    model_used: 'deepseek',
    version: 1,
    created_at: createdAt,
    updated_at: createdAt,
  }
}

describe('marketing copy board helpers', () => {
  it('每个平台只展示最新批次并按 A/B 排序', () => {
    const items = [
      asset('old-a', 'tiktok', 'A', 'batch-old', '2026-11-12T01:00:00Z'),
      asset('old-b', 'tiktok', 'B', 'batch-old', '2026-11-12T01:00:00Z'),
      asset('new-b', 'tiktok', 'B', 'batch-new', '2026-11-13T01:00:00Z'),
      asset('new-a', 'tiktok', 'A', 'batch-new', '2026-11-13T01:00:00Z'),
      asset('amazon-a', 'amazon', 'A', 'batch-amazon', '2026-11-13T01:00:00Z'),
    ]

    const latest = latestCopyByPlatform(items)

    expect(latest.tiktok?.map((item) => item.id)).toEqual(['new-a', 'new-b'])
    expect(latest.amazon?.map((item) => item.id)).toEqual(['amazon-a'])
    expect(latest.shopify).toEqual([])
  })

  it('提供中文平台名称', () => {
    expect(copyPlatformLabel('tiktok')).toBe('TikTok')
    expect(copyPlatformLabel('amazon')).toBe('Amazon')
    expect(copyPlatformLabel('shopify')).toBe('Shopify')
  })
})
