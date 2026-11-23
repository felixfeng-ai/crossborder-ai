import { writeStoredWorkspaceId } from '@/features/workspace-context/workspace-context'

/**
 * 清空跨账号运行时。这里使用按需导入，避免营销首页提前打包工作区与
 * React Query 缓存代码。
 */
export async function clearSessionRuntime(): Promise<void> {
  writeStoredWorkspaceId(null)
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('veyaship:session-cleared'))
  }
  const [workspaceModule, queryModule] = await Promise.all([
    import('@/features/workspace-context/workspace-context-store'),
    import('@/lib/queryClient'),
  ])
  workspaceModule.useWorkspaceContextStore.getState().clear()
  queryModule.appQueryClient.clear()
}
