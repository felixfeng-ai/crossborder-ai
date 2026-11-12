// ============================================================================
// VeyaShip - Axios API Client
// ============================================================================

import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios'
import type { ApiError } from '@/types'

export const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api/v1'

const apiClient = axios.create({
  baseURL: API_BASE,
  timeout: 30000,
})

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
    const token = localStorage.getItem('access_token')
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error),
)

// --- Response Interceptor: Error Handling & Token Refresh ---
apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError<ApiError>) => {
    const originalRequest = error.config

    // 401 处理：
    // 1. 登录/注册接口的 401 是"密码错误"等正常业务错误，必须放行给表单显示，
    //    不能劫持成页面跳转（否则用户看不到"邮箱或密码错误"）。
    // 2. 其余接口 401 = 会话失效，清除本地会话并回登录页。
    if (error.response?.status === 401 && originalRequest) {
      const url = originalRequest.url || ''
      const isAuthEndpoint =
        url.includes('/auth/login') || url.includes('/auth/register')

      if (!isAuthEndpoint) {
        localStorage.removeItem('access_token')
        localStorage.removeItem('refresh_token')
        window.location.href = '/login'
      }
    }

    return Promise.reject(error)
  },
)

export default apiClient
