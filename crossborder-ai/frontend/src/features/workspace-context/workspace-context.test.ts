import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  buildWorkspaceHeaders,
  readCachedWorkspaceBootstrap,
  resolveActiveWorkspace,
  workspaceRoleCanControlAgent,
  workspaceRoleLabel,
  workspaceTypeLabel,
  type WorkspaceSummary,
} from './workspace-context'
import {
  canControlActiveWorkspaceAgent,
  useWorkspaceContextStore,
} from './workspace-context-store'

const workspaces: WorkspaceSummary[] = [
  {
    id: 'personal-workspace',
    name: 'Felix 个人空间',
    type: 'personal',
    role: 'owner',
  },
  {
    id: 'team-workspace',
    name: '跨境运营团队',
    type: 'team',
    role: 'admin',
  },
]

describe('workspace context', () => {
  beforeEach(() => {
    const values = new Map<string, string>()
    vi.stubGlobal('window', {
      localStorage: {
        getItem: (key: string) => values.get(key) ?? null,
        setItem: (key: string, value: string) => values.set(key, value),
        removeItem: (key: string) => values.delete(key),
        clear: () => values.clear(),
      },
    })
    useWorkspaceContextStore.getState().clear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('恢复仍有效的上次工作区，否则回退到第一个可用工作区', () => {
    expect(resolveActiveWorkspace(workspaces, 'team-workspace')?.id).toBe(
      'team-workspace',
    )
    expect(resolveActiveWorkspace(workspaces, 'removed-workspace')?.id).toBe(
      'personal-workspace',
    )
    expect(resolveActiveWorkspace([], 'team-workspace')).toBeNull()
  })

  it('为所有跨端工作请求生成工作区请求头', () => {
    expect(buildWorkspaceHeaders('team-workspace')).toEqual({
      'X-Workspace-Id': 'team-workspace',
    })
    expect(buildWorkspaceHeaders(null)).toEqual({})
    expect(buildWorkspaceHeaders('  ')).toEqual({})
  })

  it('只允许 owner 和 admin 控制 Agent 值守状态', () => {
    expect(workspaceRoleCanControlAgent('owner')).toBe(true)
    expect(workspaceRoleCanControlAgent('admin')).toBe(true)
    expect(workspaceRoleCanControlAgent('operator')).toBe(false)
    expect(workspaceRoleCanControlAgent('viewer')).toBe(false)
    expect(workspaceRoleCanControlAgent(undefined)).toBe(false)
    expect(workspaceRoleLabel('owner')).toBe('所有者')
    expect(workspaceRoleLabel('viewer')).toBe('只读成员')
    expect(workspaceTypeLabel('team')).toBe('团队工作区')
    expect(workspaceTypeLabel('personal')).toBe('个人工作区')
    expect(canControlActiveWorkspaceAgent(workspaces, 'team-workspace')).toBe(
      true,
    )
    expect(
      canControlActiveWorkspaceAgent(
        [{ ...workspaces[0], role: 'viewer' }],
        'personal-workspace',
      ),
    ).toBe(false)
  })

  it('bootstrap 会恢复有效工作区并清除退出后的旧选择', () => {
    window.localStorage.setItem('veyaship.active_workspace_id', 'team-workspace')

    const active = useWorkspaceContextStore.getState().setBootstrap({
      user_id: 'user-1',
      display_name: 'Felix',
      avatar_url: null,
      workspaces,
      contract_version: '1',
    })

    expect(active?.id).toBe('team-workspace')
    expect(useWorkspaceContextStore.getState().activeWorkspaceId).toBe(
      'team-workspace',
    )
    expect(readCachedWorkspaceBootstrap()?.bootstrap.workspaces).toEqual(
      workspaces,
    )

    useWorkspaceContextStore.getState().clear()
    expect(useWorkspaceContextStore.getState().activeWorkspaceId).toBeNull()
    expect(window.localStorage.getItem('veyaship.active_workspace_id')).toBeNull()
    expect(readCachedWorkspaceBootstrap()).toBeNull()
  })

  it('切换工作区后同步写入活动 ID 和缓存选择', () => {
    useWorkspaceContextStore.getState().setBootstrap({
      user_id: 'user-1',
      display_name: 'Felix',
      avatar_url: null,
      workspaces,
      contract_version: '1',
    })
    useWorkspaceContextStore
      .getState()
      .setActiveWorkspace('team-workspace')

    expect(useWorkspaceContextStore.getState().activeWorkspaceId).toBe(
      'team-workspace',
    )
    expect(
      window.localStorage.getItem('veyaship.active_workspace_id'),
    ).toBe('team-workspace')
    expect(readCachedWorkspaceBootstrap()?.activeWorkspaceId).toBe(
      'team-workspace',
    )
  })
})
