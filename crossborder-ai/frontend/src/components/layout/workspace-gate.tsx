import type { ReactNode } from 'react'
import { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AlertCircle, Loader2, LogOut, RefreshCw } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { getWorkspaceBootstrap } from '@/features/workspace-context/workspace-api'
import { useWorkspaceContextStore } from '@/features/workspace-context/workspace-context-store'
import { useAuthStore } from '@/stores/authStore'

export function WorkspaceGate({ children }: { children: ReactNode }) {
  const token = useAuthStore((state) => state.token)
  const logout = useAuthStore((state) => state.logout)
  const setBootstrap = useWorkspaceContextStore((state) => state.setBootstrap)
  const clearWorkspace = useWorkspaceContextStore((state) => state.clear)
  const isReady = useWorkspaceContextStore((state) => state.isReady)
  const activeWorkspaceId = useWorkspaceContextStore(
    (state) => state.activeWorkspaceId,
  )

  const bootstrap = useQuery({
    queryKey: ['workspace-bootstrap', token],
    queryFn: getWorkspaceBootstrap,
    enabled: Boolean(token),
    retry: 1,
    staleTime: 30_000,
  })

  useEffect(() => {
    if (bootstrap.data) setBootstrap(bootstrap.data)
  }, [bootstrap.data, setBootstrap])

  if (!bootstrap.isError && !isReady && !activeWorkspaceId) {
    return (
      <div className="flex min-h-[100dvh] items-center justify-center bg-[var(--factory-ground)] px-6">
        <div className="flex items-center gap-3 border border-border bg-[var(--factory-panel)] px-5 py-4 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin text-[var(--factory-accent)]" />
          正在同步工作区
        </div>
      </div>
    )
  }

  if (bootstrap.isError && !isReady && !activeWorkspaceId) {
    return (
      <div className="flex min-h-[100dvh] items-center justify-center bg-[var(--factory-ground)] px-6">
        <div className="w-full max-w-md border border-border bg-[var(--factory-panel)] p-6">
          <AlertCircle className="h-5 w-5 text-[var(--factory-coral)]" />
          <h1 className="mt-4 text-lg font-semibold">工作区暂时无法同步</h1>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            当前不会加载商品、任务或 Agent 数据，避免在错误的工作区执行操作。
          </p>
          <div className="mt-5 flex flex-wrap gap-2">
            <Button onClick={() => void bootstrap.refetch()}>
              <RefreshCw className="mr-2 h-4 w-4" />
              重新加载
            </Button>
            <Button
              variant="outline"
              onClick={() => {
                clearWorkspace()
                logout()
              }}
            >
              <LogOut className="mr-2 h-4 w-4" />
              退出登录
            </Button>
          </div>
        </div>
      </div>
    )
  }

  return <>{children}</>
}
