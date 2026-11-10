// ============================================================================
// VeyaShip - Auth API
// ============================================================================

import apiClient from './client'
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
}
