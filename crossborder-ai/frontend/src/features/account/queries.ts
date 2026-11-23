import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  getAgentControl,
  getDeviceSessions,
  logoutAllDevices,
  removeMyAvatar,
  setAgentPaused,
  uploadMyAvatar,
} from './api'

export function useAgentControlQuery(workspaceId: string | null) {
  return useQuery({
    queryKey: ['agent-control', workspaceId],
    enabled: Boolean(workspaceId),
    staleTime: 15_000,
    queryFn: () => getAgentControl(workspaceId!),
  })
}

export function useSetAgentPausedMutation(workspaceId: string | null) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (paused: boolean) => setAgentPaused(workspaceId!, paused),
    onSuccess: (data) => {
      queryClient.setQueryData(['agent-control', workspaceId], data)
    },
  })
}

export function useDeviceSessionsQuery() {
  return useQuery({
    queryKey: ['device-sessions'],
    staleTime: 15_000,
    queryFn: getDeviceSessions,
  })
}

export function useLogoutAllDevicesMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: logoutAllDevices,
    onSettled: async () => {
      await queryClient.invalidateQueries({ queryKey: ['device-sessions'] })
    },
  })
}

export function useUploadAvatarMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: uploadMyAvatar,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['my-avatar'] })
    },
  })
}

export function useRemoveAvatarMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: removeMyAvatar,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['my-avatar'] })
    },
  })
}
