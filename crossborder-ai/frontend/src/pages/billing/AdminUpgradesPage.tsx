import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { CheckCircle2, XCircle, Loader2 } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import apiClient from '@/api/client'

interface UpgradeRecord {
  id: string
  plan: string
  contact: string
  order_id: string
  amount: number
  status: 'pending' | 'approved' | 'rejected'
  note: string
  created_at: string | null
  handled_at: string | null
}

const STATUS_META: Record<UpgradeRecord['status'], { label: string; variant: 'success' | 'warning' | 'destructive' }> = {
  pending: { label: '待确认', variant: 'warning' },
  approved: { label: '已开通', variant: 'success' },
  rejected: { label: '已拒绝', variant: 'destructive' },
}

const TABS = [
  { key: 'pending', label: '待处理' },
  { key: '', label: '全部' },
  { key: 'approved', label: '已开通' },
  { key: 'rejected', label: '已拒绝' },
]

function fmtTime(ts: string | null): string {
  if (!ts) return '—'
  return ts.slice(0, 16)
}

export default function AdminUpgradesPage() {
  const queryClient = useQueryClient()
  const [tab, setTab] = useState('pending')

  const { data, isFetching } = useQuery({
    queryKey: ['admin-upgrades', tab],
    queryFn: async () => {
      const params = tab ? `?status=${tab}` : ''
      const res = await apiClient.get(`/billing/admin/upgrades${params}`)
      return res.data.items as UpgradeRecord[]
    },
  })
  const items = data || []

  const handleMutation = useMutation({
    mutationFn: async ({ id, action }: { id: string; action: 'approve' | 'reject' }) => {
      const path = action === 'approve'
        ? `/billing/upgrades/${id}/approve`
        : `/billing/upgrades/${id}/reject`
      const res = await apiClient.post(path, { note: '' })
      return res.data
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin-upgrades'] }),
  })

  return (
    <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="space-y-6 max-w-4xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">升级审核</h1>
          <p className="text-muted-foreground mt-1">核对转账后一键开通套餐，或拒绝未到账的申请</p>
        </div>
        {isFetching && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
      </div>

      {/* Tab 切换 */}
      <div className="flex gap-1 rounded-lg border bg-muted/40 p-1 w-fit">
        {TABS.map((t) => (
          <button
            key={t.key || 'all'}
            onClick={() => setTab(t.key)}
            className={`rounded-md px-3 py-1.5 text-sm transition-colors ${
              tab === t.key ? 'bg-background shadow-sm font-medium' : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">申请列表（最多 200 条，最新在前）</CardTitle>
        </CardHeader>
        <CardContent>
          {items.length === 0 ? (
            <p className="text-sm text-muted-foreground py-8 text-center">暂无记录</p>
          ) : (
            <div className="space-y-3">
              {items.map((u) => {
                const meta = STATUS_META[u.status]
                return (
                  <div key={u.id} className="rounded-lg border p-3 space-y-2">
                    <div className="flex items-center justify-between gap-3">
                      <div className="flex items-center gap-2">
                        <p className="text-sm font-medium">
                          {u.plan === 'standard' ? 'Standard' : 'Professional'} · ¥{u.amount}
                        </p>
                        <Badge variant={meta.variant}>{meta.label}</Badge>
                      </div>
                      <span className="text-xs text-muted-foreground">{fmtTime(u.created_at)}</span>
                    </div>
                    <div className="text-xs text-muted-foreground space-y-0.5">
                      <p>联系方式：{u.contact || '—'}</p>
                      <p>
                        订单号：<code className="bg-muted px-1 py-0.5 rounded">{u.order_id}</code>
                      </p>
                      {u.note && <p>备注：{u.note}</p>}
                    </div>
                    {u.status === 'pending' && (
                      <div className="flex gap-2 pt-1">
                        <Button
                          size="sm"
                          className="flex-1"
                          disabled={handleMutation.isPending}
                          onClick={() => handleMutation.mutate({ id: u.id, action: 'approve' })}
                        >
                          {handleMutation.isPending ? (
                            <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
                          ) : (
                            <CheckCircle2 className="mr-1 h-3.5 w-3.5" />
                          )}
                          确认收款并开通
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          className="flex-1 text-destructive"
                          disabled={handleMutation.isPending}
                          onClick={() => handleMutation.mutate({ id: u.id, action: 'reject' })}
                        >
                          <XCircle className="mr-1 h-3.5 w-3.5" />
                          拒绝
                        </Button>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </motion.div>
  )
}
