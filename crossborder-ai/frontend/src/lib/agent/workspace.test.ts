import { describe, expect, it } from 'vitest'
import {
  AGENT_WORKSPACES,
  agentWorkspaceCopy,
} from './workspace'

describe('agent workspaces', () => {
  it('uses the AI decision assistant name and execution-aware intro', () => {
    expect(AGENT_WORKSPACES.general.label).toBe('AI 决策助手')
    expect(AGENT_WORKSPACES.general.intro).toContain('先判断')
    expect(AGENT_WORKSPACES.general.intro).toContain('执行')
  })

  it('provides a dedicated marketing workspace', () => {
    expect(AGENT_WORKSPACES.marketing.label).toBe('营销 Agent')
    expect(AGENT_WORKSPACES.marketing.actions.map((item) => item.label)).toEqual([
      '营销方案',
      '商品主图',
      '场景营销图',
      '营销视频',
      '广告文案',
    ])
  })

  it('keeps general and marketing copy separate', () => {
    expect(agentWorkspaceCopy('general').placeholder).toContain('1688')
    expect(agentWorkspaceCopy('marketing').placeholder).toContain('营销')
    expect(agentWorkspaceCopy('marketing').footer).toContain('营销图片')
  })
})
