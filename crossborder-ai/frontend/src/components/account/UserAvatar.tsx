import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'

import { fetchMyAvatar } from '@/features/account/api'
import { avatarInitial } from '@/features/account/avatar'
import { cn } from '@/utils/cn'

interface UserAvatarProps {
  user: {
    id?: number | string
    username?: string | null
    full_name?: string | null
    email?: string | null
    avatar_url?: string | null
  } | null
  className?: string
  imageClassName?: string
}

export function UserAvatar({
  user,
  className,
  imageClassName,
}: UserAvatarProps) {
  const [objectUrl, setObjectUrl] = useState<string | null>(null)
  const avatar = useQuery({
    queryKey: ['my-avatar', user?.id ?? 'anonymous', user?.avatar_url],
    queryFn: fetchMyAvatar,
    enabled: Boolean(user?.avatar_url),
    retry: false,
    staleTime: 5 * 60_000,
  })

  useEffect(() => {
    if (!avatar.data) {
      setObjectUrl(null)
      return
    }
    const url = URL.createObjectURL(avatar.data)
    setObjectUrl(url)
    return () => URL.revokeObjectURL(url)
  }, [avatar.data])

  const displayName =
    user?.username || user?.full_name || user?.email || 'U'

  return (
    <span
      className={cn(
        'flex shrink-0 items-center justify-center overflow-hidden rounded-full border border-border bg-[var(--factory-raised)] text-[11px] font-semibold text-foreground',
        className,
      )}
      aria-label={`${displayName} 的头像`}
    >
      {objectUrl ? (
        <img
          src={objectUrl}
          alt=""
          className={cn('h-full w-full object-cover', imageClassName)}
        />
      ) : (
        avatarInitial(displayName)
      )}
    </span>
  )
}
