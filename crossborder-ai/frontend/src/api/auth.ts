// ============================================================================
// VeyaShip - Auth API
// ============================================================================

import apiClient, { API_BASE } from './client'
import type {
  LoginRequest,
  RegisterRequest,
  TokenResponse,
  User,
} from '@/types'

export const authApi = {
  login: async (data: LoginRequest): Promise<TokenResponse> => {
    const response = await apiClient.post('/auth/login', data)
    return response.data
  },

  register: async (data: RegisterRequest): Promise<TokenResponse> => {
    const response = await apiClient.post('/auth/register', data)
    return response.data
  },

  getMe: async (): Promise<User> => {
    const response = await apiClient.get('/auth/me')
    return response.data
  },

  logout: async (
    accessToken: string,
    refreshToken?: string | null,
  ): Promise<void> => {
    // 使用不经过 Axios 拦截器的请求，确保退出本地会话前明确撤销服务端设备会话。
    const requestLogout = (token: string) =>
      fetch(`${API_BASE}/auth/logout`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'X-Device-Platform': 'web',
          'X-Device-Name': 'Web Browser',
          'X-Client-Version': 'web-1.0.0',
        },
      })

    const response = await requestLogout(accessToken)
    if (response.status !== 401 || !refreshToken) return

    // 访问令牌过期时先用仍在有效期的 refresh token 恢复一次，再撤销同一设备会话。
    const refreshResponse = await fetch(`${API_BASE}/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    })
    if (!refreshResponse.ok) return
    const rotated = (await refreshResponse.json()) as {
      access_token?: string
    }
    if (!rotated.access_token) return
    await requestLogout(rotated.access_token)
  },
}
