import type { AgentWorkspaceMode } from '@/lib/agent/workspace'

export interface AgentConversationSelection {
  scope: string
  id: string
}

interface ResolveAgentConversationIdOptions {
  scope: string
  selection: AgentConversationSelection
  recentConversations: readonly { id: string }[] | undefined
  loadHistory: boolean
  forceNewConversation: boolean
}

/**
 * 对话所属范围必须同时包含工作区和营销活动，避免跨活动复用旧会话。
 */
export function agentConversationScope(
  mode: AgentWorkspaceMode,
  campaignId: string,
): string {
  return `${mode}:${campaignId}`
}

/**
 * 直接派生当前会话 ID，不再让“恢复最近会话”和“新建会话”两个 Effect 竞争。
 */
export function resolveAgentConversationId({
  scope,
  selection,
  recentConversations,
  loadHistory,
  forceNewConversation,
}: ResolveAgentConversationIdOptions): string {
  if (selection.scope === scope && selection.id) {
    return selection.id
  }
  if (forceNewConversation || !loadHistory) {
    return ''
  }
  return recentConversations?.[0]?.id || ''
}
