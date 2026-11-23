// ============================================================================
// VeyaShip - Axios API Client
// ============================================================================

import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios'
import type { ApiError } from '@/types'
import {
  buildWorkspaceHeaders,
  readStoredWorkspaceId,
} from '@/features/workspace-context/workspace-context'
import { clearSessionRuntime } from '@/lib/session-runtime'

export const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api/v1'
export const ACCESS_TOKEN_STORAGE_KEY = 'access_token'
export const REFRESH_TOKEN_STORAGE_KEY = 'refresh_token'

interface RefreshTokenResponse {
  access_token: string
  refresh_token: string
}

interface RetryableRequestConfig extends InternalAxiosRequestConfig {
  _authRetry?: boolean
}

const apiClient = axios.create({
  baseURL: API_BASE,
  timeout: 30000,
})

let refreshPromise: Promise<string | null> | null = null
let sessionEpoch = 0

export function clearStoredAuthTokens() {
  sessionEpoch += 1
  localStorage.removeItem(ACCESS_TOKEN_STORAGE_KEY)
  localStorage.removeItem(REFRESH_TOKEN_STORAGE_KEY)
}

function persistRefreshedTokens(tokens: RefreshTokenResponse) {
  localStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, tokens.access_token)
  localStorage.setItem(REFRESH_TOKEN_STORAGE_KEY, tokens.refresh_token)
  // 页面中的 Zustand 状态也需要换成新令牌，但不要在 API 层直接依赖 store。
  window.dispatchEvent(
    new CustomEvent('veyaship:session-refreshed', {
      detail: { accessToken: tokens.access_token },
    }),
  )
}

/**
 * 同一时刻只允许一个刷新请求。
 * 多个并发 401 共用这一次轮换，避免旧 refresh token 被第二次使用后触发整组会话撤销。
 */
export function refreshAccessToken(): Promise<string | null> {
  if (refreshPromise) return refreshPromise

  const refreshToken = localStorage.getItem(REFRESH_TOKEN_STORAGE_KEY)
  if (!refreshToken) return Promise.resolve(null)
  const requestEpoch = sessionEpoch

  refreshPromise = fetch(`${API_BASE}/auth/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refreshToken }),
  })
    .then(async (response) => {
      if (!response.ok) return null
      const tokens = (await response.json()) as RefreshTokenResponse
      if (!tokens.access_token || !tokens.refresh_token) return null
      // 用户可能在刷新请求返回前退出或切换账号，旧响应不能把会话重新写回来。
      if (
        requestEpoch !== sessionEpoch ||
        localStorage.getItem(REFRESH_TOKEN_STORAGE_KEY) !== refreshToken
      ) {
        return null
      }
      persistRefreshedTokens(tokens)
      return tokens.access_token
    })
    .catch(() => null)
    .finally(() => {
      refreshPromise = null
    })

  return refreshPromise
}

function clearExpiredSession() {
  clearStoredAuthTokens()
  void clearSessionRuntime()
  if (window.location.pathname !== '/login') {
    window.location.href = '/login'
  }
}

export function normalizeFormDataHeaders(
  config: InternalAxiosRequestConfig,
): InternalAxiosRequestConfig {
  // 全局 JSON Content-Type 会让浏览器把 FormData 当普通对象处理，
  // 后端最终收到的是没有 file 字段的 JSON。移除后由浏览器生成 boundary。
  if (typeof FormData !== 'undefined' && config.data instanceof FormData) {
    config.headers.delete('Content-Type')
  }
  return config
}

// --- Request Interceptor: Attach JWT ---
apiClient.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    normalizeFormDataHeaders(config)
    const token = localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY)
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`
    }
    config.headers.set('X-Device-Platform', 'web')
    config.headers.set('X-Device-Name', 'Web Browser')
    config.headers.set('X-Client-Version', 'web-1.0.0')
    if (config.headers) {
      Object.entries(buildWorkspaceHeaders(readStoredWorkspaceId())).forEach(
        ([key, value]) => config.headers.set(key, value),
      )
    }
    return config
  },
  (error) => Promise.reject(error),
)

// --- Response Interceptor: Error Handling & Token Refresh ---
apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<ApiError>) => {
    const originalRequest = error.config as RetryableRequestConfig | undefined

    // 401 处理：
    // 1. 登录/注册接口的 401 是"密码错误"等正常业务错误，必须放行给表单显示，
    //    不能劫持成页面跳转，否则用户看不到"邮箱或密码错误"。
    // 2. 普通接口第一次 401 时先轮换 refresh token，并重放原请求。
    // 3. 刷新失败或重放仍 401 才清除会话，避免 15 分钟访问令牌到期就退出。
    if (error.response?.status === 401 && originalRequest) {
      const url = originalRequest.url || ''
      const isAuthEndpoint =
        url.includes('/auth/login') ||
        url.includes('/auth/register') ||
        url.includes('/auth/refresh') ||
        url.includes('/auth/logout')

      if (!isAuthEndpoint) {
        if (!originalRequest._authRetry) {
          const nextAccessToken = await refreshAccessToken()
          if (nextAccessToken) {
            originalRequest._authRetry = true
            originalRequest.headers.set(
              'Authorization',
              `Bearer ${nextAccessToken}`,
            )
            return apiClient(originalRequest)
          }
        }
        clearExpiredSession()
      }
    }

    return Promise.reject(error)
  },
)

export default apiClient
