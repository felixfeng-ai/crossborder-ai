import { useRef, useState } from 'react'
import {
  Camera,
  Laptop,
  Loader2,
  LogOut,
  ShieldCheck,
  Smartphone,
  Trash2,
} from 'lucide-react'

import ConfirmDialog from '@/components/common/ConfirmDialog'
import { UserAvatar } from '@/components/account/UserAvatar'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import {
  useAgentControlQuery,
  useDeviceSessionsQuery,
  useLogoutAllDevicesMutation,
  useRemoveAvatarMutation,
  useSetAgentPausedMutation,
  useUploadAvatarMutation,
} from '@/features/account/queries'
import { useAuthStore } from '@/stores/authStore'
import {
  activeWorkspaceRole,
  useWorkspaceContextStore,
} from '@/features/workspace-context/workspace-context-store'
import {
  workspaceRoleCanControlAgent,
  workspaceRoleLabel,
} from '@/features/workspace-context/workspace-context'

export function AccountSecurityPanel() {
  const user = useAuthStore((state) => state.user)
  const loadUser = useAuthStore((state) => state.loadUser)
  const logout = useAuthStore((state) => state.logout)
  const workspaceId = useWorkspaceContextStore(
    (state) => state.activeWorkspaceId,
  )
  const workspaceDisplayName = useWorkspaceContextStore(
    (state) => state.displayName,
  )
  const workspaceAvatarUrl = useWorkspaceContextStore(
    (state) => state.avatarUrl,
  )
  const workspaces = useWorkspaceContextStore((state) => state.workspaces)
  const role = activeWorkspaceRole(workspaces, workspaceId)
  const canControl = workspaceRoleCanControlAgent(role)
  const control = useAgentControlQuery(workspaceId)
  const setPaused = useSetAgentPausedMutation(workspaceId)
  const sessions = useDeviceSessionsQuery()
  const logoutAll = useLogoutAllDevicesMutation()
  const uploadAvatar = useUploadAvatarMutation()
  const removeAvatar = useRemoveAvatarMutation()
  const fileInput = useRef<HTMLInputElement>(null)
  const [message, setMessage] = useState('')
  const [avatarError, setAvatarError] = useState('')
  const [securityError, setSecurityError] = useState('')
  const [confirmLogoutAll, setConfirmLogoutAll] = useState(false)
  const displayUser =
    user ??
    (workspaceDisplayName
      ? {
          username: workspaceDisplayName,
          avatar_url: workspaceAvatarUrl,
        }
      : null)

  const handleAvatar = async (file?: File) => {
    if (!file) return
    setAvatarError('')
    setMessage('')
    try {
      await uploadAvatar.mutateAsync(file)
      await loadUser()
      setMessage('头像已更新')
    } catch {
      setAvatarError('头像没有上传成功，原头像保持不变')
    } finally {
      if (fileInput.current) fileInput.current.value = ''
    }
  }

  const handleRemoveAvatar = async () => {
    setAvatarError('')
    setMessage('')
    try {
      await removeAvatar.mutateAsync()
      await loadUser()
      setMessage('头像已移除')
    } catch {
      setAvatarError('头像没有移除，请稍后重试')
    }
  }

  const handleLogoutAll = async () => {
    setSecurityError('')
    try {
      await logoutAll.mutateAsync()
      logout()
    } catch {
      setSecurityError('没有退出全部设备，请检查网络后重试')
      setConfirmLogoutAll(false)
    }
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Camera className="h-4 w-4" />
            账号资料
          </CardTitle>
          <CardDescription>
            头像和名称会同步到 App、Agent 对话和 Web 工作台。
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap items-center gap-4">
            <UserAvatar
              user={displayUser}
              className="h-16 w-16 text-xl"
            />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium">
                {user?.username ||
                  user?.full_name ||
                  workspaceDisplayName ||
                  '未命名用户'}
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                {user?.email}
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                当前角色：{workspaceRoleLabel(role)}
              </p>
            </div>
            <input
              ref={fileInput}
              type="file"
              accept="image/jpeg,image/png,image/webp"
              className="hidden"
              onChange={(event) => void handleAvatar(event.target.files?.[0])}
            />
            <div className="flex gap-2">
              <Button
                size="sm"
                variant="outline"
                disabled={uploadAvatar.isPending}
                onClick={() => fileInput.current?.click()}
              >
                {uploadAvatar.isPending ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Camera className="mr-2 h-4 w-4" />
                )}
                更换头像
              </Button>
              {(user?.avatar_url || workspaceAvatarUrl) && (
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={removeAvatar.isPending}
                  onClick={() => void handleRemoveAvatar()}
                >
                  <Trash2 className="mr-2 h-4 w-4" />
                  移除
                </Button>
              )}
            </div>
          </div>
          {(avatarError || message) && (
            <p
              className={`mt-3 text-xs ${
                avatarError
                  ? 'text-[var(--factory-coral)]'
                  : 'text-[var(--factory-mint)]'
              }`}
            >
              {avatarError || message}
            </p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <ShieldCheck className="h-4 w-4" />
            Agent 值守
          </CardTitle>
          <CardDescription>
            暂停后 Agent 不再执行新的自动动作，等待确认的任务仍可查看。
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <p className="text-sm font-medium">
                {control.data?.paused ? 'Agent 已暂停' : 'Agent 在线值守'}
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                {control.data?.paused
                  ? `已冻结 ${control.data.frozen_action_count} 个动作`
                  : canControl
                    ? '有权暂停和恢复当前工作区的 Agent'
                    : '当前角色只能查看状态'}
              </p>
            </div>
            <button
              type="button"
              role="switch"
              aria-checked={!control.data?.paused}
              aria-label="Agent 值守开关"
              disabled={
                !canControl ||
                control.isLoading ||
                control.isError ||
                setPaused.isError ||
                setPaused.isPending
              }
              onClick={() =>
                setPaused.mutate(!Boolean(control.data?.paused))
              }
              className={`relative h-7 w-12 shrink-0 rounded-full border transition-colors ${
                !control.data?.paused
                  ? 'border-[var(--factory-accent)] bg-[var(--factory-accent)]'
                  : 'border-border bg-muted'
              } disabled:cursor-not-allowed disabled:opacity-50`}
            >
              <span
                className={`absolute top-1 h-5 w-5 rounded-full bg-background transition-transform ${
                  !control.data?.paused ? 'translate-x-5' : 'translate-x-1'
                }`}
              />
            </button>
          </div>
          {(control.isError || setPaused.isError) && (
            <p className="mt-3 text-xs text-[var(--factory-coral)]">
              Agent 值守状态暂时无法同步，当前不会允许修改。
            </p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Laptop className="h-4 w-4" />
            登录设备
          </CardTitle>
          <CardDescription>
            检查仍然有效的设备会话。退出全部设备会同时结束当前登录。
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {sessions.isError ? (
            <div className="flex items-center justify-between gap-3 text-xs text-[var(--factory-coral)]">
              <span>设备会话暂时无法同步</span>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => void sessions.refetch()}
              >
                重试
              </Button>
            </div>
          ) : sessions.isLoading ? (
            <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
          ) : sessions.data?.length ? (
            sessions.data.slice(0, 8).map((session) => (
              <div
                key={session.id}
                className="flex items-center justify-between gap-3 border-b border-border pb-3 last:border-b-0 last:pb-0"
              >
                <div className="flex min-w-0 items-center gap-3">
                  {session.platform === 'android' ||
                  session.platform === 'ios' ? (
                    <Smartphone className="h-4 w-4 text-muted-foreground" />
                  ) : (
                    <Laptop className="h-4 w-4 text-muted-foreground" />
                  )}
                  <div className="min-w-0">
                    <p className="truncate text-sm">
                      {session.device_name || session.platform || '未知设备'}
                    </p>
                    <p className="mt-0.5 text-[11px] text-muted-foreground">
                      最近使用{' '}
                      {new Date(session.last_used_at).toLocaleString('zh-CN')}
                    </p>
                  </div>
                </div>
                {session.current && (
                  <Badge variant="success" className="text-[11px]">
                    当前设备
                  </Badge>
                )}
              </div>
            ))
          ) : (
            <p className="py-4 text-sm text-muted-foreground">
              没有可显示的有效设备会话。
            </p>
          )}
          <Button
            variant="outline"
            className="mt-2 w-full"
            disabled={logoutAll.isPending}
            onClick={() => setConfirmLogoutAll(true)}
          >
            <LogOut className="mr-2 h-4 w-4" />
            退出全部设备
          </Button>
          {securityError && (
            <p className="text-xs text-[var(--factory-coral)]">
              {securityError}
            </p>
          )}
        </CardContent>
      </Card>

      <ConfirmDialog
        open={confirmLogoutAll}
        title="退出全部设备？"
        description="所有手机、浏览器和当前 Web 会话都会失效，需要重新登录。"
        confirmLabel="退出全部设备"
        pending={logoutAll.isPending}
        destructive
        onCancel={() => setConfirmLogoutAll(false)}
        onConfirm={() => void handleLogoutAll()}
      />
    </div>
  )
}
