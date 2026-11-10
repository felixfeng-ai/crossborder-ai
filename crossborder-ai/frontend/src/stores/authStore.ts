// ============================================================================
// VeyaShip - Auth State (Zustand)
// ============================================================================

import { create } from 'zustand'
import type { User } from '@/types'
import { authApi } from '@/api/auth'
import { toErrorMessage } from '@/utils/errorMessage'

interface AuthStore {
  user: User | null
  token: string | null
  isAuthenticated: boolean
  isLoading: boolean
  error: string | null

  login: (email: string, password: string) => Promise<void>
  register: (data: {
    email: string
    username: string
    password: string
    full_name?: string
    company_name?: string
  }) => Promise<void>
  logout: () => void
  loadUser: () => Promise<void>
  clearError: () => void
}

export const useAuthStore = create<AuthStore>((set, get) => ({
  user: null,
  token: localStorage.getItem('access_token'),
  isAuthenticated: !!localStorage.getItem('access_token'),
  isLoading: false,
  error: null,

  login: async (email: string, password: string) => {
    set({ isLoading: true, error: null })
    try {
      const response = await authApi.login({ email, password })
      localStorage.setItem('access_token', response.access_token)
      set({
        token: response.access_token,
        isAuthenticated: true,
        isLoading: false,
      })
      await get().loadUser()
    } catch (err: any) {
      const message = toErrorMessage(err, '登录失败，请稍后重试')
      set({ isLoading: false, error: message })
      throw new Error(message)
    }
  },

  register: async (data) => {
    set({ isLoading: true, error: null })
    try {
      const response = await authApi.register(data)
      localStorage.setItem('access_token', response.access_token)
      set({
        token: response.access_token,
        isAuthenticated: true,
        isLoading: false,
      })
      await get().loadUser()
    } catch (err: any) {
      const message = toErrorMessage(err, '注册失败，请稍后重试')
      set({ isLoading: false, error: message })
      throw new Error(message)
    }
  },

  logout: () => {
    localStorage.removeItem('access_token')
    set({
      user: null,
      token: null,
      isAuthenticated: false,
      error: null,
    })
  },

  loadUser: async () => {
    if (!get().token) return
    set({ isLoading: true })
    try {
      const user = await authApi.getMe()
      set({ user, isLoading: false })
    } catch (err: any) {
      // 只有 401（token 失效）才登出
      // 网络错误、后端重启等情况保留登录状态
      if (err?.response?.status === 401) {
        get().logout()
      } else {
        set({ isLoading: false })
      }
    }
  },

  clearError: () => set({ error: null }),
}))
