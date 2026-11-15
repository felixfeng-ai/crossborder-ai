import fs from 'node:fs'
import path from 'node:path'

import { describe, expect, it } from 'vitest'

function readSource(relativePath: string): string {
  return fs.readFileSync(path.resolve(process.cwd(), relativePath), 'utf8')
}

function sourceFiles(relativeDirectory: string): string[] {
  const root = path.resolve(process.cwd(), relativeDirectory)
  const result: string[] = []
  const walk = (directory: string) => {
    for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
      const absolute = path.join(directory, entry.name)
      if (entry.isDirectory()) {
        walk(absolute)
      } else if (/\.(tsx|css)$/.test(entry.name)) {
        result.push(absolute)
      }
    }
  }
  walk(root)
  return result
}

function luminance(hex: string): number {
  const channels = hex
    .replace('#', '')
    .match(/.{2}/g)!
    .map((value) => Number.parseInt(value, 16) / 255)
    .map((value) =>
      value <= 0.04045
        ? value / 12.92
        : ((value + 0.055) / 1.055) ** 2.4,
    )
  return channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722
}

function contrast(foreground: string, background: string): number {
  const lighter = Math.max(luminance(foreground), luminance(background))
  const darker = Math.min(luminance(foreground), luminance(background))
  return (lighter + 0.05) / (darker + 0.05)
}

function token(block: string, name: string): string {
  const match = block.match(new RegExp(`--${name}:\\s*(#[0-9a-fA-F]{6})`))
  if (!match) throw new Error(`Missing token: ${name}`)
  return match[1]
}

describe('三套主题的可读性契约', () => {
  it('主要、辅助、占位文字在各自背景上达到 WCAG AA', () => {
    const css = readSource('src/styles/globals.css')
    const root = css.slice(0, css.indexOf('html[data-theme="paper"]'))
    const paper = css.slice(
      css.indexOf('html[data-theme="paper"]'),
      css.indexOf('html[data-theme="harbor"]'),
    )
    const harbor = css.slice(css.indexOf('html[data-theme="harbor"]'))
    const themes = [
      ['graphite', root],
      ['paper', paper],
      ['harbor', harbor],
    ] as const

    for (const [name, block] of themes) {
      const ground = token(block, 'factory-ground')
      for (const role of ['factory-ink', 'factory-muted', 'factory-faint']) {
        expect(contrast(token(block, role), ground), `${name}:${role}`).toBeGreaterThanOrEqual(4.5)
      }
    }
  })

  it('AI 侧栏使用主题语义色而不是固定暗色', () => {
    const sidecar = readSource('src/components/agent/AgentSidecar.tsx')

    expect(sidecar).toContain('bg-[var(--factory-panel)]')
    expect(sidecar).toContain('text-[var(--factory-ink)]')
    expect(sidecar).not.toContain('bg-[#111411]')
    expect(sidecar).not.toContain('text-[#d8cfba]')
  })

  it('所有 factory 主题变量都有定义', () => {
    const files = sourceFiles('src')
    const source = files.map((file) => fs.readFileSync(file, 'utf8')).join('\n')
    const used = new Set(
      Array.from(source.matchAll(/var\((--factory-[a-z0-9-]+)/g), (match) => match[1]),
    )
    const defined = new Set(
      Array.from(source.matchAll(/(--factory-[a-z0-9-]+)\s*:/g), (match) => match[1]),
    )

    expect(Array.from(used).filter((name) => !defined.has(name)).sort()).toEqual([])
  })

  it('业务界面不使用固定状态色和固定图片占位底色', () => {
    const files = sourceFiles('src')
    const invalidFiles = files
      .filter((file) => {
        const source = fs.readFileSync(file, 'utf8')
        return (
          /text-(emerald|green|amber|orange|red|rose)-[0-9]{3}/.test(source) ||
          /bg-\[#d9dad5\]/.test(source)
        )
      })
      .map((file) => path.relative(process.cwd(), file))

    expect(invalidFiles.sort()).toEqual([])
  })

  it('业务界面元数据文字不小于 11px', () => {
    const excluded = new Set([
      path.resolve(process.cwd(), 'src/pages/landing/LandingPage.tsx'),
    ])
    const invalidFiles = sourceFiles('src')
      .filter((file) => !excluded.has(file))
      .filter((file) => /text-\[(9|10)px\]/.test(fs.readFileSync(file, 'utf8')))
      .map((file) => path.relative(process.cwd(), file))

    expect(invalidFiles.sort()).toEqual([])
  })

  it('账单图片预览使用专用深色遮罩保证白字可读', () => {
    const billing = readSource('src/pages/billing/BillingPage.tsx')

    expect(billing).toContain('data-billing-media-overlay')
    expect(billing).not.toContain('absolute inset-0 bg-black/20')
  })

  it('AI 助手悬浮按钮不遮挡移动端正文和操作区', () => {
    const rootLayout = readSource('src/components/layout/root-layout.tsx')

    expect(rootLayout).toContain('pb-28')
  })
})
