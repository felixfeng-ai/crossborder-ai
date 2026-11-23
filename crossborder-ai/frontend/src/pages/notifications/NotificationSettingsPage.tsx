import { useEffect, useState } from 'react'
import {
  AlertCircle,
  BellRing,
  Loader2,
  Moon,
  RefreshCw,
  Save,
  TimerReset,
} from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  canEditNotificationPreferences,
  validateNotificationPreferenceDraft,
} from '@/features/notifications/notifications'
import {
  useNotificationPreferencesQuery,
  useUpdateNotificationPreferencesMutation,
} from '@/features/notifications/queries'
import type { NotificationPreferences } from '@/features/notifications/types'
import {
  activeWorkspaceRole,
  useWorkspaceContextStore,
} from '@/features/workspace-context/workspace-context-store'

const BOOLEAN_ROWS: Array<{
  key: keyof Pick<
    NotificationPreferences,
    | 'morning_brief'
    | 'day_closeout'
    | 'needs_action'
    | 'action_failed'
    | 'authorization_expired'
  >
  title: string
  detail: string
}> = [
  {
    key: 'morning_brief',
    title: '晨间计划',
    detail: '每天开始工作时收到今日安排',
  },
  {
    key: 'day_closeout',
    title: '每日日结',
    detail: 'Agent 完成一天工作后发送结果',
  },
  {
    key: 'needs_action',
    title: '等待你决定',
    detail: '有高风险动作或结果需要确认',
  },
  {
    key: 'action_failed',
    title: '执行失败',
    detail: '动作失败或平台回读不一致',
  },
  {
    key: 'authorization_expired',
    title: '授权失效',
    detail: '店铺连接过期或权限不足',
  },
]

