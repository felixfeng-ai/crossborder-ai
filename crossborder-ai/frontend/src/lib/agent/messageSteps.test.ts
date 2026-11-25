import { describe, expect, it } from 'vitest'

import type { AgentStep } from '@/types'

import { splitAgentMessageSteps } from './messageSteps'

function step(
  action: string,
  data?: AgentStep['data'],
): AgentStep {
  return {
    action,
    status: 'success',
    data,
  }
}

describe('agent message step routing', () => {
  it('keeps marketing plans separate from product reports', () => {
    const marketingPlan = step('create_marketing_campaign_plan', {
      plan: { title: '宠物智能床营销方案' },
    })
    const selectionReport = step('select_products', {
      structured: {
        market: { active_listings: 20 },
        products: [],
      },
    })

    const result = splitAgentMessageSteps([
      marketingPlan,
      selectionReport,
      step('generate_product_video'),
    ])

    expect(result.planSteps).toEqual([marketingPlan])
    expect(result.reportSteps).toEqual([selectionReport])
    expect(result.plainSteps.map((item) => item.action)).toEqual([
      'generate_product_video',
    ])
  })

  it('keeps policy evidence out of plain execution steps', () => {
    const policy = step('search_platform_policies', {
      items: [{ title: 'Policy' }],
    })

    const result = splitAgentMessageSteps([policy])

    expect(result.policySteps).toEqual([policy])
    expect(result.plainSteps).toEqual([])
  })
})
