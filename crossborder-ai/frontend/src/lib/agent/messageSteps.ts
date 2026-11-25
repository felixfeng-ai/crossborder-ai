import type { AgentStep } from '@/types'

/**
 * 将 Agent 步骤拆成不同展示区域。
 * 营销方案与选品报告共用 steps[]，但必须走不同组件，避免结构串台。
 */
export function splitAgentMessageSteps(steps: AgentStep[] = []) {
  const planSteps = steps.filter((step) => {
    if (step.action !== 'create_marketing_campaign_plan') return false
    const plan = step.data?.plan
    return (
      plan != null &&
      typeof plan === 'object' &&
      Boolean((plan as { title?: unknown }).title)
    )
  })
  const reportSteps = steps.filter(
    (step) =>
      step.action !== 'create_marketing_campaign_plan' &&
      step.data?.structured != null,
  )
  const policySteps = steps.filter(
    (step) =>
      step.action === 'search_platform_policies' &&
      Array.isArray(step.data?.items),
  )
  const plainSteps = steps.filter(
    (step) =>
      step.data?.structured == null &&
      step.action !== 'search_platform_policies' &&
      step.action !== 'create_marketing_campaign_plan',
  )

  return { planSteps, reportSteps, policySteps, plainSteps }
}
