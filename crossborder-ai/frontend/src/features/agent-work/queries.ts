import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  getDailyPlan,
  getAgentTurn,
  getTimeline,
  getWorkItem,
  submitAgentTurn,
  submitWorkItemCommand,
  transcribeAgentAudio,
  uploadAgentImage,
} from './api'
import type { WorkItemCommandInput } from './types'
import type { AgentTurnPayload } from './composer'
import { buildWorkItemCommand } from './work-item'
import type { WorkItemDetail } from './types'

export function useDailyPlanQuery(workspaceId: string | null) {
  return useQuery({
    queryKey: ['agent-work', 'daily-plan', workspaceId],
    enabled: Boolean(workspaceId),
    staleTime: 30_000,
    refetchInterval: 60_000,
    queryFn: () => getDailyPlan(workspaceId!),
  })
}

export function useTimelineQuery(workspaceId: string | null) {
  return useQuery({
    queryKey: ['agent-work', 'timeline', workspaceId],
    enabled: Boolean(workspaceId),
    staleTime: 10_000,
    refetchInterval: 15_000,
    queryFn: () => getTimeline(workspaceId!),
  })
}

export function useWorkItemQuery(
  workspaceId: string | null,
  workItemId: string,
) {
  return useQuery({
    queryKey: ['agent-work', 'work-item', workspaceId, workItemId],
    enabled: Boolean(workspaceId && workItemId),
    staleTime: 5_000,
    refetchInterval: 10_000,
    queryFn: () => getWorkItem(workspaceId!, workItemId),
  })
}

export function useConfirmWorkItemMutation(
  workspaceId: string | null,
  item: WorkItemDetail | undefined,
) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (input: WorkItemCommandInput) => {
      if (!workspaceId || !item) {
        throw new Error('工作项尚未同步，不能提交操作')
      }
      return submitWorkItemCommand(
        workspaceId,
        item.id,
        buildWorkItemCommand(item, input),
      )
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: ['agent-work', 'timeline', workspaceId],
        }),
        queryClient.invalidateQueries({
          queryKey: ['agent-work', 'daily-plan', workspaceId],
        }),
        queryClient.invalidateQueries({
          queryKey: ['agent-work', 'work-item', workspaceId, item?.id],
        }),
      ])
    },
  })
}

export function createOperationIdempotencyKey(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`
}

export function useUploadAgentImageMutation(workspaceId: string | null) {
  return useMutation({
    mutationFn: (file: File) => uploadAgentImage(workspaceId!, file),
  })
}

export function useTranscribeAgentAudioMutation(workspaceId: string | null) {
  return useMutation({
    mutationFn: (input: {
      file: File
      durationMs: number
      idempotencyKey: string
    }) =>
      transcribeAgentAudio(
        workspaceId!,
        input.file,
        input.durationMs,
        input.idempotencyKey,
      ),
  })
}

export function useSubmitAgentTurnMutation(workspaceId: string | null) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: {
      payload: AgentTurnPayload
      idempotencyKey: string
    }) => submitAgentTurn(workspaceId!, input.payload, input.idempotencyKey),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: ['agent-work', 'timeline', workspaceId],
        }),
        queryClient.invalidateQueries({
          queryKey: ['agent-work', 'daily-plan', workspaceId],
        }),
      ])
    },
  })
}

export function useAgentTurnQuery(
  workspaceId: string | null,
  turnId: string | null,
) {
  return useQuery({
    queryKey: ['agent-work', 'agent-turn', workspaceId, turnId],
    enabled: Boolean(workspaceId && turnId),
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status && ['succeeded', 'failed', 'cancelled'].includes(status)
        ? false
        : 2_000
    },
    queryFn: () => getAgentTurn(workspaceId!, turnId!),
  })
}
