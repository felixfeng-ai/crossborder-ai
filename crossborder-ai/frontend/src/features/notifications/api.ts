import apiClient from '@/api/client'

import type {
  NotificationItem,
  NotificationPreferences,
} from './types'

export async function getNotifications(
  workspaceId: string,
): Promise<NotificationItem[]> {
  const response = await apiClient.get<NotificationItem[]>(
    `/api/mobile/v1/workspaces/${workspaceId}/notifications`,
    { baseURL: '' },
  )
  return response.data
}

export async function markAllNotificationsRead(
  workspaceId: string,
): Promise<{ marked: number; read_at: string }> {
  const response = await apiClient.post<{ marked: number; read_at: string }>(
    `/api/mobile/v1/workspaces/${workspaceId}/notifications/read-all`,
    undefined,
    { baseURL: '' },
  )
  return response.data
}

export async function markNotificationRead(
  workspaceId: string,
  notificationId: string,
): Promise<{ id: string; read_at: string }> {
  const response = await apiClient.post<{ id: string; read_at: string }>(
    `/api/mobile/v1/workspaces/${workspaceId}/notifications/${notificationId}/read`,
    undefined,
    { baseURL: '' },
  )
  return response.data
}

export async function getNotificationPreferences(
  workspaceId: string,
): Promise<NotificationPreferences> {
  const response = await apiClient.get<NotificationPreferences>(
    `/api/mobile/v1/workspaces/${workspaceId}/notification-preferences`,
    { baseURL: '' },
  )
  return response.data
}

export async function updateNotificationPreferences(
  workspaceId: string,
  payload: Partial<NotificationPreferences>,
): Promise<NotificationPreferences> {
  const response = await apiClient.put<NotificationPreferences>(
    `/api/mobile/v1/workspaces/${workspaceId}/notification-preferences`,
    payload,
    { baseURL: '' },
  )
  return response.data
}
