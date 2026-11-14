import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ArrowUpRight, RefreshCw } from 'lucide-react'
import { Link } from 'react-router-dom'

import apiClient from '@/api/client'
import {
  AdminError,
  AdminLoading,
  AdminPageHeader,
  AdminPanel,
  formatMoney,
  formatNumber,
} from './AdminPrimitives'
import type { AdminOverview } from './adminTypes'

function TrendChart({ rows }: { rows: AdminOverview['traffic']['daily'] }) {
  const width = 720
  const height = 190
  const max = Math.max(1, ...rows.map((row) => row.pv))
  const coordinates = rows.map((row, index) => {
    const x = rows.length <= 1 ? 0 : (index / (rows.length - 1)) * width
    const y = height - (row.pv / max) * (height - 20)
    return { x, y, pv: row.pv }
  })
  const points = coordinates.map((point) => `${point.x},${point.y}`)
  return (
    <div className="px-4 pb-4 pt-5">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="h-[190px] w-full"
        role="img"
        aria-label="页面访问趋势"
      >
        {[0.25, 0.5, 0.75, 1].map((ratio) => (
          <line
            key={ratio}
            x1="0"
            x2={width}
            y1={height - ratio * (height - 20)}
            y2={height - ratio * (height - 20)}
            stroke="var(--factory-line)"
            strokeWidth="1"
          />
        ))}
        {rows.length === 0 ? (
          <line
            x1="0"
            x2={width}
            y1={height}
            y2={height}
            stroke="var(--factory-faint)"
            strokeWidth="1"
          />
        ) : (
          <>
            <polyline
              points={points.join(' ')}
              fill="none"
              stroke="var(--factory-accent)"
              strokeWidth="2"
              strokeLinejoin="round"
              strokeLinecap="round"
            />
            {coordinates.length === 1 && (
              <>
                <circle
                  cx={coordinates[0].x + 4}
                  cy={coordinates[0].y}
                  r="5"
                  fill="var(--factory-accent)"
                />
                <text
                  x={coordinates[0].x + 16}
                  y={Math.max(14, coordinates[0].y - 12)}
                  fill="var(--factory-ink)"
                  fontSize="12"
                >
                  {coordinates[0].pv} PV
                </text>
              </>
            )}
          </>
        )}
      </svg>
      <div className="flex items-center justify-between text-[11px] text-muted-foreground">
        <span>{rows[0]?.date || '暂无数据'}</span>
        <span>{rows[rows.length - 1]?.date || '等待真实访问'}</span>
      </div>
    </div>
  )
}

