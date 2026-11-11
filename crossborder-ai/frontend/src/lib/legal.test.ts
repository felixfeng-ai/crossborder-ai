import fs from 'node:fs'
import path from 'node:path'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { StaticRouter } from 'react-router-dom/server'
import { describe, expect, it } from 'vitest'

import LegalConsent from '@/components/legal/LegalConsent'
import PublicLegalFooter from '@/components/legal/PublicLegalFooter'
import LegalDocumentPage from '@/pages/legal/LegalPage'
import {
  LEGAL_CONTACT_EMAIL,
  LEGAL_DOCUMENTS,
  PUBLIC_LEGAL_LINKS,
  getLegalDocument,
} from './legal'

function readSource(relativePath: string): string {
  return fs.readFileSync(path.resolve(process.cwd(), relativePath), 'utf8')
}

describe('公网法务与合规页面', () => {
  it('提供审核所需的七个独立公网地址', () => {
    expect(LEGAL_DOCUMENTS.map((document) => document.path)).toEqual([
      '/terms',
      '/privacy',
      '/data-processing',
      '/ai-disclosure',
      '/security',
      '/report',
      '/contact',
    ])

    for (const document of LEGAL_DOCUMENTS) {
      expect(document.version).toMatch(/^\d+\.\d+$/)
      expect(document.effectiveDate).toMatch(/^2026-/)
      expect(document.sections.length).toBeGreaterThanOrEqual(4)
      expect(document.sections.every((section) => section.title.length > 0)).toBe(true)
    }
  })

  it('隐私与数据处理说明覆盖 Shopify、AI、删除和安全边界', () => {
    const privacy = getLegalDocument('/privacy')
    const dataProcessing = getLegalDocument('/data-processing')
    const aiDisclosure = getLegalDocument('/ai-disclosure')
    const security = getLegalDocument('/security')
    const combined = JSON.stringify({ privacy, dataProcessing, aiDisclosure, security })

    expect(combined).toContain('Shopify')
    expect(combined).toContain('客户姓名')
    expect(combined).toContain('邮箱')
    expect(combined).toContain('电话')
    expect(combined).toContain('地址')
    expect(combined).toContain('AI')
    expect(combined).toContain('人工复核')
    expect(combined).toContain('删除')
    expect(combined).toContain('安全事件')
    expect(combined).toContain(LEGAL_CONTACT_EMAIL)
    expect(combined).toContain('90 天')
    expect(combined).toContain('180 天')
    expect(combined).toContain('customers/data_request')
    expect(combined).toContain('customers/redact')
    expect(combined).toContain('shop/redact')
  })

  it('公开展示个人经营者身份且只提供联系邮箱', () => {
    const combined = JSON.stringify(LEGAL_DOCUMENTS)
    const contact = getLegalDocument('/contact')
    const contactText = JSON.stringify(contact)

    expect(combined).toContain('冯斯远')
    expect(combined).toContain('个人经营者')
    expect(contactText).toContain(LEGAL_CONTACT_EMAIL)
    expect(contactText).not.toContain('宝安区')
    expect(contactText).not.toContain('瓦窑花园')
    expect(contactText).not.toContain('宝能公寓')
  })

  it('法务正文在桌面和移动端包含标题、目录与可读结构', () => {
    const markup = renderToStaticMarkup(
      createElement(
        StaticRouter,
        { location: '/privacy' },
        createElement(LegalDocumentPage, { document: getLegalDocument('/privacy') }),
      ),
    )

    expect(markup).toContain('<main')
    expect(markup).toContain('data-legal-document="privacy"')
    expect(markup).toContain('隐私政策')
    expect(markup).toContain('aria-label="法务目录"')
    expect(markup).toContain('id="section-')
    expect(markup).toContain('返回首页')
  })

  it('登录与注册告知提供可点击的服务条款和隐私政策链接', () => {
    const markup = renderToStaticMarkup(
      createElement(StaticRouter, { location: '/' }, createElement(LegalConsent, { mode: 'login' })),
    )
    const login = readSource('src/pages/auth/LoginPage.tsx')
    const register = readSource('src/pages/auth/RegisterPage.tsx')

    expect(markup).toContain('href="/terms"')
    expect(markup).toContain('href="/privacy"')
    expect(markup).toContain('服务条款')
    expect(markup).toContain('隐私政策')
    expect(login).toContain('<LegalConsent')
    expect(register).toContain('<LegalConsent')
  })

  it('公开页脚与首页复用同一组法务入口', () => {
    const markup = renderToStaticMarkup(
      createElement(StaticRouter, { location: '/' }, createElement(PublicLegalFooter)),
    )
    const landing = readSource('src/pages/landing/LandingPage.tsx')
    const app = readSource('src/App.tsx')

    expect(PUBLIC_LEGAL_LINKS.map((link) => link.path)).toEqual([
      '/terms',
      '/privacy',
      '/data-processing',
      '/ai-disclosure',
      '/security',
      '/report',
      '/contact',
    ])
    for (const link of PUBLIC_LEGAL_LINKS) {
      expect(markup).toContain(`href="${link.path}"`)
    }
    expect(landing).toContain('<PublicLegalFooter')
    expect(app).toContain('LEGAL_DOCUMENTS.map')
    expect(app).toContain('<LegalDocumentPage')
  })
})
