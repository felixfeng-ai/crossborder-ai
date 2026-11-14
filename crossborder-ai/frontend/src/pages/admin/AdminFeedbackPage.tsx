import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2, Save } from 'lucide-react'

import apiClient from '@/api/client'
import { Button } from '@/components/ui/button'
import {
  AdminError,
  AdminLoading,
  AdminPageHeader,
  AdminPanel,
  AdminStatusPill,
} from './AdminPrimitives'
import type { FeedbackTicket } from './adminTypes'

const STATUS_LABELS: Record<FeedbackTicket['status'], string> = {
  open: '待处理',
  in_progress: '处理中',
  resolved: '已解决',
  closed: '已关闭',
}

const PRIORITY_LABELS: Record<FeedbackTicket['priority'], string> = {
  low: '低',
  normal: '普通',
  high: '高',
  urgent: '紧急',
}

function statusTone(status: FeedbackTicket['status']) {
  if (status === 'resolved') return 'good' as const
  if (status === 'in_progress') return 'warning' as const
  if (status === 'closed') return 'neutral' as const
  return 'danger' as const
}

export default function AdminFeedbackPage() {
  const queryClient = useQueryClient()
  const [statusFilter, setStatusFilter] = useState('open')
  const [selected, setSelected] = useState<FeedbackTicket | null>(null)
  const [draftStatus, setDraftStatus] = useState<FeedbackTicket['status']>('open')
  const [draftPriority, setDraftPriority] = useState<FeedbackTicket['priority']>('normal')
  const [draftAssignee, setDraftAssignee] = useState('')
  const [draftNote, setDraftNote] = useState('')

  const query = useQuery<{ items: FeedbackTicket[] }>({
    queryKey: ['admin-feedback', statusFilter],
    queryFn: async () => {
      const response = await apiClient.get('/admin/feedback', {
        params: statusFilter ? { status: statusFilter } : {},
      })
      return response.data
    },
  })

  useEffect(() => {
    if (selected) {
      setDraftStatus(selected.status)
      setDraftPriority(selected.priority)
      setDraftAssignee(selected.assigned_to || '')
      setDraftNote(selected.note || '')
    }
  }, [selected])

  const update = useMutation({
    mutationFn: async () => {
      if (!selected) throw new Error('未选择反馈')
      const response = await apiClient.patch(`/admin/feedback/${selected.id}`, {
        status: draftStatus,
        priority: draftPriority,
        assigned_to: draftAssignee || null,
        note: draftNote || null,
      })
      return response.data as FeedbackTicket
    },
    onSuccess: (ticket) => {
      setSelected(ticket)
      void queryClient.invalidateQueries({ queryKey: ['admin-feedback'] })
      void queryClient.invalidateQueries({ queryKey: ['admin-overview'] })
      void queryClient.invalidateQueries({ queryKey: ['admin-audits'] })
    },
  })

  if (query.isLoading) return <AdminLoading />
  if (query.isError || !query.data) {
    return <AdminError onRetry={() => void query.refetch()} />
  }

  return (
    <div className="space-y-6">
      <AdminPageHeader
        title="反馈收件箱"
        description="按状态处理卖家问题，内部备注不会展示给用户"
        action={
          <select
            aria-label="反馈状态筛选"
            value={statusFilter}
            onChange={(event) => {
              setStatusFilter(event.target.value)
              setSelected(null)
            }}
            className="h-9 rounded-md border border-border bg-[var(--factory-panel)] px-2 text-sm"
          >
            <option value="open">待处理</option>
            <option value="in_progress">处理中</option>
            <option value="resolved">已解决</option>
            <option value="closed">已关闭</option>
            <option value="">全部</option>
          </select>
        }
      />

      <div className="grid gap-5 xl:grid-cols-[minmax(360px,0.8fr)_minmax(0,1.2fr)]">
        <AdminPanel title={`反馈列表 · ${query.data.items.length}`}>
          <div className="max-h-[680px] divide-y divide-border overflow-y-auto">
            {query.data.items.length === 0 ? (
              <p className="px-4 py-12 text-center text-sm text-muted-foreground">
                当前筛选下没有反馈。
              </p>
            ) : (
              query.data.items.map((ticket) => (
                <button
                  key={ticket.id}
                  type="button"
                  onClick={() => setSelected(ticket)}
                  className={`block w-full px-4 py-4 text-left transition-colors ${
                    selected?.id === ticket.id ? 'bg-secondary' : 'hover:bg-secondary/60'
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <p className="line-clamp-2 text-sm font-medium text-foreground">{ticket.title}</p>
                    <AdminStatusPill tone={statusTone(ticket.status)}>
                      {STATUS_LABELS[ticket.status]}
                    </AdminStatusPill>
                  </div>
                  <p className="mt-2 line-clamp-2 text-xs leading-5 text-muted-foreground">
                    {ticket.content}
                  </p>
                  <div className="mt-2 flex items-center justify-between text-[11px] text-muted-foreground">
                    <span>{ticket.page_path || '未记录页面'}</span>
                    <span>{ticket.created_at.slice(0, 16)}</span>
                  </div>
                </button>
              ))
            )}
          </div>
        </AdminPanel>

        <AdminPanel
          title={selected ? selected.title : '反馈详情'}
          description={
            selected
              ? `${selected.type} · ${selected.page_title || selected.page_path}`
              : '从左侧选择一条反馈'
          }
        >
          {!selected ? (
            <p className="px-4 py-16 text-center text-sm text-muted-foreground">
              查看问题页面、浏览器上下文和处理记录。
            </p>
          ) : (
            <div className="space-y-5 p-4">
              <div className="border border-border bg-[var(--factory-ground)] p-4">
                <p className="whitespace-pre-wrap text-sm leading-6 text-foreground">
                  {selected.content}
                </p>
              </div>
              <dl className="grid gap-3 text-xs sm:grid-cols-2">
                <div>
                  <dt className="text-muted-foreground">页面</dt>
                  <dd className="mt-1 break-all text-foreground">{selected.page_path || '-'}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">请求 ID</dt>
                  <dd className="mt-1 break-all font-mono text-foreground">
                    {String(selected.browser_info.request_id || '-')}
                  </dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">浏览器</dt>
                  <dd className="mt-1 text-foreground">
                    {String(selected.browser_info.user_agent || '-')}
                  </dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">视口</dt>
                  <dd className="metric-number mt-1 text-foreground">
                    {String(selected.browser_info.viewport_width || '-')} px
                  </dd>
                </div>
              </dl>

              <div className="grid gap-3 sm:grid-cols-2">
                <label className="space-y-1.5 text-xs text-muted-foreground">
                  <span>处理状态</span>
                  <select
                    value={draftStatus}
                    onChange={(event) =>
                      setDraftStatus(event.target.value as FeedbackTicket['status'])
                    }
                    className="h-9 w-full rounded-md border border-border bg-[var(--factory-ground)] px-2 text-sm text-foreground"
                  >
                    {Object.entries(STATUS_LABELS).map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="space-y-1.5 text-xs text-muted-foreground">
                  <span>优先级</span>
                  <select
                    value={draftPriority}
                    onChange={(event) =>
                      setDraftPriority(event.target.value as FeedbackTicket['priority'])
                    }
                    className="h-9 w-full rounded-md border border-border bg-[var(--factory-ground)] px-2 text-sm text-foreground"
                  >
                    {Object.entries(PRIORITY_LABELS).map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                </label>
              </div>

              <label className="block space-y-1.5 text-xs text-muted-foreground">
                <span>负责人</span>
                <input
                  value={draftAssignee}
                  onChange={(event) => setDraftAssignee(event.target.value)}
                  placeholder="邮箱或运营人员"
                  className="h-9 w-full rounded-md border border-border bg-[var(--factory-ground)] px-2.5 text-sm text-foreground outline-none focus:ring-2 focus:ring-ring"
                />
              </label>

              <label className="block space-y-1.5 text-xs text-muted-foreground">
                <span>内部备注</span>
                <textarea
                  value={draftNote}
                  onChange={(event) => setDraftNote(event.target.value)}
                  rows={5}
                  className="w-full rounded-md border border-border bg-[var(--factory-ground)] px-2.5 py-2 text-sm leading-6 text-foreground outline-none focus:ring-2 focus:ring-ring"
                />
              </label>

              <div className="flex items-center gap-3">
                <Button
                  type="button"
                  size="sm"
                  disabled={update.isPending}
                  onClick={() => update.mutate()}
                >
                  {update.isPending ? (
                    <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Save className="mr-1 h-3.5 w-3.5" />
                  )}
                  保存处理结果
                </Button>
                {update.isError && (
                  <p role="alert" className="text-xs text-[var(--factory-coral)]">
                    保存失败，请重试。
                  </p>
                )}
              </div>
            </div>
          )}
        </AdminPanel>
      </div>
    </div>
  )
}
