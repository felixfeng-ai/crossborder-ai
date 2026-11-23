import apiClient from '@/api/client'

import type { WorkspaceBootstrap } from './workspace-context'

/**
 * App 与 Web 共用同一套 Agent 工作区运行面。
 * Web 通过独立 baseURL 访问，认证和工作区请求头仍由统一 axios 客户端注入。
 */
export async function getWorkspaceBootstrap(): Promise<WorkspaceBootstrap> {
  const response = await apiClient.get<WorkspaceBootstrap>(
    '/api/mobile/v1/bootstrap',
    {
      baseURL: '',
    },
  )
  return response.data
}
