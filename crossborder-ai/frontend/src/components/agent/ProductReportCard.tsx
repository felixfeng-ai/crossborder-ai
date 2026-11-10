import {
  BarChart3,
  Package,
  TrendingUp,
  ShoppingBag,
  Target,
  Flame,
  Sprout,
  Star,
  CheckCircle2,
  AlertTriangle,
  DollarSign,
  ExternalLink,
  type LucideIcon,
} from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import type { SelectionReport } from '@/types'

/**
 * ProductReportCard - Agent 品类/选品报告卡片
 *
 * 把后端 data.structured 渲染成生产级数据卡：
 * 市场指标 KPI 网格 → 候选商品列表 → 推荐结论横幅。
 * 字段缺失自动隐藏对应区块（LLM 输出容错）。
 */
export default function ProductReportCard({ report }: { report: SelectionReport }) {
  const market = report.market
  const products = report.products || []
  const rec = report.recommendation

  // LLM 字段漂移容错：reasons/risks/user_pains/risk_tips 可能是字符串而非数组
  const pains = asList(market?.user_pains)
  const reasons = asList(rec?.reasons)
  const risks = asList(rec?.risks)

  const hasMarket = market != null && Object.keys(market).length > 0
  const hasRec = rec != null && !!(rec.top_pick || rec.verdict || reasons.length || risks.length)

  return (
    <div className="space-y-2">
      {/* ── 市场指标 ─────────────────────────────────────── */}
      {hasMarket && (
        <Card className="bg-primary/5 border-primary/20">
          <CardHeader className="px-3 pt-3 pb-2">
            <CardTitle className="text-xs flex items-center gap-1.5">
              <BarChart3 className="h-3.5 w-3.5 text-primary" />
              市场指标
            </CardTitle>
          </CardHeader>
          <CardContent className="px-3 pb-3 pt-0">
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
              {market.monthly_search_volume != null && (
                <KpiStat icon={TrendingUp} label="月搜索量" value={formatNumber(market.monthly_search_volume)} />
              )}
              {market.active_listings != null && (
                <KpiStat icon={ShoppingBag} label="在售 Listing" value={formatNumber(market.active_listings)} />
              )}
              {market.avg_price_usd != null && (
                <KpiStat icon={DollarSign} label="平均售价" value={fmtUsd(market.avg_price_usd)} />
              )}
              {market.head_concentration != null && (
                <KpiStat icon={Target} label="头部集中度" value={formatPct(market.head_concentration)} />
              )}
              {market.competition_level != null && (
                <LevelStat label="竞争度" level={market.competition_level} color="amber" />
              )}
              {market.price_war_level != null && (
                <LevelStat label="价格战" level={market.price_war_level} color="red" />
              )}
              {market.new_product_survival_rate != null && (
                <KpiStat icon={Sprout} label="新品存活率" value={formatPct(market.new_product_survival_rate)} />
              )}
            </div>
            {pains.length > 0 && (
              <div className="mt-2 pt-2 border-t border-primary/10">
                <p className="text-[11px] text-muted-foreground mb-1">用户痛点</p>
                <div className="flex flex-wrap gap-1">
                  {pains.map((p, i) => (
                    <Badge key={i} variant="outline" className="text-[11px] font-normal">
                      {p}
                    </Badge>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* ── 候选商品 ─────────────────────────────────────── */}
      {products.length > 0 && (
        <Card>
          <CardHeader className="px-3 pt-3 pb-2">
            <CardTitle className="text-xs flex items-center gap-1.5">
              <Package className="h-3.5 w-3.5 text-primary" />
              候选商品
            </CardTitle>
          </CardHeader>
          <CardContent className="px-3 pb-3 pt-0">
            <div className="divide-y divide-border">
              {products.map((p, i) => (
                <div key={i} className="py-2 first:pt-0 last:pb-0">
                  <div className="flex flex-wrap items-start justify-between gap-1">
                    <ExternalProductLink
                      label={p.name}
                      url={p.url}
                      className="text-sm font-medium leading-snug"
                    />
                    <p className="text-sm font-semibold text-primary">{fmtUsd(p.suggested_price_usd)}</p>
                  </div>
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-1 text-xs text-muted-foreground">
                    {p.net_profit_usd != null && <span>单件净利 {fmtUsd(p.net_profit_usd)}</span>}
                    {p.net_margin != null && <span>净利率 {formatPct(p.net_margin)}</span>}
                    {p.cost_cny != null && <span>采购价 ¥{p.cost_cny}</span>}
                    {p.competition != null && (
                      <span className="inline-flex items-center gap-1">
                        竞争度 <Stars level={p.competition} />
                      </span>
                    )}
                  </div>
                  {asList(p.risk_tips).length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-1.5">
                      {asList(p.risk_tips).map((r, j) => (
                        <Badge key={j} variant="warning" className="text-[11px] font-normal">
                          {r}
                        </Badge>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* ── 推荐结论 ─────────────────────────────────────── */}
      {hasRec && (
        <Card className="bg-primary/10 border-primary/30">
          <CardHeader className="px-3 pt-3 pb-2">
            <CardTitle className="text-xs flex items-center gap-1.5">
              <CheckCircle2 className="h-3.5 w-3.5 text-primary" />
              推荐结论
            </CardTitle>
          </CardHeader>
          <CardContent className="px-3 pb-3 pt-0 space-y-2">
            {rec.top_pick && (
              <p className="text-sm font-bold text-primary">
                首选：<ExternalProductLink label={rec.top_pick} url={rec.url} />
              </p>
            )}
            {rec.verdict && <p className="text-sm">{rec.verdict}</p>}
            {rec.score != null && (
              <Badge variant="success" className="text-[11px]">
                综合评分 {rec.score}/10
              </Badge>
            )}
            {reasons.length > 0 && (
              <ul className="space-y-1">
                {reasons.map((r, i) => (
                  <li key={i} className="flex items-start gap-1.5 text-xs text-muted-foreground">
                    <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500 mt-0.5 shrink-0" />
                    {r}
                  </li>
                ))}
              </ul>
            )}
            {risks.length > 0 && (
              <ul className="space-y-1">
                {risks.map((r, i) => (
                  <li key={i} className="flex items-start gap-1.5 text-xs text-destructive">
                    <AlertTriangle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
                    {r}
                  </li>
                ))}
              </ul>
            )}
            {rec.entry_advice && <p className="text-xs text-muted-foreground">💡 {rec.entry_advice}</p>}
          </CardContent>
        </Card>
      )}
    </div>
  )
}

// ── 局部展示组件 ──────────────────────────────────────────────

function KpiStat({ icon: Icon, label, value }: { icon: LucideIcon; label: string; value: string }) {
  return (
    <div className="rounded-lg bg-background/60 border border-primary/10 p-2.5">
      <div className="flex items-center gap-1 text-[11px] text-muted-foreground">
        <Icon className="h-3 w-3" />
        {label}
      </div>
      <p className="text-base font-bold mt-0.5">{value}</p>
    </div>
  )
}

/** 5 格程度条（1-5），数据驱动配色：amber=竞争度、red=价格战 */
function LevelStat({ label, level, color }: { label: string; level: number; color: 'amber' | 'red' }) {
  const filled = color === 'red' ? 'bg-destructive' : 'bg-amber-500'
  return (
    <div className="rounded-lg bg-background/60 border border-primary/10 p-2.5">
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className="flex gap-0.5 mt-1.5">
        {[1, 2, 3, 4, 5].map((n) => (
          <span key={n} className={`h-1.5 flex-1 rounded-full ${n <= level ? filled : 'bg-muted'}`} />
        ))}
      </div>
    </div>
  )
}

/** 5 颗星（1-5），amber 填充，用于商品竞争度 */
function Stars({ level }: { level: number }) {
  return (
    <span className="inline-flex items-center gap-0.5">
      {[1, 2, 3, 4, 5].map((n) => (
        <Star
          key={n}
          className={`h-3 w-3 ${n <= level ? 'text-amber-500 fill-amber-500' : 'text-muted-foreground/30'}`}
        />
      ))}
    </span>
  )
}

// ── 格式化工具 ────────────────────────────────────────────────

/** 列表字段容错：LLM 可能返回 string（"a、b"）而非 string[]，统一归一化为数组 */
function asList<T>(v: T[] | string | null | undefined): T[] {
  return Array.isArray(v) ? v : []
}

function ExternalProductLink({
  label,
  url,
  className = '',
}: {
  label: string
  url?: string | null
  className?: string
}) {
  const safeUrl = normalizeExternalUrl(url)
  if (!safeUrl) return <span className={className}>{label}</span>

  return (
    <a
      href={safeUrl}
      target="_blank"
      rel="noopener noreferrer"
      title="在 Amazon 查看相关商品"
      className={`${className} inline-flex items-start gap-1 transition-colors hover:text-primary hover:underline underline-offset-4`}
    >
      <span>{label}</span>
      <ExternalLink className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
    </a>
  )
}

function normalizeExternalUrl(value?: string | null): string | null {
  if (!value) return null
  try {
    const parsed = new URL(value)
    return parsed.protocol === 'http:' || parsed.protocol === 'https:' ? parsed.toString() : null
  } catch {
    return null
  }
}

function formatNumber(n: number): string {
  if (n == null) return '-'
  if (n >= 10000) return `${(n / 10000).toFixed(1).replace(/\.0$/, '')}万`
  return String(n)
}

function formatPct(n: number): string {
  if (n == null) return '-'
  return `${n}%`
}

function fmtUsd(n: number | null | undefined): string {
  if (n == null) return '-'
  return `$${Number(n).toFixed(2)}`
}
