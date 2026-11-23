import type { NotificationItem } from './types'

export interface NotificationGroup {
  key: string
  title: string
  items: NotificationItem[]
}

export function unreadNotificationCount(
  notifications: NotificationItem[],
): number {
  return notifications.filter((notification) => !notification.read_at).length
}

export function canEditNotificationPreferences(
  role?: string | null,
): boolean {
  return role === 'owner' || role === 'admin'
}

function dateKey(value: Date): string {
  const year = value.getFullYear()
  const month = String(value.getMonth() + 1).padStart(2, '0')
  const day = String(value.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

export function groupNotificationsByDay(
  notifications: NotificationItem[],
  reference = new Date(),
): NotificationGroup[] {
  const today = new Date(reference)
  today.setHours(0, 0, 0, 0)
  const yesterday = new Date(today)
  yesterday.setDate(yesterday.getDate() - 1)
  const todayKey = dateKey(today)
  const yesterdayKey = dateKey(yesterday)
  const groups = new Map<string, NotificationItem[]>()

  for (const notification of notifications) {
    const key = dateKey(new Date(notification.created_at))
    groups.set(key, [...(groups.get(key) ?? []), notification])
  }

  return [...groups.entries()]
    .sort(([left], [right]) => right.localeCompare(left))
    .map(([key, items]) => ({
      key,
      title:
        key === todayKey
          ? '今天'
          : key === yesterdayKey
            ? '昨天'
            : new Date(`${key}T00:00:00`).toLocaleDateString('zh-CN', {
                month: '2-digit',
                day: '2-digit',
              }),
      items: items.sort((left, right) =>
        right.created_at.localeCompare(left.created_at),
      ),
    }))
}

export function normalizeNotificationDeepLink(deepLink: string): string {
  const value = deepLink.trim()
  if (!value) return '/app/today'
  if (value.startsWith('veyaship://task/')) {
    return `/app/tasks/${value.slice('veyaship://task/'.length)}`
  }
  if (value.startsWith('/task/')) {
    return `/app/tasks/${value.slice('/task/'.length)}`
  }
  if (value.startsWith('/app/')) return value
  return value
}

export function validateNotificationPreferenceDraft(input: {
  timezone: string
  quiet_start_hour: number | null
  quiet_end_hour: number | null
}): string | null {
  if (!input.timezone.trim()) {
    return '请填写 IANA 时区，例如 Asia/Shanghai'
  }
  const start = input.quiet_start_hour
  const end = input.quiet_end_hour
  if ((start == null) !== (end == null)) {
    return '免打扰开始和结束时间需要同时设置'
  }
  if (
    start != null &&
    (!Number.isInteger(start) || start < 0 || start > 23)
  ) {
    return '免打扰开始时间必须在 0 到 23 点之间'
  }
  if (end != null && (!Number.isInteger(end) || end < 0 || end > 23)) {
    return '免打扰结束时间必须在 0 到 23 点之间'
  }
  return null
}
