import { describe, expect, it } from 'vitest'

import {
  canEditNotificationPreferences,
  groupNotificationsByDay,
  normalizeNotificationDeepLink,
  unreadNotificationCount,
  validateNotificationPreferenceDraft,
} from './notifications'
import type { NotificationItem } from './types'

const notifications: NotificationItem[] = [
  {
    id: 'n1',
    notification_type: 'needs_action',
    title: '需要确认回复',
    body: '买家正在等待物流回复',
    deep_link: 'veyaship://task/work-item-1',
    work_item_id: 'work-item-1',
    status: 'active',
    created_at: '2026-11-23T09:00:00+08:00',
    read_at: null,
  },
  {
    id: 'n2',
    notification_type: 'action_failed',
    title: '同步失败',
    body: '店铺授权已过期',
    deep_link: '/task/work-item-2',
    work_item_id: 'work-item-2',
    status: 'active',
    created_at: '2026-11-22T09:00:00+08:00',
    read_at: '2026-11-22T10:00:00+08:00',
  },
]

describe('notification behavior', () => {
  it('统计未读通知并只允许管理员修改偏好', () => {
    expect(unreadNotificationCount(notifications)).toBe(1)
    expect(canEditNotificationPreferences('owner')).toBe(true)
    expect(canEditNotificationPreferences('admin')).toBe(true)
    expect(canEditNotificationPreferences('operator')).toBe(false)
    expect(canEditNotificationPreferences('viewer')).toBe(false)
  })

  it('按业务日期分组通知', () => {
    const groups = groupNotificationsByDay(
      notifications,
      new Date('2026-11-23T12:00:00+08:00'),
    )
    expect(groups.map((group) => group.title)).toEqual(['今天', '昨天'])
    expect(groups[0].items.map((item) => item.id)).toEqual(['n1'])
    expect(groups[1].items.map((item) => item.id)).toEqual(['n2'])
  })

  it('把 App 深链转换成 Web 工作项路由', () => {
    expect(normalizeNotificationDeepLink('veyaship://task/work-item-1')).toBe(
      '/app/tasks/work-item-1',
    )
    expect(normalizeNotificationDeepLink('/task/work-item-2')).toBe(
      '/app/tasks/work-item-2',
    )
    expect(normalizeNotificationDeepLink('/app/tasks/work-item-3')).toBe(
      '/app/tasks/work-item-3',
    )
    expect(normalizeNotificationDeepLink('https://veyaship.com/help')).toBe(
      'https://veyaship.com/help',
    )
  })

  it('拒绝空时区和只设置一半的免打扰时段', () => {
    expect(
      validateNotificationPreferenceDraft({
        timezone: '',
        quiet_start_hour: null,
        quiet_end_hour: null,
      }),
    ).toBe('请填写 IANA 时区，例如 Asia/Shanghai')
    expect(
      validateNotificationPreferenceDraft({
        timezone: 'Asia/Shanghai',
        quiet_start_hour: 22,
        quiet_end_hour: null,
      }),
    ).toBe('免打扰开始和结束时间需要同时设置')
    expect(
      validateNotificationPreferenceDraft({
        timezone: 'Asia/Shanghai',
        quiet_start_hour: 22,
        quiet_end_hour: 8,
      }),
    ).toBeNull()
  })
})
