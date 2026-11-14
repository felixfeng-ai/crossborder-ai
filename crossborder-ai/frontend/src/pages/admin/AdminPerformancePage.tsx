import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'

import apiClient from '@/api/client'
import {
  AdminError,
  AdminLoading,
  AdminPageHeader,
  AdminPanel,
  AdminStatusPill,
  formatNumber,
} from './AdminPrimitives'
import type { AdminOverview } from './adminTypes'

const THRESHOLDS: Record<string, [number, number, string]> = {
  LCP: [2500, 4000, 'ms'],
  FCP: [1800, 3000, 'ms'],
  INP: [200, 500, 'ms'],
  CLS: [0.1, 0.25, ''],
  TTFB: [800, 1800, 'ms'],
}

function ratingFor(name: string, value: number | null): 'good' | 'warning' | 'danger' | 'neutral' {
  if (value == null) return 'neutral'
  const threshold = THRESHOLDS[name]
  if (!threshold) return 'neutral'
  if (value <= threshold[0]) return 'good'
  if (value <= threshold[1]) return 'warning'
  return 'danger'
}

export default function AdminPerformancePage() {
  const [group, setGroup] = useState<'all' | 'china' | 'overseas' | 'mobile'>('all')
  const query = useQuery<AdminOverview>({
    queryKey: ['admin-performance'],
    queryFn: async () => {
      const response = await apiClient.get('/admin/analytics/overview', {
        params: { days: 30 },
      })
      return response.data
    },
  })
  if (query.isLoading) return <AdminLoading />
  if (query.isError || !query.data) {
    return <AdminError onRetry={() => void query.refetch()} />
  }
  const metrics =
    query.data.performance.groups?.[group]?.metrics ||
    query.data.performance.metrics

  return (
    <div className="space-y-6">
      <AdminPageHeader
        title="页面性能"
        description="真实用户 Web Vitals，近 30 天 p75；样本不足时保持空值"
        action={
          <div className="flex flex-wrap gap-1 rounded-md border border-border p-1">
            {[
              ['all', '全部'],
              ['china', '中国'],
              ['overseas', '海外'],
              ['mobile', '移动网络'],
            ].map(([value, label]) => (
              <button
                key={value}
                type="button"
                onClick={() => setGroup(value as typeof group)}
                className={`min-h-7 rounded px-2 text-xs ${
                  group === value
                    ? 'bg-secondary text-foreground'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        }
      />
      <AdminPanel title="核心指标" description="绿色为良好，琥珀需要观察，珊瑚色需优化">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] text-left text-sm">
            <thead className="text-xs text-muted-foreground">
              <tr className="border-b border-border">
                <th className="px-4 py-3 font-normal">指标</th>
                <th className="px-4 py-3 text-right font-normal">p75</th>
                <th className="px-4 py-3 text-right font-normal">样本</th>
                <th className="px-4 py-3 text-right font-normal">良好</th>
                <th className="px-4 py-3 text-right font-normal">待改进</th>
                <th className="px-4 py-3 text-right font-normal">较差</th>
                <th className="px-4 py-3 text-right font-normal">目标</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {Object.entries(metrics).map(([name, metric]) => {
                const unit = THRESHOLDS[name]?.[2] || ''
                return (
                  <tr key={name}>
                    <td className="px-4 py-4 font-mono text-xs text-[var(--factory-accent)]">{name}</td>
                    <td className="metric-number px-4 py-4 text-right text-base text-foreground">
                      {metric.p75 == null ? '-' : `${formatNumber(metric.p75, 2)} ${unit}`}
                    </td>
                    <td className="metric-number px-4 py-4 text-right text-muted-foreground">
                      {formatNumber(metric.samples)}
                    </td>
                    <td className="metric-number px-4 py-4 text-right">{metric.ratings.good}</td>
                    <td className="metric-number px-4 py-4 text-right">
                      {metric.ratings['needs-improvement']}
                    </td>
                    <td className="metric-number px-4 py-4 text-right">{metric.ratings.poor}</td>
                    <td className="px-4 py-4 text-right">
                      <AdminStatusPill tone={ratingFor(name, metric.p75)}>
                        ≤ {formatNumber(THRESHOLDS[name]?.[0] ?? 0, name === 'CLS' ? 2 : 0)}
                        {unit}
                      </AdminStatusPill>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </AdminPanel>
      <p className="text-xs leading-5 text-muted-foreground">
        页面性能按浏览器真实上报计算。CLI 合成测试和 Lighthouse 数据不会混入这里，避免把实验室指标当成用户指标。
      </p>
    </div>
  )
}
