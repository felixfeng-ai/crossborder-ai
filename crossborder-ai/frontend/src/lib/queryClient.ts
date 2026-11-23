import { QueryClient } from '@tanstack/react-query'

/**
 * 全应用共享同一个 QueryClient，登录态切换时由认证层统一清空，
 * 防止上一个账号的工作区、任务和店铺缓存串入新会话。
 */
export const appQueryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 5 * 60 * 1000,
    },
  },
})
