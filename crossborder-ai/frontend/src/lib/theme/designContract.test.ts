import fs from 'node:fs'
import path from 'node:path'

import { describe, expect, it } from 'vitest'

function readSource(relativePath: string): string {
  return fs.readFileSync(path.resolve(process.cwd(), relativePath), 'utf8')
}

describe('石墨决策台设计契约', () => {
  it('使用 drama-outline 同款字体事实', () => {
    const globals = readSource('src/styles/globals.css')

    expect(globals).toContain(
      '--font-cjk: "Noto Sans SC", "MiSans", "HarmonyOS Sans SC"',
    )
    expect(globals).toContain(
      '--font-ui: var(--font-latin), var(--font-cjk), sans-serif',
    )
    expect(globals).toContain('"JetBrains Mono"')
    expect(globals).not.toContain('Instrument Sans')
  })

  it('只保留石墨决策台主题并移除旧光效 token', () => {
    const globals = readSource('src/styles/globals.css')
    const themes = readSource('src/utils/themes.ts')

    expect(globals).toContain('--factory-ground: #0d0e0e')
    expect(globals).toContain('--factory-accent: #d8b56d')
    expect(globals).toContain('--factory-success: #8ebba7')
    expect(globals).toContain('--factory-danger: #d98b70')
    expect(globals).toContain('--font-data: var(--font-latin)')
    expect(globals).not.toContain('--aurora-a')
    expect(globals).not.toContain('--gradient-from')
    expect(themes).toContain("name: 'graphite'")
    expect(themes).not.toContain("name: 'ocean'")
    expect(themes).not.toContain("name: 'forest'")
  })

  it('应用外壳使用不透明石墨工作面', () => {
    const rootLayout = readSource('src/components/layout/root-layout.tsx')
    const sidebar = readSource('src/components/layout/sidebar.tsx')

    expect(rootLayout).toContain('data-app-shell="graphite-decision-desk"')
    expect(rootLayout).toContain('min-h-[100dvh]')
    expect(rootLayout).not.toContain('aurora-layer')
    expect(rootLayout).not.toContain('backdrop-blur')
    expect(sidebar).toContain('w-[232px]')
    expect(sidebar).not.toContain('bg-glass')
  })

  it('总览首屏以商品经营链路为主角', () => {
    const dashboard = readSource('src/pages/dashboard/DashboardPage.tsx')

    expect(dashboard).toContain('data-dashboard-protagonist="product-pipeline"')
    expect(dashboard).toContain('经营总览')
    expect(dashboard).toContain('pipeline?.stages')
    expect(dashboard).toContain('recent_operations')
    expect(dashboard).toContain('巡检详情')
    expect(dashboard).toContain('aria-expanded')
    expect(dashboard).not.toContain('👋')
    expect(dashboard).not.toContain('grid grid-cols-4 gap-3')
  })

  it('总览快捷动作不撑高主链路网格', () => {
    const dashboard = readSource('src/pages/dashboard/DashboardPage.tsx')
    const topGrid = dashboard.indexOf('data-dashboard-top-grid')
    const topGridEnd = dashboard.indexOf('</section>', topGrid)
    const onboarding = dashboard.indexOf('<OnboardingGuide />')
    const quickActions = dashboard.indexOf('data-dashboard-quick-actions')
    const analysis = dashboard.indexOf('AI 品类分析')

    expect(topGrid).toBeGreaterThan(-1)
    expect(topGridEnd).toBeGreaterThan(topGrid)
    expect(onboarding).toBeGreaterThan(topGridEnd)
    expect(quickActions).toBeGreaterThan(onboarding)
    expect(quickActions).toBeGreaterThan(topGrid)
    expect(analysis).toBeGreaterThan(quickActions)
    expect(dashboard).toContain('xl:grid-cols-5')
  })

  it('基础组件不再使用渐变、玻璃和悬浮卡片', () => {
    const button = readSource('src/components/ui/button.tsx')
    const card = readSource('src/components/ui/card.tsx')

    expect(button).not.toContain('bg-gradient-to-br')
    expect(button).toContain('bg-primary text-primary-foreground')
    expect(card).not.toContain('backdrop-blur')
    expect(card).not.toContain('rounded-2xl')
    expect(card).toContain('rounded-lg')
  })

  it('登录与注册页共享 AI 跨境决策分屏', () => {
    const login = readSource('src/pages/auth/LoginPage.tsx')
    const register = readSource('src/pages/auth/RegisterPage.tsx')
    const authLayoutPath = path.resolve(
      process.cwd(),
      'src/components/auth/AuthLayout.tsx',
    )
    const authLayout = fs.existsSync(authLayoutPath)
      ? fs.readFileSync(authLayoutPath, 'utf8')
      : ''

    expect(login).toContain('<AuthLayout')
    expect(register).toContain('<AuthLayout')
    expect(authLayout).toContain('data-auth-layout="graphite-ai-decision"')
    expect(authLayout).toContain('从选品判断到真正上架')
    expect(authLayout).toContain('让 AI 把整条链路跑完')
    expect(authLayout).toContain('AI Agent 执行链')
    expect(authLayout).toContain('对话即操作')
    expect(authLayout).toContain('合规即闭环')
    expect(authLayout).toContain('卖家零配置')
  })
})
