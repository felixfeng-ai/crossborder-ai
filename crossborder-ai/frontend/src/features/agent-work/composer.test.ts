import { describe, expect, it } from 'vitest'

import {
  buildAgentTurnPayload,
  canSubmitAgentDraft,
  detectAgentInputType,
} from './composer'

describe('cross-surface agent composer', () => {
  it('识别链接并允许纯图片或纯语音提交', () => {
    expect(detectAgentInputType('https://detail.1688.com/offer/1.html', 'text')).toBe(
      'link',
    )
    expect(detectAgentInputType('#1001 查一下物流', 'order')).toBe('text')
    expect(
      canSubmitAgentDraft({
        mode: 'text',
        text: '',
        imageAssetIds: ['asset-1'],
        audioAssetId: null,
        recording: false,
      }),
    ).toBe(true)
    expect(
      canSubmitAgentDraft({
        mode: 'text',
        text: '',
        imageAssetIds: [],
        audioAssetId: 'audio-1',
        recording: false,
      }),
    ).toBe(true)
  })

  it('录音中、空草稿或无效链接不能提交', () => {
    expect(
      canSubmitAgentDraft({
        mode: 'text',
        text: '检查库存',
        imageAssetIds: [],
        audioAssetId: null,
        recording: true,
      }),
    ).toBe(false)
    expect(
      canSubmitAgentDraft({
        mode: 'text',
        text: '   ',
        imageAssetIds: [],
        audioAssetId: null,
        recording: false,
      }),
    ).toBe(false)
    expect(
      canSubmitAgentDraft({
        mode: 'link',
        text: 'not-a-url',
        imageAssetIds: [],
        audioAssetId: null,
        recording: false,
      }),
    ).toBe(false)
  })

  it('构造与 App 相同的 Agent turn 请求', () => {
    expect(
      buildAgentTurnPayload({
        mode: 'link',
        text: ' https://detail.1688.com/offer/1.html ',
        imageAssetIds: [],
        audioAssetId: null,
        recording: false,
      }),
    ).toEqual({
      input_type: 'link',
      text: 'https://detail.1688.com/offer/1.html',
      source_url: 'https://detail.1688.com/offer/1.html',
    })
    expect(
      buildAgentTurnPayload({
        mode: 'text',
        text: '检查这张订单截图',
        imageAssetIds: ['asset-1'],
        audioAssetId: 'audio-1',
        recording: false,
      }),
    ).toEqual({
      input_type: 'image',
      text: '检查这张订单截图',
      asset_ids: ['asset-1'],
      audio_asset_id: 'audio-1',
    })
  })
})
