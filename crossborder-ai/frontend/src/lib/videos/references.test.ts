import { describe, expect, it } from 'vitest'
import {
  REFERENCE_ROLE_OPTIONS,
  buildReferenceAssetsPayload,
  toggleReferenceAsset,
} from './references'

describe('product reference selection', () => {
  it('toggles an asset without allowing more than nine total images', () => {
    const selected = Array.from({ length: 9 }, (_, index) => `asset-${index}`)

    expect(toggleReferenceAsset(selected, 'asset-0')).toEqual(
      selected.filter((assetId) => assetId !== 'asset-0'),
    )
    expect(toggleReferenceAsset(selected, 'asset-9')).toEqual(selected)
  })

  it('builds reference payload with primary first and stable role fallback', () => {
    const payload = buildReferenceAssetsPayload(
      'primary',
      ['primary', 'package', 'detail'],
      { package: 'package' },
    )

    expect(payload).toEqual([
      { asset_id: 'package', role: 'package' },
      { asset_id: 'detail', role: 'detail' },
    ])
    expect(REFERENCE_ROLE_OPTIONS.map((item) => item.value)).toContain('lifestyle')
  })
})
