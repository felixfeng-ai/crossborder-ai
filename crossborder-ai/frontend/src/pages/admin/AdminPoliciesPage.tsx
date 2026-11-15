import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { BookOpenCheck, Loader2, Upload } from 'lucide-react'

import apiClient from '@/api/client'
import {
  AdminError,
  AdminLoading,
  AdminPageHeader,
  AdminPanel,
  AdminStatusPill,
} from './AdminPrimitives'

type PolicySourceItem = {
  id: string
  title: string
  platform: string
  market: string
  category: string | null
  version: string
  source_url: string
  status: string
  updated_at: string
}

type PolicyForm = {
  title: string
  platform: string
  market: string
  category: string
  document_type: string
  source_url: string
  version: string
  effective_at: string
  content_text: string
}

const EMPTY_FORM: PolicyForm = {
  title: '',
  platform: 'amazon',
  market: 'US',
  category: '',
  document_type: 'listing_policy',
  source_url: '',
  version: '',
  effective_at: '',
  content_text: '',
}

export default function AdminPoliciesPage() {
  const queryClient = useQueryClient()
  const [form, setForm] = useState<PolicyForm>(EMPTY_FORM)
  const [message, setMessage] = useState('')

  const sourcesQuery = useQuery<{ items: PolicySourceItem[]; total: number }>({
    queryKey: ['admin-policy-sources'],
    queryFn: async () => {
      const response = await apiClient.get('/platform-policies/sources')
      return response.data
    },
  })

  const ingestMutation = useMutation({
    mutationFn: async () => {
      const response = await apiClient.post('/platform-policies/ingest', {
        ...form,
        category: form.category || null,
        effective_at: form.effective_at
          ? new Date(`${form.effective_at}T00:00:00`).toISOString()
          : null,
      })
      return response.data as {
        chunk_count: number
        vector_status: string
        changed: boolean
      }
    },
    onSuccess: (data) => {
      setMessage(
        data.changed
          ? `政策已入库：${data.chunk_count} 个片段，向量状态为 ${data.vector_status}。`
          : '政策版本内容未变化，已跳过重复入库。',
      )
      setForm((current) => ({
        ...current,
        title: '',
        source_url: '',
        version: '',
        content_text: '',
      }))
      void queryClient.invalidateQueries({ queryKey: ['admin-policy-sources'] })
      void queryClient.invalidateQueries({ queryKey: ['admin-audits'] })
    },
    onError: () => {
      setMessage('政策导入失败，请检查版本、来源链接和原文内容。')
    },
  })

  if (sourcesQuery.isLoading) return <AdminLoading label="正在读取政策知识库" />
  if (sourcesQuery.isError || !sourcesQuery.data) {
    return <AdminError onRetry={() => void sourcesQuery.refetch()} />
  }

  const canSubmit =
    form.title.trim() &&
    form.source_url.trim() &&
    form.version.trim() &&
    form.content_text.trim().length >= 20

  return (
    <div className="space-y-6">
      <AdminPageHeader
        title="政策知识库"
        description="维护平台级政策原文、版本与来源；RAG 只提供依据，不替代确定性合规规则"
      />

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.15fr)_minmax(340px,0.85fr)]">
        <AdminPanel
          title="导入政策版本"
          description="同一来源与版本内容不变时会自动跳过重复入库"
        >
          <div className="space-y-4 p-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="space-y-1.5 text-xs text-muted-foreground">
                <span>政策标题</span>
                <input
                  value={form.title}
                  onChange={(event) => setForm({ ...form, title: event.target.value })}
                  placeholder="例如 Amazon Children's Product Policy"
                  className="h-10 w-full rounded-md border border-border bg-[var(--factory-ground)] px-3 text-sm text-foreground outline-none placeholder:text-muted-foreground focus:ring-2 focus:ring-ring"
                />
              </label>
              <label className="space-y-1.5 text-xs text-muted-foreground">
                <span>平台</span>
                <select
                  value={form.platform}
                  onChange={(event) => setForm({ ...form, platform: event.target.value })}
                  className="h-10 w-full rounded-md border border-border bg-[var(--factory-ground)] px-3 text-sm text-foreground outline-none focus:ring-2 focus:ring-ring"
                >
                  <option value="amazon">Amazon</option>
                  <option value="tiktok">TikTok Shop</option>
                  <option value="shopify">Shopify</option>
                </select>
              </label>
              <label className="space-y-1.5 text-xs text-muted-foreground">
                <span>市场</span>
                <input
                  value={form.market}
                  onChange={(event) => setForm({ ...form, market: event.target.value })}
                  placeholder="US"
                  className="h-10 w-full rounded-md border border-border bg-[var(--factory-ground)] px-3 text-sm text-foreground outline-none placeholder:text-muted-foreground focus:ring-2 focus:ring-ring"
                />
              </label>
              <label className="space-y-1.5 text-xs text-muted-foreground">
                <span>类目（可选）</span>
                <input
                  value={form.category}
                  onChange={(event) => setForm({ ...form, category: event.target.value })}
                  placeholder="toys"
                  className="h-10 w-full rounded-md border border-border bg-[var(--factory-ground)] px-3 text-sm text-foreground outline-none placeholder:text-muted-foreground focus:ring-2 focus:ring-ring"
                />
              </label>
              <label className="space-y-1.5 text-xs text-muted-foreground">
                <span>版本</span>
                <input
                  value={form.version}
                  onChange={(event) => setForm({ ...form, version: event.target.value })}
                  placeholder="2026.11"
                  className="h-10 w-full rounded-md border border-border bg-[var(--factory-ground)] px-3 text-sm text-foreground outline-none placeholder:text-muted-foreground focus:ring-2 focus:ring-ring"
                />
              </label>
              <label className="space-y-1.5 text-xs text-muted-foreground">
                <span>生效日期</span>
                <input
                  type="date"
                  value={form.effective_at}
                  onChange={(event) => setForm({ ...form, effective_at: event.target.value })}
                  className="h-10 w-full rounded-md border border-border bg-[var(--factory-ground)] px-3 text-sm text-foreground outline-none focus:ring-2 focus:ring-ring"
                />
              </label>
              <label className="space-y-1.5 text-xs text-muted-foreground sm:col-span-2">
                <span>官方来源链接</span>
                <input
                  value={form.source_url}
                  onChange={(event) => setForm({ ...form, source_url: event.target.value })}
                  placeholder="https://sellercentral.amazon.com/..."
                  className="h-10 w-full rounded-md border border-border bg-[var(--factory-ground)] px-3 text-sm text-foreground outline-none placeholder:text-muted-foreground focus:ring-2 focus:ring-ring"
                />
              </label>
            </div>
            <label className="block space-y-1.5 text-xs text-muted-foreground">
              <span>政策原文（Markdown）</span>
              <textarea
                value={form.content_text}
                onChange={(event) => setForm({ ...form, content_text: event.target.value })}
                rows={12}
                placeholder={'# 政策标题\n\n## 具体要求\n\n粘贴经过审核的官方政策原文...'}
                className="w-full rounded-md border border-border bg-[var(--factory-ground)] px-3 py-2 text-sm leading-6 text-foreground outline-none placeholder:text-muted-foreground focus:ring-2 focus:ring-ring"
              />
            </label>
            <div className="flex flex-wrap items-center gap-3">
              <button
                type="button"
                disabled={!canSubmit || ingestMutation.isPending}
                onClick={() => ingestMutation.mutate()}
                className="inline-flex h-9 items-center justify-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:pointer-events-none disabled:opacity-50"
              >
                {ingestMutation.isPending ? (
                  <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Upload className="mr-1.5 h-3.5 w-3.5" />
                )}
                导入政策
              </button>
              {message && (
                <p
                  role={ingestMutation.isError ? 'alert' : 'status'}
                  className={
                    ingestMutation.isError
                      ? 'text-xs text-[var(--factory-coral)]'
                      : 'text-xs text-muted-foreground'
                  }
                >
                  {message}
                </p>
              )}
            </div>
          </div>
        </AdminPanel>

        <AdminPanel
          title={`政策来源 · ${sourcesQuery.data.total}`}
          description="按最近更新时间倒序显示"
        >
          <div className="max-h-[760px] divide-y divide-border overflow-y-auto">
            {sourcesQuery.data.items.length === 0 ? (
              <div className="flex min-h-44 flex-col items-center justify-center px-5 text-center">
                <BookOpenCheck className="h-5 w-5 text-muted-foreground" />
                <p className="mt-3 text-sm text-muted-foreground">尚未导入平台政策。</p>
              </div>
            ) : (
              sourcesQuery.data.items.map((item) => (
                <article key={item.id} className="px-4 py-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <h3 className="text-sm font-medium text-foreground">{item.title}</h3>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {item.platform.toUpperCase()} · {item.market}
                        {item.category ? ` · ${item.category}` : ''} · {item.version}
                      </p>
                    </div>
                    <AdminStatusPill tone={item.status === 'active' ? 'good' : 'neutral'}>
                      {item.status === 'active' ? '已启用' : item.status}
                    </AdminStatusPill>
                  </div>
                  <div className="mt-3 flex items-center justify-between gap-3 text-[11px] text-muted-foreground">
                    <span>{item.updated_at.slice(0, 16).replace('T', ' ')}</span>
                    <a
                      href={item.source_url}
                      target="_blank"
                      rel="noreferrer"
                      className="font-medium text-[var(--factory-accent)] underline-offset-4 hover:underline"
                    >
                      查看原文
                    </a>
                  </div>
                </article>
              ))
            )}
          </div>
        </AdminPanel>
      </div>
    </div>
  )
}
