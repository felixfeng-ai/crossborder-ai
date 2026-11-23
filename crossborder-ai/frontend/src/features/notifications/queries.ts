import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  getNotificationPreferences,
  getNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  updateNotificationPreferences,
} from './api'
import type { NotificationPreferences } from './types'

export function useNotificationsQuery(workspaceId: string | null) {
  return useQuery({
    queryKey: ['notifications', workspaceId],
    enabled: Boolean(workspaceId),
    staleTime: 15_000,
    refetchInterval: 30_000,
    queryFn: () => getNotifications(workspaceId!),
  })
}

export function useNotificationPreferencesQuery(workspaceId: string | null) {
  return useQuery({
    queryKey: ['notification-preferences', workspaceId],
    enabled: Boolean(workspaceId),
    staleTime: 30_000,
    queryFn: () => getNotificationPreferences(workspaceId!),
  })
}

export function useMarkAllNotificationsReadMutation(
  workspaceId: string | null,
) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => markAllNotificationsRead(workspaceId!),
    onSettled: async () => {
      await queryClient.invalidateQueries({
        queryKey: ['notifications', workspaceId],
      })
    },
  })
}

export function useMarkNotificationReadMutation(
  workspaceId: string | null,
) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (notificationId: string) =>
      markNotificationRead(workspaceId!, notificationId),
    onSettled: async () => {
      await queryClient.invalidateQueries({
        queryKey: ['notifications', workspaceId],
      })
    },
  })
}

export function useUpdateNotificationPreferencesMutation(
  workspaceId: string | null,
) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: Partial<NotificationPreferences>) =>
      updateNotificationPreferences(workspaceId!, payload),
    onSuccess: (data) => {
      queryClient.setQueryData(
        ['notification-preferences', workspaceId],
        data,
      )
    },
  })
}
