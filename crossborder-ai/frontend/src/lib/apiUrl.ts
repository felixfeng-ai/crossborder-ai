import { API_BASE } from '@/api/client'


/**
 * 后端素材接口返回 `/api/v1/...`。前端单独部署到其他域名时，
 * 浏览器不能把该地址误解析到静态站点端口，因此统一按 API 源重写。
 */
export function resolveMediaUrl(
  path: string,
  apiBase = API_BASE,
  origin = window.location.origin,
): string {
  if (!path || /^https?:\/\//i.test(path)) return path

  const apiUrl = new URL(apiBase, origin)
  const apiPath = apiUrl.pathname.replace(/\/$/, '')

  if (/^https?:\/\//i.test(apiBase)) {
    if (path === apiPath || path.startsWith(`${apiPath}/`)) {
      return `${apiUrl.origin}${path}`
    }
    if (path.startsWith('/')) return `${apiUrl.origin}${path}`
    return new URL(path, `${apiUrl.origin}/`).toString()
  }

  return path
}
