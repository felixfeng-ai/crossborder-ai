import { describe, expect, it } from 'vitest'
import {
  MAX_IMAGE_UPLOAD_BYTES,
  imageUploadErrorMessage,
  validateImageUpload,
} from './upload'


describe('image upload diagnostics', () => {
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
})