export default function NotificationSettingsPage() {
  const workspaceId = useWorkspaceContextStore(
    (state) => state.activeWorkspaceId,
  )
  const workspaces = useWorkspaceContextStore((state) => state.workspaces)
  const role = activeWorkspaceRole(workspaces, workspaceId)
  const editable = canEditNotificationPreferences(role)
  const query = useNotificationPreferencesQuery(workspaceId)
  const mutation = useUpdateNotificationPreferencesMutation(workspaceId)
  const [draft, setDraft] = useState<NotificationPreferences | null>(null)
  const [error, setError] = useState('')
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    if (query.data) setDraft(query.data)
  }, [query.data])

  if (query.isError) {
    return (
      <div className="mx-auto max-w-2xl border border-border bg-[var(--factory-panel)] p-6">
        <AlertCircle className="h-5 w-5 text-[var(--factory-coral)]" />
        <h1 className="mt-3 text-lg font-semibold">通知偏好暂时无法同步</h1>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">
          当前不会显示默认值冒充已保存配置。
        </p>
        <Button
          className="mt-4"
          variant="outline"
          onClick={() => void query.refetch()}
        >
          <RefreshCw className="mr-2 h-4 w-4" />
          重新加载
        </Button>
      </div>
    )
  }

  if (query.isLoading || !draft) {
    return (
      <div className="flex min-h-[420px] items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-[var(--factory-accent)]" />
      </div>
    )
  }

  const updateDraft = (changes: Partial<NotificationPreferences>) => {
    if (!editable) return
    setSaved(false)
    setError('')
    setDraft((current) => (current ? { ...current, ...changes } : current))
  }

  const save = async () => {
    if (!editable || mutation.isPending) return
    const validation = validateNotificationPreferenceDraft({
      timezone: draft.timezone,
      quiet_start_hour: draft.quiet_start_hour,
      quiet_end_hour: draft.quiet_end_hour,
    })
    if (validation) {
      setError(validation)
      return
    }
    try {
      const next = await mutation.mutateAsync(draft)
      setDraft(next)
      setSaved(true)
    } catch {
      setError('通知偏好没有保存，请刷新后重试')
    }
  }

  const hourOptions = Array.from({ length: 24 }, (_, i) => i)

  return (
    <div className="mx-auto max-w-3xl space-y-6" data-notification-settings="true">
      <header className="border-b border-border pb-6">
        <h1 className="page-title">通知偏好</h1>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">
          控制 Agent、店铺授权和每日工作的提醒方式。高优先级失败不受免打扰影响。
        </p>
      </header>

      {!editable && (
        <div className="border border-border bg-[var(--factory-panel)] px-4 py-3 text-sm text-muted-foreground">
          当前角色只能查看通知偏好，只有所有者和管理员可以修改。
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <BellRing className="h-4 w-4" />
            提醒类型
          </CardTitle>
        </CardHeader>
        <CardContent className="pt-0">
          {BOOLEAN_ROWS.map((row, index) => (
            <label
              key={row.key}
              className={`flex cursor-pointer items-center justify-between gap-4 py-4 ${
                index > 0 ? 'border-t border-border' : ''
              } ${!editable ? 'cursor-not-allowed opacity-60' : ''}`}
            >
              <span>
                <span className="block text-sm font-medium">{row.title}</span>
                <span className="mt-1 block text-xs text-muted-foreground">
                  {row.detail}
                </span>
              </span>
              <input
                type="checkbox"
                checked={draft[row.key]}
                disabled={!editable}
                onChange={(event) =>
                  updateDraft({ [row.key]: event.target.checked })
                }
                className="h-4 w-4 accent-[var(--factory-accent)]"
              />
            </label>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Moon className="h-4 w-4" />
            免打扰
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 pt-0">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border pb-4">
            <div>
              <p className="text-sm font-medium">免打扰时段</p>
              <p className="mt-1 text-xs text-muted-foreground">
                关闭后任何提醒都可能即时送达。
              </p>
            </div>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={!editable}
              onClick={() =>
                updateDraft({
                  quiet_start_hour: null,
                  quiet_end_hour: null,
                })
              }
            >
              关闭
            </Button>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="space-y-1.5 text-xs text-muted-foreground">
              开始
              <select
                value={draft.quiet_start_hour ?? ''}
                disabled={!editable}
                onChange={(event) =>
                  updateDraft({
                    quiet_start_hour: event.target.value
                      ? Number(event.target.value)
                      : null,
                  })
                }
                className="h-10 w-full border border-border bg-background px-3 text-sm text-foreground"
              >
                <option value="">未设置</option>
                {hourOptions.map((hour) => (
                  <option key={hour} value={hour}>
                    {String(hour).padStart(2, '0')}:00
                  </option>
                ))}
              </select>
            </label>
            <label className="space-y-1.5 text-xs text-muted-foreground">
              结束
              <select
                value={draft.quiet_end_hour ?? ''}
                disabled={!editable}
                onChange={(event) =>
                  updateDraft({
                    quiet_end_hour: event.target.value
                      ? Number(event.target.value)
                      : null,
                  })
                }
                className="h-10 w-full border border-border bg-background px-3 text-sm text-foreground"
              >
                <option value="">未设置</option>
                {hourOptions.map((hour) => (
                  <option key={hour} value={hour}>
                    {String(hour).padStart(2, '0')}:00
                  </option>
                ))}
              </select>
            </label>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <TimerReset className="h-4 w-4" />
            时区
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 pt-0">
          <input
            value={draft.timezone}
            disabled={!editable}
            onChange={(event) => updateDraft({ timezone: event.target.value })}
            placeholder="Asia/Shanghai"
            className="h-10 w-full border border-border bg-background px-3 text-sm"
          />
          <p className="text-xs text-muted-foreground">
            使用 IANA 时区名称，例如 Asia/Shanghai。
          </p>
        </CardContent>
      </Card>

      {(error || saved) && (
        <div
          className={`border px-4 py-3 text-sm ${
            error
              ? 'border-[color:rgba(217,139,112,0.3)] bg-[color:rgba(217,139,112,0.08)] text-[var(--factory-coral)]'
              : 'border-[color:rgba(157,187,173,0.3)] bg-[color:rgba(157,187,173,0.08)] text-[var(--factory-mint)]'
          }`}
        >
          {error || '通知偏好已保存'}
        </div>
      )}

      {editable && (
        <div className="flex justify-end">
          <Button
            onClick={() => void save()}
            disabled={mutation.isPending}
            className="min-w-36"
          >
            {mutation.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Save className="mr-2 h-4 w-4" />
            )}
            保存通知偏好
          </Button>
        </div>
      )}
    </div>
  )
}
