/**
 * 当前可用的 Android 内测包。
 * 正式分发前通过 VITE_MOBILE_APP_DOWNLOAD_URL 指向官网稳定下载地址，
 * 避免 EAS 临时构建产物过期后二维码失效。
 */
export const DEFAULT_MOBILE_APP_DOWNLOAD_URL =
  'https://expo.dev/artifacts/eas/bKteV0OXlh1tOtesB0X4C3AEb3qz5P64R0TRCu3FnI8.apk'

export const MOBILE_APP_BUILD_LABEL = 'Android 内测版 · 1.0.0 (16)'

export function resolveMobileDownloadUrl(configured?: string): string {
  const value = configured?.trim()
  if (!value) return DEFAULT_MOBILE_APP_DOWNLOAD_URL

  try {
    const url = new URL(value)
    // 安装包必须通过 HTTPS 分发，避免内网地址或 http 链接进入二维码。
    return url.protocol === 'https:' ? url.toString() : DEFAULT_MOBILE_APP_DOWNLOAD_URL
  } catch {
    return DEFAULT_MOBILE_APP_DOWNLOAD_URL
  }
}

export const MOBILE_APP_DOWNLOAD_URL = resolveMobileDownloadUrl(
  import.meta.env.VITE_MOBILE_APP_DOWNLOAD_URL,
)
