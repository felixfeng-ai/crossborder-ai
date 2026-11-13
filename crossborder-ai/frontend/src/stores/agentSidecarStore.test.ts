import { beforeEach, describe, expect, it } from 'vitest'
import { useAgentSidecarStore } from './agentSidecarStore'

describe('agent sidecar store', () => {
  beforeEach(() => {
    useAgentSidecarStore.setState({
      isOpen: false,
      context: {
        route: '/app/videos',
        page: '视频工作台',
        details: ['商品图生视频'],
      },
      suppressedDetails: [],
    })
  })

  it('keeps a removed context detail hidden when the page re-registers it', () => {
    useAgentSidecarStore
      .getState()
      .removeContextDetail('商品图生视频')
    expect(useAgentSidecarStore.getState().context.details).toEqual([])

    useAgentSidecarStore.getState().setContext({
      route: '/app/videos',
      page: '视频工作台',
      details: ['商品图生视频', '当前首帧'],
    })

    expect(useAgentSidecarStore.getState().context.details).toEqual([
      '当前首帧',
    ])
  })
})
