import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  MAX_IMAGE_UPLOAD_BYTES,
  imageUploadErrorMessage,
  uploadImageFile,
  validateImageUpload,
} from './upload'


describe('image upload diagnostics', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('上传前拦截大小和格式问题', () => {
    expect(
      validateImageUpload({
        name: 'huge.png',
        type: 'image/png',
        size: MAX_IMAGE_UPLOAD_BYTES + 1,
      }),
    ).toContain('12MB')
    expect(
      validateImageUpload({
        name: 'manual.pdf',
        type: 'application/pdf',
        size: 1000,
      }),
    ).toContain('JPEG')
    expect(
      validateImageUpload({
        name: 'product.webp',
        type: 'image/webp',
        size: 1000,
      }),
    ).toBeNull()
  })

  it('把网关与网络错误翻译成明确原因', () => {
    expect(imageUploadErrorMessage({ response: { status: 413 } })).toContain(
      '服务器上传限制',
    )
    expect(imageUploadErrorMessage({ response: { status: 415 } })).toContain(
      '格式',
    )
    expect(imageUploadErrorMessage({ response: { status: 502 } })).toContain(
      '服务暂时不可用',
    )
    expect(imageUploadErrorMessage({ code: 'ERR_NETWORK' })).toContain(
      '网络',
    )
  })

  it('优先展示后端中文业务错误', () => {
    expect(
      imageUploadErrorMessage({
        response: {
          status: 400,
          data: { detail: '无法识别图片，请上传 JPEG、PNG 或 WebP 文件' },
        },
      }),
    ).toBe('无法识别图片，请上传 JPEG、PNG 或 WebP 文件')
  })

  it('使用 XHR 发送 multipart 并报告上传进度', async () => {
    const progress: number[] = []
    class MockXHR {
      upload = {}
      status = 201
      responseText = JSON.stringify({ id: 'asset-1', name: '素材2' })
      timeout = 0
      onload: (() => void) | null = null
      onerror: (() => void) | null = null
      ontimeout: (() => void) | null = null
      open() {}
      setRequestHeader(key: string, value: string) {
        expect(key).toBe('Authorization')
        expect(value).toBe('Bearer test-token')
      }
      abort() {}
      send(body: unknown) {
        expect(body).toBeInstanceOf(FormData)
        ;(this.upload as { onprogress?: (event: ProgressEvent) => void }).onprogress?.({
          lengthComputable: true,
          loaded: 50,
          total: 100,
        } as ProgressEvent)
        this.onload?.()
      }
    }
    vi.stubGlobal('XMLHttpRequest', MockXHR)
    vi.stubGlobal('localStorage', {
      getItem: (key: string) => key === 'access_token' ? 'test-token' : null,
    })
    const file = new File([new Uint8Array([1, 2, 3])], '素材2.jpg', {
      type: 'image/jpeg',
    })

    const result = await uploadImageFile<{ id: string; name: string }>(
      file,
      { onProgress: (value) => progress.push(value) },
    )

    expect(result).toEqual({ id: 'asset-1', name: '素材2' })
    expect(progress).toEqual([50, 100])
  })
})
