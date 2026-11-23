import apiClient from '@/api/client'
import { MOBILE_API_BASE } from '@/features/workspace-context/workspace-api'
import type { User } from '@/types'

export interface AgentControlResponse {
  paused: boolean
  frozen_action_count: number
  policies: Array<{
    id: string
    action_id: string
    autonomy_level: 'suggest' | 'confirm' | 'auto'
    conditions: Record<string, number | boolean>
    enabled: boolean
    version: number
  }>
}

export interface DeviceSession {
  id: string
  device_name: string | null
  platform: string | null
  client_version: string | null
  created_at: string
  last_used_at: string
  expires_at: string
  current: boolean
}

export async function fetchMyAvatar(): Promise<Blob> {
  const response = await apiClient.get<Blob>('/users/me/avatar', {
    responseType: 'blob',
  })
  return response.data
}

export async function uploadMyAvatar(file: File): Promise<User> {
  const form = new FormData()
  form.append('file', file)
  const response = await apiClient.put<User>('/users/me/avatar', form)
  return response.data
}

export async function removeMyAvatar(): Promise<void> {
  await apiClient.delete('/users/me/avatar')
}

export async function getAgentControl(
  workspaceId: string,
): Promise<AgentControlResponse> {
  const response = await apiClient.get<AgentControlResponse>(
    `/workspaces/${workspaceId}/agent-control`,
    { baseURL: MOBILE_API_BASE },
  )
  return response.data
}

export async function setAgentPaused(
  workspaceId: string,
  paused: boolean,
): Promise<AgentControlResponse> {
  const response = await apiClient.patch<AgentControlResponse>(
    `/workspaces/${workspaceId}/agent-control`,
    { paused },
    { baseURL: MOBILE_API_BASE },
  )
  return response.data
}

export async function getDeviceSessions(): Promise<DeviceSession[]> {
  const response = await apiClient.get<{ items: DeviceSession[] }>(
    '/auth/sessions',
  )
  return response.data.items
}

export async function logoutAllDevices(): Promise<void> {
  await apiClient.post('/auth/logout-all')
}
