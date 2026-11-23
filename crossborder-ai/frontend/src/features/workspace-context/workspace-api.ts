import apiClient from '@/api/client'

import type { WorkspaceBootstrap } from './workspace-context'

export const MOBILE_API_BASE =
  import.meta.env.VITE_MOBILE_API_BASE_URL || '/api/mobile/v1'

/**
 * App 与 Web 共用同一套 Agent 工作区运行面。
 * Web 通过独立 baseURL 访问，认证和工作区请求头仍由统一 axios 客户端注入。
 */
export async function getWorkspaceBootstrap(): Promise<WorkspaceBootstrap> {
  const response = await apiClient.get<WorkspaceBootstrap>('/bootstrap', {
    baseURL: MOBILE_API_BASE,
  })
  return response.data
}
