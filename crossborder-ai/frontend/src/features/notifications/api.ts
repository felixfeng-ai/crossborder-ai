import apiClient from '@/api/client'
import { MOBILE_API_BASE } from '@/features/workspace-context/workspace-api'

import type {
  NotificationItem,
  NotificationPreferences,
} from './types'

export async function getNotifications(
  workspaceId: string,
): Promise<NotificationItem[]> {
  const response = await apiClient.get<NotificationItem[]>(
    `/workspaces/${workspaceId}/notifications`,
    { baseURL: MOBILE_API_BASE },
  )
  return response.data
}

export async function markAllNotificationsRead(
  workspaceId: string,
): Promise<{ marked: number; read_at: string }> {
  const response = await apiClient.post<{ marked: number; read_at: string }>(
    `/workspaces/${workspaceId}/notifications/read-all`,
    undefined,
    { baseURL: MOBILE_API_BASE },
  )
  return response.data
}

export async function markNotificationRead(
  workspaceId: string,
  notificationId: string,
): Promise<{ id: string; read_at: string }> {
  const response = await apiClient.post<{ id: string; read_at: string }>(
    `/workspaces/${workspaceId}/notifications/${notificationId}/read`,
    undefined,
    { baseURL: MOBILE_API_BASE },
  )
  return response.data
}

export async function getNotificationPreferences(
  workspaceId: string,
): Promise<NotificationPreferences> {
  const response = await apiClient.get<NotificationPreferences>(
    `/workspaces/${workspaceId}/notification-preferences`,
    { baseURL: MOBILE_API_BASE },
  )
  return response.data
}

export async function updateNotificationPreferences(
  workspaceId: string,
  payload: Partial<NotificationPreferences>,
): Promise<NotificationPreferences> {
  const response = await apiClient.put<NotificationPreferences>(
    `/workspaces/${workspaceId}/notification-preferences`,
    payload,
    { baseURL: MOBILE_API_BASE },
  )
  return response.data
}
