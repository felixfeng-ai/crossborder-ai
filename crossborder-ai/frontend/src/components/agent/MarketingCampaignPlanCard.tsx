import {
  BarChart3,
  ListChecks,
  Megaphone,
  Route,
  ShieldAlert,
  Target,
  Users,
} from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

export interface MarketingCampaignPlan {
  title: string
  product_name: string
  objective: string
  platform: string
  market: string
  language: string
  audience: string
  positioning: string
  campaign_goal?: string
  value_props: string[]
  channel_plan: Array<{
    channel: string
    role: string
    formats: string[]
    cadence: string
  }>
  content_plan: Array<{
    stage: string
    assets: string[]
    message: string
  }>
  launch_steps: string[]
  metrics: string[]
  assumptions: string[]
}

/**
 * 营销活动方案卡。
 * 只呈现可执行策略与前提，不把完整 Markdown 塞进普通步骤文本。
 */
export function MarketingCampaignPlanCard({
  plan,
}: {
  plan: MarketingCampaignPlan
}) {
  return (
    <Card className="overflow-hidden border-[var(--factory-line)] bg-background">
      <CardHeader className="border-b border-border px-4 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline" className="gap-1 text-[11px] font-normal">
            <Megaphone className="h-3 w-3" />
            营销方案
          </Badge>
          <span className="text-xs text-muted-foreground">
            {plan.platform} · {plan.market}
          </span>
        </div>
        <CardTitle className="mt-2 text-base leading-6">{plan.title}</CardTitle>
      </CardHeader>

      <CardContent className="space-y-4 p-4">
        <section className="grid gap-3 sm:grid-cols-2">
          <div>
            <SectionTitle icon={Users} title="目标人群" />
            <p className="mt-1 text-xs leading-5 text-muted-foreground">
              {plan.audience}
            </p>
          </div>
          <div>
            <SectionTitle icon={Target} title="定位" />
            <p className="mt-1 text-xs leading-5 text-muted-foreground">
              {plan.positioning}
            </p>
          </div>
        </section>

        {plan.value_props.length > 0 && (
          <section className="border-t border-border pt-3">
            <SectionTitle icon={Megaphone} title="核心信息" />
            <ul className="mt-1.5 space-y-1">
              {plan.value_props.map((item) => (
                <li key={item} className="flex gap-2 text-xs leading-5">
                  <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-primary" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </section>
        )}

        {(plan.channel_plan.length > 0 || plan.content_plan.length > 0) && (
          <section className="border-t border-border pt-3">
            <SectionTitle icon={Route} title="渠道与内容" />
            <div className="mt-2 space-y-2">
              {plan.channel_plan.map((item) => (
                <div
                  key={`${item.channel}-${item.role}`}
                  className="border-l-2 border-primary/40 pl-3"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-xs font-medium">{item.channel}</span>
                    <span className="text-[11px] text-muted-foreground">
                      {item.cadence}
                    </span>
                  </div>
                  <p className="mt-1 text-xs leading-5 text-muted-foreground">
                    {item.role}
                    {item.formats.length > 0
                      ? ` · ${item.formats.join(' / ')}`
                      : ''}
                  </p>
                </div>
              ))}
              {plan.content_plan.map((item) => (
                <div
                  key={`${item.stage}-${item.message}`}
                  className="flex flex-wrap gap-x-2 text-xs leading-5"
                >
                  <span className="font-medium">{item.stage}</span>
                  <span className="text-muted-foreground">{item.message}</span>
                </div>
              ))}
            </div>
          </section>
        )}

        {plan.launch_steps.length > 0 && (
          <section className="border-t border-border pt-3">
            <SectionTitle icon={ListChecks} title="执行顺序" />
            <ol className="mt-1.5 space-y-1.5">
              {plan.launch_steps.map((item, index) => (
                <li key={item} className="flex gap-2 text-xs leading-5">
                  <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-secondary text-[11px] font-medium">
                    {index + 1}
                  </span>
                  <span>{item}</span>
                </li>
              ))}
            </ol>
          </section>
        )}

        {plan.metrics.length > 0 && (
          <section className="border-t border-border pt-3">
            <SectionTitle icon={BarChart3} title="衡量指标" />
            <div className="mt-2 flex flex-wrap gap-1.5">
              {plan.metrics.map((item) => (
                <Badge
                  key={item}
                  variant="outline"
                  className="text-[11px] font-normal"
                >
                  {item}
                </Badge>
              ))}
            </div>
          </section>
        )}

        {plan.assumptions.length > 0 && (
          <section className="border-t border-border pt-3">
            <SectionTitle icon={ShieldAlert} title="执行前提" />
            <p className="mt-1 text-[11px] leading-5 text-muted-foreground">
              {plan.assumptions.join('；')}
            </p>
          </section>
        )}
      </CardContent>
    </Card>
  )
}

function SectionTitle({
  icon: Icon,
  title,
}: {
  icon: typeof Users
  title: string
}) {
  return (
    <div className="flex items-center gap-1.5 text-xs font-medium">
      <Icon className="h-3.5 w-3.5 text-primary" aria-hidden="true" />
      {title}
    </div>
  )
}
