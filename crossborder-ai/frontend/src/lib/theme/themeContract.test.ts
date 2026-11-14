import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

function readSource(relativePath: string): string {
  return fs.readFileSync(path.resolve(process.cwd(), relativePath), 'utf8')
}

describe('多主题与首页结构契约', () => {
  it('主题模块包含四个允许选择值和石墨默认值', () => {
    const themes = readSource('src/utils/themes.ts')

    expect(themes).toContain("'graphite'")
    expect(themes).toContain("'paper'")
    expect(themes).toContain("'harbor'")
    expect(themes).toContain("'system'")
    expect(themes).toContain("DEFAULT_THEME_MODE = 'graphite'")
    expect(themes).toContain("classList.toggle('dark'")
  })

  it('CSS 为白色和海港主题提供语义覆盖', () => {
    const css = readSource('src/styles/globals.css')

    expect(css).toContain('[data-theme="paper"]')
    expect(css).toContain('[data-theme="harbor"]')
    expect(css).toContain('color-scheme: light')
  })

  it('语言按钮旁提供主题菜单', () => {
    const header = readSource('src/components/layout/header.tsx')
    const switcher = readSource('src/components/theme/ThemeSwitcher.tsx')
    const themes = readSource('src/utils/themes.ts')

    expect(header).toContain('<ThemeSwitcher')
    expect(switcher).toContain('THEME_OPTIONS')
    expect(themes).toContain('石墨琥珀')
    expect(themes).toContain('纯白纸张')
    expect(themes).toContain('海港青')
    expect(themes).toContain('跟随系统')
    expect(switcher).toContain('aria-label')
  })

  it('首屏启动脚本在 React 前应用保存主题', () => {
    const html = readSource('index.html')

    expect(html).toContain('veya-theme')
    expect(html).toContain('dataset.theme')
    expect(html).toContain("'graphite'")
  })

  it('首页使用真实决策摘要并把平台支持移出首屏', () => {
    const landing = readSource('src/pages/landing/LandingPage.tsx')
    const platforms = readSource('src/components/landing/LandingPlatformStrip.tsx')

    expect(landing).toContain('data-landing-hero')
    expect(platforms).toContain('data-landing-platforms')
    expect(platforms).toContain('SUPPORTED_COPY_PLATFORMS.map')
    expect(landing).not.toContain('LANDING_PIPELINE')
    expect(landing).not.toContain('SUPPORTED_COPY_PLATFORMS.map')
  })
})
