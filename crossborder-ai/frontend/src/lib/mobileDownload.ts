const MOBILE_APP_VERSION = '1.0.0'
const MOBILE_APP_BUILD_NUMBER = '18'

/**
 * 当前可用的 Android 内测包。
 * 安装包同步到官网静态目录，避免 EAS 临时构建产物过期后二维码失效。
 */
export const DEFAULT_MOBILE_APP_DOWNLOAD_URL =
  `https://veyaship.com/downloads/veyaship-${MOBILE_APP_VERSION}-${MOBILE_APP_BUILD_NUMBER}.apk`

export const MOBILE_APP_BUILD_LABEL =
  `Android 内测版 · ${MOBILE_APP_VERSION} (${MOBILE_APP_BUILD_NUMBER})`

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
