import { create } from 'zustand'

import {
  readStoredWorkspaceId,
  readCachedWorkspaceBootstrap,
  resolveActiveWorkspace,
  workspaceRoleCanControlAgent,
  writeStoredWorkspaceId,
  writeCachedWorkspaceBootstrap,
  type WorkspaceBootstrap,
  type WorkspaceSummary,
} from './workspace-context'

const cached = readCachedWorkspaceBootstrap()
const cachedActive = resolveActiveWorkspace(
  cached?.bootstrap.workspaces ?? [],
  readStoredWorkspaceId(),
)

interface WorkspaceContextState {
  activeWorkspaceId: string | null
  workspaces: WorkspaceSummary[]
  displayName: string | null
  avatarUrl: string | null
  isReady: boolean
  setBootstrap: (bootstrap: WorkspaceBootstrap) => WorkspaceSummary | null
  setActiveWorkspace: (workspaceId: string) => void
  clear: () => void
}

export const useWorkspaceContextStore = create<WorkspaceContextState>((set) => ({
  activeWorkspaceId: cachedActive?.id ?? null,
  workspaces: cached?.bootstrap.workspaces ?? [],
  displayName: cached?.bootstrap.display_name ?? null,
  avatarUrl: cached?.bootstrap.avatar_url ?? null,
  isReady: Boolean(cachedActive),

  setBootstrap: (bootstrap) => {
    const active = resolveActiveWorkspace(
      bootstrap.workspaces,
      readStoredWorkspaceId(),
    )
    writeStoredWorkspaceId(active?.id ?? null)
    writeCachedWorkspaceBootstrap({
      bootstrap,
      activeWorkspaceId: active?.id ?? null,
    })
    set({
      workspaces: bootstrap.workspaces,
      activeWorkspaceId: active?.id ?? null,
      displayName: bootstrap.display_name,
      avatarUrl: bootstrap.avatar_url,
      isReady: true,
    })
    return active
  },

  setActiveWorkspace: (workspaceId) => {
    writeStoredWorkspaceId(workspaceId)
    const cachedBootstrap = readCachedWorkspaceBootstrap()
    if (cachedBootstrap) {
      writeCachedWorkspaceBootstrap({
        ...cachedBootstrap,
        activeWorkspaceId: workspaceId,
      })
    }
    set({ activeWorkspaceId: workspaceId })
  },

  clear: () => {
    writeStoredWorkspaceId(null)
    writeCachedWorkspaceBootstrap(null)
    set({
      activeWorkspaceId: null,
      workspaces: [],
      displayName: null,
      avatarUrl: null,
      isReady: false,
    })
  },
}))

export function activeWorkspaceRole(
  workspaces: WorkspaceSummary[],
  activeWorkspaceId: string | null,
): string | null {
  return (
    workspaces.find((workspace) => workspace.id === activeWorkspaceId)?.role ??
    null
  )
}

export function canControlActiveWorkspaceAgent(
  workspaces: WorkspaceSummary[],
  activeWorkspaceId: string | null,
): boolean {
  return workspaceRoleCanControlAgent(
    activeWorkspaceRole(workspaces, activeWorkspaceId),
  )
}
