export const WORKSPACE_STORAGE_KEY = 'veyaship.active_workspace_id'
export const WORKSPACE_CACHE_KEY = 'veyaship.workspace_context'

export type WorkspaceRole = 'owner' | 'admin' | 'operator' | 'viewer'

export interface WorkspaceSummary {
  id: string
  name: string
  type: 'personal' | 'team'
  role: WorkspaceRole | string
}

export interface WorkspaceBootstrap {
  user_id: string
  display_name: string
  avatar_url: string | null
  workspaces: WorkspaceSummary[]
  contract_version: string
}

export interface CachedWorkspaceBootstrap {
  bootstrap: WorkspaceBootstrap
  activeWorkspaceId: string | null
}

export function resolveActiveWorkspace(
  workspaces: WorkspaceSummary[],
  preferredWorkspaceId?: string | null,
): WorkspaceSummary | null {
  if (!workspaces.length) return null
  return (
    workspaces.find((workspace) => workspace.id === preferredWorkspaceId) ??
    workspaces[0]
  )
}

export function buildWorkspaceHeaders(
  workspaceId?: string | null,
): Record<string, string> {
  const value = workspaceId?.trim()
  return value ? { 'X-Workspace-Id': value } : {}
}

export function workspaceRoleCanControlAgent(
  role?: string | null,
): boolean {
  return role === 'owner' || role === 'admin'
}

export function readStoredWorkspaceId(): string | null {
  if (typeof window === 'undefined') return null
  return window.localStorage.getItem(WORKSPACE_STORAGE_KEY)
}

export function writeStoredWorkspaceId(workspaceId: string | null): void {
  if (typeof window === 'undefined') return
  if (workspaceId) {
    window.localStorage.setItem(WORKSPACE_STORAGE_KEY, workspaceId)
    return
  }
  window.localStorage.removeItem(WORKSPACE_STORAGE_KEY)
}

export function readCachedWorkspaceBootstrap(): CachedWorkspaceBootstrap | null {
  if (typeof window === 'undefined') return null
  const raw = window.localStorage.getItem(WORKSPACE_CACHE_KEY)
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw) as CachedWorkspaceBootstrap
    if (
      !parsed.bootstrap ||
      !Array.isArray(parsed.bootstrap.workspaces) ||
      !parsed.bootstrap.user_id
    ) {
      return null
    }
    return parsed
  } catch {
    return null
  }
}

export function writeCachedWorkspaceBootstrap(
  value: CachedWorkspaceBootstrap | null,
): void {
  if (typeof window === 'undefined') return
  if (!value) {
    window.localStorage.removeItem(WORKSPACE_CACHE_KEY)
    return
  }
  window.localStorage.setItem(WORKSPACE_CACHE_KEY, JSON.stringify(value))
}

export function workspaceRoleLabel(role?: string | null): string {
  switch (role) {
    case 'owner':
      return '所有者'
    case 'admin':
      return '管理员'
    case 'operator':
      return '运营成员'
    case 'viewer':
      return '只读成员'
    default:
      return '成员'
  }
}

export function workspaceTypeLabel(type?: string | null): string {
  return type === 'team' ? '团队工作区' : '个人工作区'
}
