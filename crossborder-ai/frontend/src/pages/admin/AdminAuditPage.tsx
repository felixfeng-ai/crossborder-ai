import { useQuery } from '@tanstack/react-query'

import apiClient from '@/api/client'
import { AdminError, AdminLoading, AdminPageHeader, AdminPanel } from './AdminPrimitives'

type AuditRow = {
  id: string
  action: string
  target_type: string
  target_id: string
  created_at: string
  changes: Record<string, unknown>
}

export default function AdminAuditPage() {
  const query = useQuery<{ items: AuditRow[] }>({
    queryKey: ['admin-audits'],
    queryFn: async () => {
      const response = await apiClient.get('/admin/audits?limit=100')
      return response.data
    },
  })
  if (query.isLoading) return <AdminLoading />
  if (query.isError || !query.data) {
    return <AdminError onRetry={() => void query.refetch()} />
  }

  return (
    <div className="space-y-6">
      <AdminPageHeader
        title="操作审计"
        description="套餐发布和反馈处理等管理员操作记录"
      />
      <AdminPanel>
        <div className="divide-y divide-border">
          {query.data.items.length === 0 ? (
            <p className="px-4 py-12 text-center text-sm text-muted-foreground">
              尚无管理员操作记录。
            </p>
          ) : (
            query.data.items.map((row) => (
              <div key={row.id} className="grid gap-2 px-4 py-4 sm:grid-cols-[minmax(0,1fr)_220px_160px]">
                <div>
                  <p className="text-sm font-medium text-foreground">{row.action}</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {row.target_type} · {row.target_id}
                  </p>
                </div>
                <code className="truncate text-xs text-muted-foreground">
                  {JSON.stringify(row.changes)}
                </code>
                <p className="metric-number text-xs text-muted-foreground sm:text-right">
                  {row.created_at.slice(0, 19)}
                </p>
              </div>
            ))
          )}
        </div>
      </AdminPanel>
    </div>
  )
}
