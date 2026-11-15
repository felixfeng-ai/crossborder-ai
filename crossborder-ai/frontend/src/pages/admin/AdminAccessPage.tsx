import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2, ShieldAlert, Trash2, UserPlus } from 'lucide-react'

import apiClient from '@/api/client'
import ConfirmDialog from '@/components/common/ConfirmDialog'
import {
  AdminError,
  AdminLoading,
  AdminPageHeader,
  AdminPanel,
  AdminStatusPill,
} from './AdminPrimitives'

export default function AdminAccessPage() {
  const queryClient = useQueryClient()
  const [email, setEmail] = useState('')
  const [message, setMessage] = useState('')
  const [pendingRemoval, setPendingRemoval] = useState('')

  const query = useQuery<{ emails: string[] }>({
    queryKey: ['admin-whitelist'],
    queryFn: async () => {
      const response = await apiClient.get('/settings/whitelist')
      return response.data
    },
  })

  const addMutation = useMutation({
    mutationFn: async (targetEmail: string) => {
      const response = await apiClient.post('/settings/whitelist/add', {
        email: targetEmail,
      })
      return response.data
    },
    onSuccess: (_, targetEmail) => {
      setEmail('')
      setMessage(`已将 ${targetEmail} 加入白名单。`)
      void queryClient.invalidateQueries({ queryKey: ['admin-whitelist'] })
      void queryClient.invalidateQueries({ queryKey: ['admin-audits'] })
    },
    onError: () => setMessage('添加失败，请检查邮箱格式和当前管理员权限。'),
  })

  const removeMutation = useMutation({
    mutationFn: async (targetEmail: string) => {
      const response = await apiClient.post('/settings/whitelist/remove', {
        email: targetEmail,
      })
      return response.data
    },
    onSuccess: (_, targetEmail) => {
      setMessage(`已移除白名单账号 ${targetEmail}。`)
      setPendingRemoval('')
      void queryClient.invalidateQueries({ queryKey: ['admin-whitelist'] })
      void queryClient.invalidateQueries({ queryKey: ['admin-audits'] })
    },
    onError: () => {
      setPendingRemoval('')
      setMessage('移除失败，请稍后重试。')
    },
  })

  if (query.isLoading) return <AdminLoading label="正在读取访问控制名单" />
  if (query.isError || !query.data) {
    return <AdminError onRetry={() => void query.refetch()} />
  }

  return (
    <div className="space-y-6">
      <AdminPageHeader
        title="访问控制"
        description="管理可绕过套餐限制的受控测试账号"
      />

      <div className="border border-[color:color-mix(in_srgb,var(--factory-coral)_36%,var(--factory-line))] bg-[color:color-mix(in_srgb,var(--factory-coral)_8%,var(--factory-panel))] px-4 py-3">
        <div className="flex items-start gap-2">
          <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-[var(--factory-coral)]" />
          <div>
            <p className="text-sm font-medium text-foreground">白名单可绕过套餐限制</p>
            <p className="mt-1 text-xs leading-5 text-muted-foreground">
              仅用于平台验收、商务演示和受控测试账号。添加前确认账号归属与回收时间，不应用于普通卖家。
            </p>
          </div>
        </div>
      </div>

      <AdminPanel
        title={`白名单账号 · ${query.data.emails.length}`}
        description="按邮箱精确匹配"
      >
        <form
          className="flex flex-col gap-3 border-b border-border px-4 py-4 sm:flex-row sm:items-end"
          onSubmit={(event) => {
            event.preventDefault()
            const normalized = email.trim().toLowerCase()
            if (!normalized) return
            addMutation.mutate(normalized)
          }}
        >
          <label className="min-w-0 flex-1 space-y-1.5 text-xs text-muted-foreground">
            <span>账号邮箱</span>
            <input
              type="email"
              required
              value={email}
              onChange={(event) => {
                setMessage('')
                setEmail(event.target.value)
              }}
              placeholder="name@example.com"
              className="h-10 w-full rounded-md border border-border bg-[var(--factory-ground)] px-3 text-sm text-foreground outline-none placeholder:text-muted-foreground focus:ring-2 focus:ring-ring"
            />
          </label>
          <button
            type="submit"
            disabled={addMutation.isPending || !email.trim()}
            className="inline-flex h-10 items-center justify-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:pointer-events-none disabled:opacity-50"
          >
            {addMutation.isPending ? (
              <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
            ) : (
              <UserPlus className="mr-1.5 h-3.5 w-3.5" />
            )}
            加入白名单
          </button>
        </form>

        {message && (
          <p
            role={addMutation.isError || removeMutation.isError ? 'alert' : 'status'}
            className="border-b border-border px-4 py-2 text-xs text-muted-foreground"
          >
            {message}
          </p>
        )}

        <div className="divide-y divide-border">
          {query.data.emails.length === 0 ? (
            <p className="px-4 py-12 text-center text-sm text-muted-foreground">
              当前没有白名单账号。
            </p>
          ) : (
            query.data.emails.map((item) => (
              <div
                key={item}
                className="flex min-h-14 items-center justify-between gap-3 px-4 py-3"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm text-foreground">{item}</p>
                  <p className="mt-0.5 text-[11px] text-muted-foreground">
                    可绕过套餐功能限制
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <AdminStatusPill tone="warning">受控访问</AdminStatusPill>
                  <button
                    type="button"
                    disabled={removeMutation.isPending}
                    onClick={() => setPendingRemoval(item)}
                    className="inline-flex h-9 w-9 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-secondary hover:text-[var(--factory-coral)] disabled:opacity-50"
                    aria-label={`移除白名单 ${item}`}
                    title="移除白名单"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      </AdminPanel>

      <ConfirmDialog
        open={Boolean(pendingRemoval)}
        title="移除白名单账号"
        description={`移除 ${pendingRemoval} 后，该账号将立即恢复套餐功能限制。请确认该账号不再用于平台验收或商务演示。`}
        confirmLabel="确认移除"
        pending={removeMutation.isPending}
        onCancel={() => {
          if (!removeMutation.isPending) setPendingRemoval('')
        }}
        onConfirm={() => {
          if (pendingRemoval) removeMutation.mutate(pendingRemoval)
        }}
      />
    </div>
  )
}
