import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Store, Palette, Sparkles, CheckCircle2, ChevronRight, Rocket } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  isOnboardingSeen,
  markOnboardingSeen,
  useShopifyChannels,
  usePersonaFilled,
  useImageHistory,
} from './useOnboarding'

/**
 * OnboardingGuide - 新手三步激活引导（Dashboard 空状态主区块）
 *
 * 触发规则（满足其一就不再打扰）：
 *   1. localStorage 已有 veyaship_onboarded_seen 标记（跳过过）
 *   2. 已绑定 Shopify 店铺
 *   3. 图片历史中存在 completed 记录
 * 非强制阻断：右上角可随时「跳过」，引导卡仅占 Dashboard 一段，可关可滚。
 */
export default function OnboardingGuide() {
  const navigate = useNavigate()
  const [dismissed, setDismissed] = useState(false)

  // 真实信号：店铺 / 品牌调性 / 图片历史（失败即视为未完成，静默降级）
  const channels = useShopifyChannels()
  const persona = usePersonaFilled()
  const history = useImageHistory()

  const shopBound = !!channels.data && channels.data.length > 0
  const personaDone = persona.data === true
  const imageDone =
    !history.isError &&
    !!history.data &&
    history.data.some(
      (it) => it.status === 'completed' && Array.isArray(it.image_urls) && it.image_urls.length > 0,
    )

  // 首次挂载：等三个信号都落定再决定显隐，避免完成用户的引导闪烁
  const deciding = channels.isLoading || persona.isLoading || history.isLoading
  if (dismissed || deciding || shopBound || imageDone || isOnboardingSeen()) return null

  const steps = [
    {
      icon: Store,
      title: '绑定 Shopify 店铺',
      subtitle: '把店铺连进来，之后的商品上新、自动退款才有操作对象',
      path: '/app/shopify',
      cta: '去绑定',
      done: shopBound,
    },
    {
      icon: Palette,
      title: '设置品牌调性',
      subtitle: '告诉 AI 你的品牌风格与违禁词，生成的文案才像你亲手写的',
      path: '/app/settings',
      cta: '去设置',
      done: personaDone,
    },
    {
      icon: Sparkles,
      title: '生成第一张 AI 主图',
      subtitle: '用一句话描述商品，看到第一条产出，就验证了从想法到素材的整条链路',
      path: '/app/images',
      cta: '去生成',
      done: imageDone,
    },
  ]

  const doneCount = steps.filter((s) => s.done).length

  const handleSkip = () => {
    markOnboardingSeen()
    setDismissed(true)
  }

  return (
    <Card className="overflow-hidden">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <Rocket className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
              <CardTitle className="text-sm font-medium">
                跑通第一条商品链路
              </CardTitle>
            </div>
            <CardDescription className="mt-1 text-xs">
              连接店铺、设置品牌调性并生成第一张主图。
            </CardDescription>
          </div>
          <Button variant="ghost" size="sm" className="h-7 px-2 text-xs text-muted-foreground shrink-0" onClick={handleSkip}>
            跳过
          </Button>
        </div>
      </CardHeader>
      <CardContent className="p-0">
        <div className="flex items-center gap-3 border-y border-border px-5 py-2 text-xs text-muted-foreground">
          <span className="metric-number">已完成 {doneCount}/3</span>
          <span className="h-px flex-1 bg-border" />
        </div>

        {steps.map((step, index) => (
          <button
            key={step.path}
            type="button"
            onClick={!step.done ? () => navigate(step.path) : undefined}
            disabled={step.done}
            className={`flex w-full items-center gap-3 border-b border-border px-5 py-3 text-left last:border-b-0 ${
              step.done
                ? 'cursor-default'
                : 'hover:bg-accent'
            }`}
          >
            <span className="metric-number w-5 shrink-0 text-xs text-muted-foreground">
              {String(index + 1).padStart(2, '0')}
            </span>
            <span className="flex shrink-0 items-center justify-center">
              {step.done ? (
                <CheckCircle2 className="h-4 w-4 text-[var(--factory-mint)]" />
              ) : (
                <step.icon className="h-4 w-4 text-muted-foreground" />
              )}
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-[13px] font-medium">{step.title}</p>
              <p className="text-xs text-muted-foreground line-clamp-1">{step.subtitle}</p>
            </div>
            {step.done ? (
              <Badge variant="success" className="shrink-0">已完成</Badge>
            ) : (
              <span className="flex shrink-0 items-center gap-0.5 text-xs font-medium">
                {step.cta}
                <ChevronRight className="h-3.5 w-3.5" />
              </span>
            )}
          </button>
        ))}
      </CardContent>
    </Card>
  )
}
