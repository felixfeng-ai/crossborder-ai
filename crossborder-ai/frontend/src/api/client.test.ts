import { AxiosHeaders } from 'axios'
import { describe, expect, it } from 'vitest'
import apiClient, { normalizeFormDataHeaders } from './client'


describe('multipart request headers', () => {
  it('API 客户端不再全局强制 JSON Content-Type', () => {
    expect(apiClient.defaults.headers.common['Content-Type']).toBeUndefined()
  })

  it('FormData 请求移除全局 JSON Content-Type', () => {
    const headers = new AxiosHeaders({ 'Content-Type': 'application/json' })
    const config = {
      data: new FormData(),
      headers,
    }

    normalizeFormDataHeaders(config as never)

    expect(headers.get('Content-Type')).toBeUndefined()
  })

  it('普通 JSON 请求保留 Content-Type', () => {
    const headers = new AxiosHeaders({ 'Content-Type': 'application/json' })
    const config = {
      data: { title: '商品' },
      headers,
    }

    normalizeFormDataHeaders(config as never)

    expect(headers.get('Content-Type')).toBe('application/json')
  })
})
