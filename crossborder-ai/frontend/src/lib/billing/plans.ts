export type PlanAccessState = 'current' | 'included' | 'available'

const PLAN_RANK: Record<string, number> = {
  free: 0,
  standard: 1,
  professional: 2,
}

function rank(plan: string): number {
  return PLAN_RANK[plan] ?? 0
}

export function planAccessState(
  currentPlan: string,
  targetPlan: string,
): PlanAccessState {
  if (rank(targetPlan) === rank(currentPlan)) return 'current'
  if (rank(targetPlan) < rank(currentPlan)) return 'included'
  return 'available'
}
