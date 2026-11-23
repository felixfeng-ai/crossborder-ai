import apiClient from '@/api/client'

import type {
  CommandResponse,
  DailyPlanResponse,
  ImageAsset,
  TimelineResponse,
  AgentTurnDetail,
  AgentTurnResponse,
  WorkItemCommandPayload,
  WorkItemDetail,
} from './types'
import type { AgentTurnPayload } from './composer'

export function currentTimeZone(): string {
  return (
    Intl.DateTimeFormat().resolvedOptions().timeZone ||
    'Asia/Shanghai'
  )
}

export async function getDailyPlan(
  workspaceId: string,
): Promise<DailyPlanResponse> {
  const response = await apiClient.get<DailyPlanResponse>(
    `/api/mobile/v1/workspaces/${workspaceId}/daily-plan`,
    {
      baseURL: '',
      params: { timezone: currentTimeZone() },
    },
  )
  return response.data
}

export async function getTimeline(
  workspaceId: string,
): Promise<TimelineResponse> {
  const response = await apiClient.get<TimelineResponse>(
    `/api/mobile/v1/workspaces/${workspaceId}/timeline`,
    {
      baseURL: '',
      params: { timezone: currentTimeZone() },
    },
  )
  return response.data
}

export async function getWorkItem(
  workspaceId: string,
  workItemId: string,
): Promise<WorkItemDetail> {
  const response = await apiClient.get<WorkItemDetail>(
    `/api/mobile/v1/workspaces/${workspaceId}/work-items/${workItemId}`,
    { baseURL: '' },
  )
  return response.data
}

export async function submitWorkItemCommand(
  workspaceId: string,
  workItemId: string,
  command: WorkItemCommandPayload,
): Promise<CommandResponse> {
  const { idempotency_key: idempotencyKey, ...payload } = command
  const response = await apiClient.post<CommandResponse>(
    `/api/mobile/v1/workspaces/${workspaceId}/work-items/${workItemId}/commands`,
    payload,
    {
      baseURL: '',
      headers: { 'Idempotency-Key': idempotencyKey },
    },
  )
  return response.data
}

export async function uploadAgentImage(
  workspaceId: string,
  file: File,
): Promise<ImageAsset> {
  const form = new FormData()
  form.append('file', file)
  const response = await apiClient.post<ImageAsset>(
    `/api/mobile/v1/workspaces/${workspaceId}/assets/images`,
    form,
    { baseURL: '' },
  )
  return response.data
}

export async function transcribeAgentAudio(
  workspaceId: string,
  file: File,
  durationMs: number,
  idempotencyKey: string,
): Promise<{ asset_id: string; transcript: string; language: string }> {
  const form = new FormData()
  form.append('duration_ms', String(Math.max(0, Math.round(durationMs))))
  form.append('file', file)
  const response = await apiClient.post<{
    asset_id: string
    transcript: string
    language: string
  }>(`/api/mobile/v1/workspaces/${workspaceId}/audio/transcriptions`, form, {
    baseURL: '',
    headers: { 'Idempotency-Key': idempotencyKey },
  })
  return response.data
}

export async function submitAgentTurn(
  workspaceId: string,
  payload: AgentTurnPayload,
  idempotencyKey: string,
): Promise<AgentTurnResponse> {
  const response = await apiClient.post<AgentTurnResponse>(
    `/api/mobile/v1/workspaces/${workspaceId}/agent-turns`,
    payload,
    {
      baseURL: '',
      headers: { 'Idempotency-Key': idempotencyKey },
    },
  )
  return response.data
}

export async function getAgentTurn(
  workspaceId: string,
  turnId: string,
): Promise<AgentTurnDetail> {
  const response = await apiClient.get<AgentTurnDetail>(
    `/api/mobile/v1/workspaces/${workspaceId}/agent-turns/${turnId}`,
    { baseURL: '' },
  )
  return response.data
}
