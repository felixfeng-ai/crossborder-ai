import { toErrorMessage } from '@/utils/errorMessage'
import { API_BASE } from '@/api/client'


export const MAX_IMAGE_UPLOAD_BYTES = 12 * 1024 * 1024

const SUPPORTED_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp'])
const SUPPORTED_EXTENSIONS = /\.(jpe?g|png|webp)$/i

interface UploadCandidate {
  name: string
  type: string
  size: number
}

interface UploadErrorShape {
  code?: string
  message?: string
  response?: {
    status?: number
    data?: { detail?: unknown }
  }
}

export function validateImageUpload(file: UploadCandidate): string | null {
  if (file.size <= 0) return '图片文件为空，请重新选择'
  if (file.size > MAX_IMAGE_UPLOAD_BYTES) {
    return '图片超过 12MB 上传限制，请压缩后重试'
  }
  if (!SUPPORTED_TYPES.has(file.type) && !SUPPORTED_EXTENSIONS.test(file.name)) {
    return '仅支持 JPEG、PNG 或 WebP 图片'
  }
  return null
}

export function imageUploadErrorMessage(error: unknown): string {
  const normalized = (error || {}) as UploadErrorShape
  const status = normalized.response?.status
  if (status === 413) {
    return '图片超过服务器上传限制，请压缩到 12MB 以内'
  }
  if (status === 415) {
    return '服务器不支持该图片格式，请转换为 JPEG、PNG 或 WebP'
  }
  if (status === 502 || status === 503 || status === 504) {
    return '图片上传服务暂时不可用，请稍后重试'
  }
  if (normalized.code === 'ECONNABORTED' || normalized.code === 'ETIMEDOUT') {
    return '图片处理超时，请压缩图片后重试'
  }
  if (!normalized.response && normalized.code === 'ERR_NETWORK') {
    return '网络连接失败，请检查网络后重试'
  }
  return toErrorMessage(error, '图片上传失败，请稍后重试')
}

export async function uploadImageFile<T>(file: File): Promise<T> {
  const controller = new AbortController()
  const timeout = globalThis.setTimeout(() => controller.abort(), 60_000)
  const form = new FormData()
  form.append('file', file)
  const token = globalThis.localStorage?.getItem('access_token')

  try {
    let response: Response
    try {
      response = await fetch(`${API_BASE}/images/assets/upload`, {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: form,
        signal: controller.signal,
      })
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') {
        throw { code: 'ETIMEDOUT' }
      }
      throw { code: 'ERR_NETWORK' }
    }

    let body: unknown = null
    try {
      body = await response.json()
    } catch {
      body = null
    }
    if (!response.ok) {
      throw { response: { status: response.status, data: body } }
    }
    return body as T
  } finally {
    globalThis.clearTimeout(timeout)
  }
}