export default function AdminOverviewPage() {
  const [days, setDays] = useState(7)
  const query = useQuery<AdminOverview>({
    queryKey: ['admin-overview', days],
    queryFn: async () => {
      const response = await apiClient.get('/admin/analytics/overview', {
        params: { days },
      })
      return response.data
    },
  })

  if (query.isLoading) {
    return <AdminLoading />
  }
  if (query.isError || !query.data) {
    return <AdminError onRetry={() => void query.refetch()} />
  }

  const data = query.data
  const pending = data.business.pending_upgrades + data.business.pending_credit_purchases
  const lcp = data.performance.metrics.LCP
  const finding =
    pending > 0
      ? `${pending} 笔订单等待人工审核，${data.business.feedback_open} 条反馈仍在处理中。`
      : data.business.feedback_open > 0
        ? `${data.business.feedback_open} 条用户反馈仍在处理中。`
        : '当前没有积压的订单或反馈，继续关注流量和页面性能。'

  return (
    <div className="space-y-6">
      <AdminPageHeader
        title="运营总览"
        description={`近 ${days} 天的真实业务、访问与页面性能状态`}
        action={
          <div className="flex items-center gap-2">
            <select
              aria-label="统计时间范围"
              className="h-9 rounded-md border border-border bg-[var(--factory-panel)] px-2 text-sm"
              value={days}
              onChange={(event) => setDays(Number(event.target.value))}
            >
              <option value={7}>近 7 天</option>
              <option value={30}>近 30 天</option>
              <option value={90}>近 90 天</option>
            </select>
            <button
              type="button"
              className="inline-flex h-9 items-center gap-1.5 rounded-md border border-border px-3 text-xs text-muted-foreground hover:text-foreground"
              onClick={() => void query.refetch()}
            >
              <RefreshCw className={`h-3.5 w-3.5 ${query.isFetching ? 'animate-spin' : ''}`} />
              刷新
            </button>
          </div>
        }
      />

      <section className="border border-border bg-[var(--factory-panel)]">
        <div className="border-b border-border px-4 py-3">
          <p className="text-sm font-medium text-foreground">当前最需要处理</p>
          <p className="mt-0.5 text-xs text-muted-foreground">{finding}</p>
        </div>
        <div className="grid grid-cols-2 divide-x divide-y divide-border md:grid-cols-3 xl:grid-cols-6 xl:divide-y-0">
          {[
            ['用户总数', formatNumber(data.business.total_users)],
            ['付费用户', formatNumber(data.business.paid_users)],
            ['确认收入', formatMoney(data.business.revenue)],
            ['待审订单', formatNumber(pending)],
            ['PV / UV', `${formatNumber(data.traffic.pv)} / ${formatNumber(data.traffic.uv)}`],
            ['LCP p75', lcp.p75 == null ? '-' : `${formatNumber(lcp.p75)} ms`],
          ].map(([label, value]) => (
            <div key={label} className="min-h-24 px-4 py-4">
              <p className="text-xs text-muted-foreground">{label}</p>
              <p className="metric-number mt-2 text-2xl font-medium text-foreground">{value}</p>
            </div>
          ))}
        </div>
      </section>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.45fr)_minmax(320px,0.75fr)]">
        <AdminPanel title="页面访问趋势" description="按天统计的公开页面 PV，仅供运营判断">
          <TrendChart rows={data.traffic.daily} />
        </AdminPanel>

        <AdminPanel title="待办队列" description="有明确处理动作的事项">
          <div className="divide-y divide-border">
            {[
              {
                label: '套餐升级申请',
                value: data.business.pending_upgrades,
                to: '/admin/orders',
              },
              {
                label: '积分包到账确认',
                value: data.business.pending_credit_purchases,
                to: '/admin/orders',
              },
              {
                label: '未关闭用户反馈',
                value: data.business.feedback_open,
                to: '/admin/feedback',
              },
            ].map((item) => (
              <Link
                key={item.label}
                to={item.to}
                className="flex min-h-14 items-center justify-between gap-3 px-4 text-sm hover:bg-secondary/50"
              >
                <span className="text-muted-foreground">{item.label}</span>
                <span className="flex items-center gap-2 font-medium text-foreground">
                  {formatNumber(item.value)}
                  <ArrowUpRight className="h-3.5 w-3.5" />
                </span>
              </Link>
            ))}
          </div>
        </AdminPanel>
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <AdminPanel title="访问最多的页面" description="PV 优先，UV 用于判断覆盖人数">
          <div className="divide-y divide-border">
            {data.traffic.top_paths.length === 0 ? (
              <p className="px-4 py-10 text-center text-sm text-muted-foreground">
                尚无页面访问数据。
              </p>
            ) : (
              data.traffic.top_paths.slice(0, 6).map((row) => (
                <div
                  key={row.path}
                  className="grid grid-cols-[minmax(0,1fr)_72px_72px] items-center gap-3 px-4 py-3 text-sm"
                >
                  <span className="truncate text-foreground">{row.path}</span>
                  <span className="metric-number text-right text-muted-foreground">
                    {formatNumber(row.pv)} PV
                  </span>
                  <span className="metric-number text-right text-muted-foreground">
                    {formatNumber(row.uv)} UV
                  </span>
                </div>
              ))
            )}
          </div>
        </AdminPanel>

        <AdminPanel title="性能摘要" description="浏览器实测 p75，不是实验室估算">
          <div className="divide-y divide-border">
            {['LCP', 'FCP', 'INP', 'CLS', 'TTFB'].map((name) => {
              const metric = data.performance.metrics[name]
              return (
                <div
                  key={name}
                  className="grid grid-cols-[72px_minmax(0,1fr)_84px] items-center gap-3 px-4 py-3 text-sm"
                >
                  <span className="font-mono text-xs text-[var(--factory-accent)]">{name}</span>
                  <span className="text-muted-foreground">
                    {metric.samples ? `${metric.samples} 个样本` : '等待真实样本'}
                  </span>
                  <span className="metric-number text-right text-foreground">
                    {metric.p75 == null ? '-' : formatNumber(metric.p75, 2)}
                  </span>
                </div>
              )
            })}
          </div>
        </AdminPanel>
      </div>
    </div>
  )
}
