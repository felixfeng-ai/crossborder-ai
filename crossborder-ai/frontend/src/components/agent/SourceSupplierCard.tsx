import {
  ExternalLink,
  Factory,
  MapPin,
  PackageSearch,
  ShieldCheck,
} from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import RemoteImage from '@/components/common/RemoteImage'
import type {
  SourceSupplierItem,
  SourcingSearchReport,
} from '@/types'

/** 1688 货源候选卡：只展示公开线索和利润分析入口，不执行采购动作。 */
export default function SourceSupplierCard({
  report,
  onUseSource,
}: {
  report: SourcingSearchReport
  onUseSource: (source: SourceSupplierItem) => void
}) {
  const items = Array.isArray(report.items) ? report.items : []
  const searchMode = report.image_search_used ? '图片相似搜索' : '关键词搜索'
  const provider = providerLabel(report.provider)

  return (
    <div className="space-y-2">
      <Card>
        <CardHeader className="px-3 pt-3 pb-2">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <CardTitle className="flex items-center gap-1.5 text-xs">
              <PackageSearch className="h-3.5 w-3.5 text-primary" />
              1688 货源候选
            </CardTitle>
            <div className="flex flex-wrap gap-1">
              <Badge variant="outline">{searchMode}</Badge>
              <Badge variant="secondary">{provider}</Badge>
            </div>
          </div>
          <div className="space-y-0.5 text-[11px] text-muted-foreground">
            <p>
              搜索词：{report.keyword} · 共 {report.total_count ?? items.length}{' '}
              个结果
            </p>
            <p>观察时间：{formatObservedAt(report.observed_at)}</p>
          </div>
        </CardHeader>
        <CardContent className="space-y-2 px-3 pb-3 pt-0">
          {report.image_fallback_reason && (
            <p className="border border-amber-500/25 bg-amber-500/5 px-2.5 py-2 text-[11px] text-muted-foreground">
              {report.image_fallback_reason}
            </p>
          )}
          {report.provider_fallback_reason && (
            <p className="border border-border bg-muted/40 px-2.5 py-2 text-[11px] text-muted-foreground">
              {report.provider_fallback_reason}
            </p>
          )}
          {items.length === 0 ? (
            <div className="py-8 text-center text-xs text-muted-foreground">
              暂未找到可展示的 1688 货源，请调整采购关键词后重试。
            </div>
          ) : (
            items.map((item) => (
              <SupplierItem
                key={item.item_id}
                item={item}
                onUseSource={onUseSource}
              />
            ))
          )}
          {report.limitations.length > 0 && (
            <ul className="space-y-1 border-t border-border pt-2 text-[11px] leading-4 text-muted-foreground">
              {report.limitations.map((item) => (
                <li key={item}>· {item}</li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

function SupplierItem({
  item,
  onUseSource,
}: {
  item: SourceSupplierItem
  onUseSource: (source: SourceSupplierItem) => void
}) {
  return (
    <div className="border border-border bg-background p-2.5">
      <div className="flex gap-2.5">
        {item.image_url ? (
          <RemoteImage
            src={item.image_url}
            alt={item.title}
            className="h-[72px] w-[72px] shrink-0 border border-border object-cover"
            fallback={<ImagePlaceholder />}
          />
        ) : (
          <ImagePlaceholder />
        )}
        <div className="min-w-0 flex-1">
          <a
            href={item.url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-start gap-1 text-sm font-medium leading-snug hover:text-primary hover:underline underline-offset-4"
          >
            <span className="line-clamp-2">{item.title}</span>
            <ExternalLink className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          </a>
          {item.shop_name && (
            <p className="mt-1 truncate text-[11px] text-muted-foreground">
              {item.shop_name}
              {item.shop_years != null ? ` · ${item.shop_years} 年` : ''}
            </p>
          )}
          <div className="mt-1 flex flex-wrap gap-1">
            {item.is_factory && (
              <Badge variant="outline" className="gap-1 text-[11px] font-normal">
                <Factory className="h-3 w-3" />
                工厂
              </Badge>
            )}
            {item.factory_inspection && (
              <Badge variant="outline" className="gap-1 text-[11px] font-normal">
                <ShieldCheck className="h-3 w-3" />
                验厂
              </Badge>
            )}
            {item.location && (
              <Badge variant="secondary" className="gap-1 text-[11px] font-normal">
                <MapPin className="h-3 w-3" />
                {item.location}
              </Badge>
            )}
          </div>
        </div>
      </div>

      <div className="mt-2 grid grid-cols-3 gap-1 border-t border-border pt-2 text-[11px]">
        <Metric label="采购价" value={item.price || formatPrice(item)} />
        <Metric label="MOQ" value={item.moq != null ? String(item.moq) : '-'} />
        <Metric
          label="销量"
          value={
            item.sale_quantity != null
              ? item.sale_quantity.toLocaleString('zh-CN')
              : '-'
          }
        />
      </div>

      <Button
        type="button"
        size="sm"
        className="mt-2 h-11 w-full text-xs"
        onClick={() => onUseSource(item)}
      >
        用这个货源算利润
      </Button>
    </div>
  )
}

function ImagePlaceholder() {
  return (
    <div className="flex h-[72px] w-[72px] shrink-0 items-center justify-center border border-border bg-muted/40">
      <PackageSearch className="h-5 w-5 text-muted-foreground" />
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-muted-foreground">{label}</p>
      <p className="mt-0.5 truncate font-medium text-foreground">{value}</p>
    </div>
  )
}

function providerLabel(provider: string): string {
  if (provider === 'justone') return 'Just One'
  if (provider === 'onebound') return 'Onebound'
  return provider
}

function formatObservedAt(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(date)
}

function formatPrice(item: SourceSupplierItem): string {
  if (item.price_min_cny == null) return '-'
  if (
    item.price_max_cny != null &&
    item.price_max_cny !== item.price_min_cny
  ) {
    return `¥${item.price_min_cny} - ¥${item.price_max_cny}`
  }
  return `¥${item.price_min_cny}`
}
