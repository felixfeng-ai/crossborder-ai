import apiClient from './client'
import type { Product, ProductListResponse } from '@/types'

export const productsApi = {
  list: async (params?: {
    search?: string
    category?: string
    is_active?: boolean
    page?: number
    page_size?: number
  }): Promise<ProductListResponse> => {
    const response = await apiClient.get('/products', { params })
    return response.data
  },

  getById: async (id: string): Promise<Product> => {
    const response = await apiClient.get(`/products/${id}`)
    return response.data
  },

  delete: async (id: string): Promise<void> => {
    await apiClient.delete(`/products/${id}`)
  },
}
