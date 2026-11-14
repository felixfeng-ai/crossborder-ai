import { useQuery } from '@tanstack/react-query'

import apiClient from '@/api/client'
import {
  AdminError,
  AdminLoading,
  AdminPageHeader,
  AdminPanel,
  formatNumber,
} from './AdminPrimitives'
import type { AdminOverview } from './adminTypes'

export default function AdminAnalyticsPage() {
  const query = useQuery<AdminOverview>({
    queryKey: ['admin-analytics'],
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
  const data = query.data

  return (
    <div className="space-y-6">
      <AdminPageHeader
        title="访问分析"
        description="近 30 天匿名访问，不保存原始 IP 和完整 User-Agent"
      />
      <section className="grid grid-cols-3 divide-x divide-border border border-border bg-[var(--factory-panel)]">
        {[
          ['PV', data.traffic.pv],
          ['UV', data.traffic.uv],
          ['会话', data.traffic.sessions],
        ].map(([label, value]) => (
          <div key={String(label)} className="px-4 py-5">
            <p className="text-xs text-muted-foreground">{label}</p>
            <p className="metric-number mt-2 text-2xl font-medium">{formatNumber(Number(value))}</p>
          </div>
        ))}
      </section>

      <AdminPanel title="页面排行" description="按 PV 排序，UV 表示当天独立访问者">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[560px] text-left text-sm">
            <thead className="text-xs text-muted-foreground">
              <tr className="border-b border-border">
                <th className="px-4 py-3 font-normal">页面</th>
                <th className="px-4 py-3 text-right font-normal">PV</th>
                <th className="px-4 py-3 text-right font-normal">UV</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {data.traffic.top_paths.map((row) => (
                <tr key={row.path}>
                  <td className="max-w-[420px] truncate px-4 py-3">{row.path}</td>
                  <td className="metric-number px-4 py-3 text-right">{formatNumber(row.pv)}</td>
                  <td className="metric-number px-4 py-3 text-right">{formatNumber(row.uv)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </AdminPanel>

      <div className="grid gap-5 lg:grid-cols-2">
        {[
          { title: '设备分布', rows: data.traffic.devices.map((row) => [row.device, row.pv]) },
          { title: '地区分布', rows: data.traffic.countries.map((row) => [row.country, row.pv]) },
        ].map((block) => (
          <AdminPanel key={block.title} title={block.title}>
            <div className="divide-y divide-border">
              {block.rows.length === 0 ? (
                <p className="px-4 py-10 text-center text-sm text-muted-foreground">暂无数据</p>
              ) : (
                block.rows.map(([label, value]) => (
                  <div key={String(label)} className="flex items-center justify-between px-4 py-3 text-sm">
                    <span className="text-muted-foreground">{String(label)}</span>
                    <span className="metric-number text-foreground">{formatNumber(Number(value))}</span>
                  </div>
                ))
              )}
            </div>
          </AdminPanel>
        ))}
      </div>
    </div>
  )
}
