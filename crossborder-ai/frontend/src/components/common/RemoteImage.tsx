import {
  useEffect,
  useState,
  type ImgHTMLAttributes,
  type ReactNode,
} from 'react'

import { resolveMediaUrl } from '@/lib/apiUrl'

interface RemoteImageProps
  extends Omit<ImgHTMLAttributes<HTMLImageElement>, 'src' | 'onError'> {
  src?: string | null
  fallback?: ReactNode
  onError?: ImgHTMLAttributes<HTMLImageElement>['onError']
}

/** 商品外链图片统一禁止 Referer，兼容 1688 CDN 防盗链并提供失败占位。 */
export default function RemoteImage({
  src,
  fallback = null,
  className,
  alt = '',
  loading = 'lazy',
  decoding = 'async',
  onError,
  ...props
}: RemoteImageProps) {
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    setFailed(false)
  }, [src])

  if (!src || failed) return <>{fallback}</>

  return (
    <img
      {...props}
      src={resolveMediaUrl(src)}
      alt={alt}
      className={className}
      loading={loading}
      decoding={decoding}
      referrerPolicy="no-referrer"
      onError={(event) => {
        setFailed(true)
        onError?.(event)
      }}
    />
  )
}
