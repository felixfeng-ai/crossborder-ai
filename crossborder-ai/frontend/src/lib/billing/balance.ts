export interface CreditBalanceBreakdown {
  plan_credits: number
  purchased_credits: number
  total_credits: number
}

export function formatCreditTotal(value: number | null | undefined): string {
  const amount = Number.isFinite(Number(value)) ? Math.max(0, Number(value)) : 0
  return amount.toLocaleString('zh-CN')
}

export function creditBreakdownLabel(
  wallet: CreditBalanceBreakdown,
): string {
  return `套餐额度 ${formatCreditTotal(wallet.plan_credits)} + 购买积分 ${formatCreditTotal(wallet.purchased_credits)}`
}
