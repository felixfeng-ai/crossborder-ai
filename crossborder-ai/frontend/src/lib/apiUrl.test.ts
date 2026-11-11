import { describe, expect, it } from 'vitest'
import { resolveMediaUrl } from './apiUrl'


describe('resolveMediaUrl', () => {
  it('把后端相对素材地址解析到绝对 API 源', () => {
    expect(
      resolveMediaUrl(
        '/api/v1/images/assets/1/file',
        'http://127.0.0.1:8001/api/v1',
        'http://127.0.0.1:5174',
      ),
    ).toBe('http://127.0.0.1:8001/api/v1/images/assets/1/file')
  })

  it('保留同源代理地址和外部图片地址', () => {
    expect(
      resolveMediaUrl(
        '/api/v1/images/assets/1/file',
        '/api/v1',
        'https://veyaship.com',
      ),
    ).toBe('/api/v1/images/assets/1/file')
    expect(
      resolveMediaUrl(
        'https://cdn.example.com/image.webp',
        '/api/v1',
        'https://veyaship.com',
      ),
    ).toBe('https://cdn.example.com/image.webp')
  })
})
