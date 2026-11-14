import { motion } from 'framer-motion'
import { useNavigate } from 'react-router-dom'
import {
  ArrowRight,
  BookOpenText,
  Bot,
  CheckCircle2,
  CircleDollarSign,
  Images,
  ListChecks,
  Package,
  Rocket,
  Store,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  TUTORIAL_QUICK_LINKS,
  TUTORIAL_SHORTCUTS,
  TUTORIAL_STEPS,
  type TutorialStepId,
} from '@/lib/tutorial/content'

const STEP_ICONS: Record<TutorialStepId, typeof Package> = {
  product: Package,
  assistant: Bot,
  listing: ListChecks,
  media: Images,
  publish: Store,
  account: CircleDollarSign,
}

export default function TutorialPage() {
  const navigate = useNavigate()

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      className="mx-auto max-w-6xl space-y-8"
      data-tutorial-page="true"
    >
      <header className="border-b border-border pb-8">
        <div className="flex items-center gap-2 text-xs font-medium text-[var(--factory-accent)]">
          <BookOpenText className="h-4 w-4" />
          Getting started · 6 steps
        </div>
        <h1 className="page-title mt-3">VeyaShip 使用教程</h1>
        <p className="mt-3 max-w-3xl text-sm leading-7 text-muted-foreground">
          从商品事实开始，依次完成 AI 判断、Listing 与合规、图片视频、素材沉淀和渠道发布。
          右下角“问 AI”会在任何页面跟随当前任务提供帮助。
        </p>
        <div className="mt-6 flex flex-wrap gap-2">
          <Button onClick={() => navigate('/app/products')} className="h-10 gap-2">
            <Rocket className="h-4 w-4" />
            从商品开始
          </Button>
          <Button
            variant="outline"
            onClick={() => navigate('/app/agent')}
            className="h-10 gap-2"
          >
            <Bot className="h-4 w-4" />
            打开 AI 决策助手
          </Button>
        </div>
      </header>

      <section aria-labelledby="tutorial-quick-start">
        <div className="mb-3 flex items-end justify-between gap-4">
          <div>
            <h2 id="tutorial-quick-start" className="section-title">
              快捷开始
            </h2>
            <p className="mt-1 text-xs text-muted-foreground">
              不确定从哪里开始时，直接进入最常用的工作台。
            </p>
          </div>
          <span className="hidden text-[10px] text-[var(--factory-faint)] sm:block">
            QUICK START / 04
          </span>
        </div>
        <div className="grid border border-border sm:grid-cols-2 lg:grid-cols-4">
          {TUTORIAL_QUICK_LINKS.map((item, index) => (
            <button
              key={item.path}
              type="button"
              onClick={() => navigate(item.path)}
              className="group flex min-h-28 flex-col justify-between border-b border-border p-4 text-left transition-colors hover:bg-accent/60 sm:odd:border-r lg:border-b-0 lg:border-r lg:last:border-r-0"
            >
              <div className="flex items-center justify-between gap-3">
                <span className="font-mono text-[10px] text-[var(--factory-faint)]">
                  {String(index + 1).padStart(2, '0')}
                </span>
                <ArrowRight className="h-4 w-4 text-[var(--factory-faint)] transition-transform group-hover:translate-x-0.5 group-hover:text-[var(--factory-accent)]" />
              </div>
              <div className="mt-4">
                <p className="text-sm font-medium">{item.label}</p>
                <p className="mt-1 text-xs leading-5 text-muted-foreground">
                  {item.description}
                </p>
              </div>
            </button>
          ))}
        </div>
      </section>

      <div className="grid gap-8 lg:grid-cols-[220px_minmax(0,1fr)]">
        <aside className="lg:sticky lg:top-6 lg:self-start">
          <div className="border border-border bg-[var(--factory-panel)] p-4">
            <p className="text-[11px] font-medium text-muted-foreground">本页目录</p>
            <nav className="mt-3 space-y-1" aria-label="教程目录">
              {TUTORIAL_STEPS.map((step) => (
                <a
                  key={step.id}
                  href={`#tutorial-${step.id}`}
                  className="flex min-h-9 items-center gap-2 border-l border-border px-3 text-xs text-muted-foreground transition-colors hover:border-[var(--factory-accent)] hover:bg-accent/60 hover:text-foreground"
                >
                  <span className="font-mono text-[9px] text-[var(--factory-faint)]">
                    {step.step}
                  </span>
                  {step.title}
                </a>
              ))}
            </nav>
          </div>

          <div className="mt-3 border border-border bg-[var(--factory-panel)] p-4">
            <p className="text-[11px] font-medium text-muted-foreground">快捷操作</p>
            <div className="mt-3 space-y-3">
              {TUTORIAL_SHORTCUTS.map((shortcut) => (
                <div key={shortcut.keys}>
                  <kbd className="inline-flex min-h-7 items-center border border-[var(--factory-line-strong)] bg-[var(--factory-ground)] px-2 font-mono text-[10px] text-foreground">
                    {shortcut.keys}
                  </kbd>
                  <p className="mt-1.5 text-[11px] leading-5 text-muted-foreground">
                    {shortcut.description}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </aside>

        <div>
          {TUTORIAL_STEPS.map((step, index) => {
            const Icon = STEP_ICONS[step.id]
            return (
              <section
                key={step.id}
                id={`tutorial-${step.id}`}
                className="scroll-mt-24 border-t border-border py-8 first:border-t-0 first:pt-0"
              >
                <div className="grid gap-5 sm:grid-cols-[54px_minmax(0,1fr)]">
                  <div>
                    <span className="font-mono text-xs text-[var(--factory-accent)]">
                      {step.step}
                    </span>
                    <div className="mt-3 flex h-9 w-9 items-center justify-center border border-[var(--factory-line-strong)] bg-[var(--factory-panel)]">
                      <Icon className="h-[18px] w-[18px] text-[var(--factory-accent)]" />
                    </div>
                  </div>

                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-3">
                      <h2 className="text-xl font-semibold leading-8">{step.title}</h2>
                      <span className="font-mono text-[10px] text-[var(--factory-faint)]">
                        STEP {index + 1} / {TUTORIAL_STEPS.length}
                      </span>
                    </div>
                    <p className="mt-2 max-w-3xl text-sm leading-7 text-muted-foreground">
                      {step.summary}
                    </p>

                    <ul className="mt-4 space-y-2.5">
                      {step.outcomes.map((outcome) => (
                        <li
                          key={outcome}
                          className="flex items-start gap-2.5 text-[13px] leading-6 text-[var(--factory-muted)]"
                        >
                          <CheckCircle2 className="mt-1 h-4 w-4 shrink-0 text-[var(--factory-mint)]" />
                          <span>{outcome}</span>
                        </li>
                      ))}
                    </ul>

                    <div className="mt-5 flex flex-wrap gap-2">
                      {step.actions.map((action, actionIndex) => (
                        <Button
                          key={action.path}
                          variant={actionIndex === 0 ? 'default' : 'outline'}
                          onClick={() => navigate(action.path)}
                          className="h-10 gap-2"
                          title={action.description}
                        >
                          {action.label}
                          <ArrowRight className="h-3.5 w-3.5" />
                        </Button>
                      ))}
                    </div>
                  </div>
                </div>
              </section>
            )
          })}
        </div>
      </div>
    </motion.div>
  )
}
