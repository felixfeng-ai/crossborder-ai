import { describe, expect, it } from 'vitest'

import { toErrorMessage } from './errorMessage'

describe('toErrorMessage', () => {
  it('保留后端中文字符串 detail', () => {
    const error = { response: { data: { detail: '商品不存在' } } }
    expect(toErrorMessage(error)).toBe('商品不存在')
  })

  it('提取 detail 对象里的中文 message', () => {
    const error = {
      response: {
        data: {
          detail: { code: 'invalid_url', message: '仅支持 1688 商品链接' },
        },
      },
    }
    expect(toErrorMessage(error)).toBe('仅支持 1688 商品链接')
  })

  it('提取 FastAPI 422 数组里的中文提示', () => {
    const error = {
      response: {
        data: {
          detail: [
            { loc: ['body', 'url'], msg: '链接格式不正确' },
            { loc: ['body', 'price'], msg: '价格不能为负数' },
          ],
        },
      },
    }
    expect(toErrorMessage(error)).toBe('链接格式不正确')
  })

  it('无中文 detail 时使用业务兜底文案', () => {
    const error = { message: 'Network Error' }
    expect(toErrorMessage(error, '抓取失败，请稍后重试')).toBe('抓取失败，请稍后重试')
  })

  it('过滤含英文技术词的 detail', () => {
    const error = {
      response: {
        data: {
          detail: { message: 'Connection refused by upstream' },
        },
      },
    }
    expect(toErrorMessage(error, '服务暂不可用')).toBe('服务暂不可用')
  })
})
