import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

function readSource(relativePath: string): string {
  return fs.readFileSync(path.resolve(process.cwd(), relativePath), 'utf8')
}

describe('frontend performance contract', () => {
  it('lazy-loads every route and suspends while chunks load', () => {
    const app = readSource('src/App.tsx')

    expect(app).toContain('lazy(')
    expect(app).toContain('<Suspense')
    expect(app).toContain("import('@/pages/landing/LandingPage')")
    expect(app).toContain("import('@/pages/images/ImagesPage')")
    expect(app).not.toContain("import LandingPage from '@/pages/landing/LandingPage'")
    expect(app).not.toContain("import ImagesPage from '@/pages/images/ImagesPage'")
  })

  it('defers below-fold paint and lazy-loads the demo image', () => {
    const landing = readSource('src/pages/landing/LandingPage.tsx')

    expect(landing).toContain('loading="lazy"')
    expect(landing).toContain('decoding="async"')
    expect((landing.match(/deferred-section/g) || []).length).toBeGreaterThan(5)
  })

  it('serves an immediate static startup shell before React loads', () => {
    const html = readSource('index.html')

    expect(html).toContain('data-app-boot')
    expect(html).toContain('正在加载')
  })

  it('keeps public legal metadata separate from full legal documents', () => {
    const footer = readSource('src/components/legal/PublicLegalFooter.tsx')
    const legalMeta = readSource('src/lib/legalMeta.ts')

    expect(footer).toContain('@/lib/legalMeta')
    expect(footer).not.toContain("from '@/lib/legal'")
    expect(legalMeta).toContain('PUBLIC_LEGAL_LINKS')
    expect(legalMeta).not.toContain('LEGAL_DOCUMENTS')
  })

  it('caches fonts and demo assets separately while limiting streaming buffering to Agent APIs', () => {
    const nginx = readSource('../deploy/veyaship-hk/deploy-nginx.sh')

    expect(nginx).toContain('location /fonts/')
    expect(nginx).toContain('location /demo/')
    expect(nginx).toContain('location ^~ /api/v1/agent/')
    expect(nginx).toContain('location ^~ /api/')
    expect(nginx).toContain('proxy_ignore_headers Cache-Control Expires Set-Cookie;')
    expect(nginx).toContain('proxy_cache_valid      200 30s;')
    expect(nginx).toContain('proxy_buffering on;')
  })

  it('enforces an initial bundle budget after production builds', () => {
    const pkg = JSON.parse(readSource('package.json'))
    const budgetScript = readSource('scripts/check-bundle-size.mjs')

    expect(pkg.scripts['check:bundle']).toBe(
      'node scripts/check-bundle-size.mjs',
    )
    expect(budgetScript).toContain('MAX_INITIAL_GZIP_BYTES')
  })
})
