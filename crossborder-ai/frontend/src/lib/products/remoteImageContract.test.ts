import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

function readSource(relativePath: string): string {
  return fs.readFileSync(path.resolve(process.cwd(), relativePath), 'utf8')
}

describe('remote product image contract', () => {
  it('disables referer headers and handles image failures', () => {
    const image = readSource('src/components/common/RemoteImage.tsx')

    expect(image).toContain('referrerPolicy="no-referrer"')
    expect(image).toContain('onError')
    expect(image).toContain('setFailed(true)')
    expect(image).toContain('resolveMediaUrl(src)')
  })

  it('uses the protected image component on product-facing pages', () => {
    const products = readSource('src/pages/products/ProductsPage.tsx')
    const detail = readSource('src/pages/products/ProductDetailPage.tsx')
    const radar = readSource('src/pages/radar/RadarPage.tsx')
    const content = readSource('src/pages/content/ContentPage.tsx')

    expect(products).toContain('<RemoteImage')
    expect(detail).toContain('<RemoteImage')
    expect(radar).toContain('<RemoteImage')
    expect(content).toContain('<RemoteImage')
  })
})
