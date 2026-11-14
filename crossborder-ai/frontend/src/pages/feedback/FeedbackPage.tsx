import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, Loader2, MessageSquareText } from 'lucide-react'
import { useLocation } from 'react-router-dom'

import apiClient from '@/api/client'
import { Button } from '@/components/ui/button'
import type { FeedbackTicket } from '@/pages/admin/adminTypes'

const STATUS_LABELS: Record<FeedbackTicket['status'], string> = {
  open: '待处理',
  in_progress: '处理中',
  resolved: '已解决',
  closed: '已关闭',
}

export default function FeedbackPage() {
  const location = useLocation()
  const queryClient = useQueryClient()
  const [type, setType] = useState('bug')
  const [title, setTitle] = useState('')
  const [content, setContent] = useState('')

  const history = useQuery<{ items: FeedbackTicket[] }>({
    queryKey: ['my-feedback'],
    queryFn: async () => {
      const response = await apiClient.get('/feedback/mine')
      return response.data
    },
  })
  const submit = useMutation({
    mutationFn: async () => {
      const response = await apiClient.post('/feedback', {
        type,
        title,
        content,
        page_path: location.pathname,
        page_title: '用户反馈',
        browser_info: {
          user_agent: navigator.userAgent,
          viewport_width: window.innerWidth,
          language: navigator.language,
        },
      })
      return response.data as FeedbackTicket
    },
    onSuccess: () => {
      setTitle('')
      setContent('')
      void queryClient.invalidateQueries({ queryKey: ['my-feedback'] })
    },
  })

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div className="border-b border-border pb-5">
        <h1 className="flex items-center gap-2 text-2xl font-semibold">
          <MessageSquareText className="h-5 w-5 text-[var(--factory-accent)]" />
          用户反馈
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          描述问题或建议，系统会自动附带当前页面和浏览器上下文。
        </p>
      </div>

      <section className="border border-border bg-[var(--factory-panel)]">
        <div className="border-b border-border px-4 py-3">
          <h2 className="text-sm font-semibold">提交新反馈</h2>
        </div>
        <form
          className="space-y-4 p-4"
          onSubmit={(event) => {
            event.preventDefault()
            submit.mutate()
          }}
        >
          <label className="block space-y-1.5 text-xs text-muted-foreground">
            <span>问题类型</span>
            <select
              value={type}
              onChange={(event) => setType(event.target.value)}
              className="h-9 w-full rounded-md border border-border bg-[var(--factory-ground)] px-2 text-sm text-foreground sm:max-w-xs"
            >
              <option value="bug">功能问题</option>
              <option value="performance">页面卡顿或速度</option>
              <option value="billing">账单与积分</option>
              <option value="content">AI 内容质量</option>
              <option value="feature">功能建议</option>
              <option value="other">其他</option>
            </select>
          </label>
          <label className="block space-y-1.5 text-xs text-muted-foreground">
            <span>标题</span>
            <input
              required
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              maxLength={200}
              className="h-9 w-full rounded-md border border-border bg-[var(--factory-ground)] px-2.5 text-sm text-foreground outline-none focus:ring-2 focus:ring-ring"
              placeholder="一句话说明问题"
            />
          </label>
          <label className="block space-y-1.5 text-xs text-muted-foreground">
            <span>详细描述</span>
            <textarea
              required
              value={content}
              onChange={(event) => setContent(event.target.value)}
              rows={6}
              maxLength={5000}
              className="w-full rounded-md border border-border bg-[var(--factory-ground)] px-2.5 py-2 text-sm leading-6 text-foreground outline-none focus:ring-2 focus:ring-ring"
              placeholder="说明操作步骤、预期结果和实际结果"
            />
          </label>
          <div className="flex items-center gap-3">
            <Button type="submit" size="sm" disabled={submit.isPending}>
              {submit.isPending ? (
                <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
              ) : (
                <CheckCircle2 className="mr-1 h-3.5 w-3.5" />
              )}
              提交反馈
            </Button>
            {submit.isSuccess && (
              <p className="text-xs text-[var(--factory-mint)]">反馈已提交，可在下方查看状态。</p>
            )}
            {submit.isError && (
              <p role="alert" className="text-xs text-[var(--factory-coral)]">
                提交失败，请稍后重试。
              </p>
            )}
          </div>
        </form>
      </section>

      <section className="border border-border bg-[var(--factory-panel)]">
        <div className="border-b border-border px-4 py-3">
          <h2 className="text-sm font-semibold">我的反馈</h2>
        </div>
        <div className="divide-y divide-border">
          {history.data?.items.length ? (
            history.data.items.map((ticket) => (
              <div key={ticket.id} className="px-4 py-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-sm font-medium">{ticket.title}</p>
                    <p className="mt-1 line-clamp-2 text-xs leading-5 text-muted-foreground">
                      {ticket.content}
                    </p>
                  </div>
                  <span className="shrink-0 rounded border border-border px-1.5 py-0.5 text-[11px] text-muted-foreground">
                    {STATUS_LABELS[ticket.status]}
                  </span>
                </div>
                <p className="mt-2 text-[11px] text-muted-foreground">
                  {ticket.created_at.slice(0, 16)} · {ticket.page_path}
                </p>
              </div>
            ))
          ) : (
            <p className="px-4 py-10 text-center text-sm text-muted-foreground">
              还没有提交过反馈。
            </p>
          )}
        </div>
      </section>
    </div>
  )
}
