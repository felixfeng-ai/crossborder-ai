import {
  AlertCircle,
  Bell,
  CalendarDays,
  CheckCheck,
  Loader2,
  MessageSquareText,
  RefreshCw,
  TriangleAlert,
} from 'lucide-react'
import { useNavigate } from 'react-router-dom'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  groupNotificationsByDay,
  normalizeNotificationDeepLink,
  unreadNotificationCount,
} from '@/features/notifications/notifications'
import {
  useMarkAllNotificationsReadMutation,
  useMarkNotificationReadMutation,
  useNotificationsQuery,
} from '@/features/notifications/queries'
import { useWorkspaceContextStore } from '@/features/workspace-context/workspace-context-store'

function NotificationIcon({ type }: { type: string }) {
  if (type === 'morning_brief' || type === 'day_closeout') {
    return <CalendarDays className="h-4 w-4" />
  }
  if (type === 'action_failed') {
    return <TriangleAlert className="h-4 w-4 text-[var(--factory-coral)]" />
  }
  if (type === 'needs_action') {
    return <MessageSquareText className="h-4 w-4 text-[var(--factory-accent)]" />
  }
  return <Bell className="h-4 w-4" />
}

export default function ActivityPage() {
  const navigate = useNavigate()
  const workspaceId = useWorkspaceContextStore(
    (state) => state.activeWorkspaceId,
  )
  const query = useNotificationsQuery(workspaceId)
  const markAll = useMarkAllNotificationsReadMutation(workspaceId)
  const markOne = useMarkNotificationReadMutation(workspaceId)
  const notifications = query.data ?? []
  const unreadCount = unreadNotificationCount(notifications)
  const groups = groupNotificationsByDay(notifications)

  const openNotification = async (id: string, readAt: string | null, deepLink: string) => {
    if (!readAt) {
      try {
        await markOne.mutateAsync(id)
      } catch {
        // 已读失败不阻断打开任务，列表后续刷新会恢复真实状态。
      }
    }
    const href = normalizeNotificationDeepLink(deepLink)
    if (href.startsWith('http')) {
      window.open(href, '_blank', 'noopener,noreferrer')
      return
    }
    navigate(href)
  }

  if (query.isLoading && !query.data) {
    return (
      <div className="flex min-h-[420px] items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-[var(--factory-accent)]" />
      </div>
    )
  }

  if (query.isError) {
    return (
      <div className="mx-auto max-w-2xl border border-border bg-[var(--factory-panel)] p-6">
        <AlertCircle className="h-5 w-5 text-[var(--factory-coral)]" />
        <h1 className="mt-3 text-lg font-semibold">通知暂时无法同步</h1>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">
          当前不会把请求失败显示成“暂无通知”。
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

  return (
    <div className="mx-auto max-w-4xl space-y-6" data-notification-center="true">
      <header className="flex flex-col justify-between gap-4 border-b border-border pb-6 sm:flex-row sm:items-end">
        <div>
          <h1 className="page-title">通知</h1>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            Agent 执行失败、授权失效和等待你决定的工作会集中到这里。
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant={unreadCount ? 'warning' : 'outline'}>
            {unreadCount} 条未读
          </Badge>
          <Button
            variant="outline"
            disabled={!unreadCount || markAll.isPending}
            onClick={() => void markAll.mutateAsync()}
          >
            {markAll.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <CheckCheck className="mr-2 h-4 w-4" />
            )}
            全部已读
          </Button>
          <Button
            size="icon"
            variant="ghost"
            aria-label="刷新通知"
            disabled={query.isFetching}
            onClick={() => void query.refetch()}
          >
            <RefreshCw
              className={`h-4 w-4 ${query.isFetching ? 'animate-spin' : ''}`}
            />
          </Button>
        </div>
      </header>

      {notifications.length === 0 ? (
        <div className="border border-border bg-[var(--factory-panel)] py-20 text-center">
          <Bell className="mx-auto h-8 w-8 text-muted-foreground" />
          <p className="mt-4 text-sm font-medium">暂无通知</p>
          <p className="mt-1 text-xs text-muted-foreground">
            失败、授权失效或等待确认时会出现在这里。
          </p>
        </div>
      ) : (
        groups.map((group) => (
          <section key={group.key}>
            <h2 className="mb-2 px-1 text-xs font-medium text-muted-foreground">
              {group.title}
            </h2>
            <div className="border border-border bg-[var(--factory-panel)]">
              {group.items.map((notification, index) => (
                <button
                  key={notification.id}
                  type="button"
                  onClick={() =>
                    void openNotification(
                      notification.id,
                      notification.read_at,
                      notification.deep_link,
                    )
                  }
                  className={`grid w-full gap-3 px-5 py-4 text-left hover:bg-accent/45 sm:grid-cols-[34px_minmax(0,1fr)_auto] ${
                    index > 0 ? 'border-t border-border' : ''
                  }`}
                >
                  <span className="flex h-8 w-8 items-center justify-center border border-border bg-background text-muted-foreground">
                    <NotificationIcon type={notification.notification_type} />
                  </span>
                  <span className="min-w-0">
                    <span
                      className={`block text-sm ${notification.read_at ? 'font-medium' : 'font-semibold'}`}
                    >
                      {notification.title}
                    </span>
                    <span className="mt-1 block text-xs leading-5 text-muted-foreground">
                      {notification.body}
                    </span>
                  </span>
                  <span className="flex items-center gap-2 text-[11px] text-muted-foreground">
                    {!notification.read_at && (
                      <span className="h-1.5 w-1.5 rounded-full bg-[var(--factory-accent)]" />
                    )}
                    {new Date(notification.created_at).toLocaleTimeString(
                      'zh-CN',
                      { hour: '2-digit', minute: '2-digit' },
                    )}
                  </span>
                </button>
              ))}
            </div>
          </section>
        ))
      )}
    </div>
  )
}
