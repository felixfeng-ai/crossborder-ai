import type { ReactNode } from 'react'
import { Globe } from 'lucide-react'
import { Link } from 'react-router-dom'

const decisionStages = [
  {
    index: '01',
    title: 'AI 选品决策',
    detail: '市场 · 竞争 · 机会',
  },
  {
    index: '02',
    title: '利润测算',
    detail: '成本 · 运费 · 佣金',
  },
  {
    index: '03',
    title: 'AI Listing',
    detail: '标题 · 五点 · SEO',
    active: true,
  },
  {
    index: '04',
    title: '合规检查',
    detail: '违禁词 · 平台规则',
  },
  {
    index: '05',
    title: '上架与巡检',
    detail: 'Shopify · 每日检查',
  },
]

const brandPillars = ['对话即操作', '合规即闭环', '卖家零配置']

/**
 * 登录与注册共用的 AI 跨境决策分屏。
 *
 * 左侧只承担品牌理解和产品证据，右侧由具体页面承载登录或注册任务。
 * 移动端移除执行链，保留品牌主张和完整表单，避免氛围压过登录操作。
 */
export function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <main
      data-auth-layout="graphite-ai-decision"
      className="grid min-h-[100dvh] bg-background text-foreground lg:grid-cols-[minmax(0,1.16fr)_minmax(420px,0.84fr)]"
    >
      <section
        aria-label="VeyaShip AI 跨境决策能力"
        className="relative flex min-w-0 flex-col overflow-hidden border-b border-border bg-[var(--factory-side)] px-5 py-6 sm:px-8 lg:border-b-0 lg:border-r lg:px-[clamp(32px,5vw,78px)] lg:py-9"
      >
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-y-0 right-[10%] hidden w-px bg-[rgba(243,242,237,0.035)] lg:block"
        />

        <Link
          to="/"
          className="relative z-10 inline-flex w-fit items-center gap-2.5"
          aria-label="返回 VeyaShip 首页"
        >
          <span className="flex h-[30px] w-[30px] items-center justify-center rounded-[5px] border border-[var(--factory-line-strong)] bg-[var(--factory-panel)]">
            <Globe className="h-[17px] w-[17px]" aria-hidden="true" />
          </span>
          <span>
            <span className="block font-latin text-[15px] font-semibold leading-4">
              VeyaShip
            </span>
            <span className="mt-1 block text-[11px] leading-4 text-muted-foreground">
              AI 跨境决策引擎
            </span>
          </span>
        </Link>

        <div className="relative z-10 mt-10 w-full max-w-[660px] lg:mt-[clamp(82px,12vh,142px)]">
          <div className="flex items-center gap-2.5 text-xs leading-[18px] text-muted-foreground">
            <span className="h-px w-6 bg-[var(--factory-accent)]" aria-hidden="true" />
            AI Agent · 跨境决策与执行
          </div>

          <h2 className="mt-4 max-w-[620px] text-[30px] font-semibold leading-[1.3] sm:text-[38px] lg:text-[clamp(36px,3.6vw,56px)] lg:leading-[1.2]">
            从选品判断到真正上架，
            <br />
            让 AI 把整条链路跑完。
          </h2>

          <p className="mt-5 hidden max-w-[520px] text-sm leading-7 text-muted-foreground sm:block">
            说一句话，AI Agent 自动完成品类分析、利润测算、Listing、合规检查与店铺巡检。
          </p>
        </div>

        <div
          data-auth-agent-pipeline
          className="relative z-10 mt-10 hidden w-full max-w-[680px] border-y border-[var(--factory-line-strong)] md:block lg:mt-[clamp(50px,8vh,88px)]"
        >
          <div className="flex min-h-[42px] items-center justify-between gap-4 text-[11px] text-[var(--factory-faint)]">
            <span>AI Agent 执行链</span>
            <span className="font-mono text-[var(--factory-accent)]">
              DECIDE → GENERATE → PUBLISH
            </span>
          </div>

          <div className="grid grid-cols-5 border-t border-border">
            {decisionStages.map((stage, index) => (
              <div
                key={stage.title}
                className={`min-w-0 border-border px-3 py-4 ${
                  index < decisionStages.length - 1 ? 'border-r' : ''
                } ${stage.active ? 'bg-[var(--factory-panel)]' : ''}`}
              >
                <span
                  className={`font-mono text-[11px] leading-none ${
                    stage.active
                      ? 'text-[var(--factory-accent)]'
                      : 'text-[var(--factory-faint)]'
                  }`}
                >
                  {stage.index}
                </span>
                <strong className="mt-3 block whitespace-nowrap text-xs font-medium leading-[18px]">
                  {stage.title}
                </strong>
                <span
                  className={`mt-1 block truncate text-[11px] leading-4 ${
                    stage.active
                      ? 'text-[var(--factory-accent)]'
                      : 'text-[var(--factory-faint)]'
                  }`}
                >
                  {stage.detail}
                </span>
              </div>
            ))}
          </div>
        </div>

        <div className="relative z-10 mt-auto hidden flex-wrap items-center gap-x-4 gap-y-2 pt-8 text-[11px] text-[var(--factory-faint)] md:flex">
          <span className="h-[5px] w-[5px] rounded-full bg-[var(--factory-accent)]" />
          {brandPillars.map((pillar) => (
            <span key={pillar}>{pillar}</span>
          ))}
          <span className="ml-auto font-mono text-muted-foreground">
            AGENT / COMPLIANCE / ZERO CONFIG
          </span>
        </div>
      </section>

      <section className="flex min-h-[calc(100dvh-220px)] items-start justify-center bg-background px-5 py-9 sm:px-8 lg:min-h-0 lg:items-center lg:px-12 xl:px-16">
        <div className="w-full max-w-[380px]">{children}</div>
      </section>
    </main>
  )
}
