export type IpRiskLevel = 'low' | 'medium' | 'high' | 'unknown' | string
export type IpCoverageState = 'checked' | 'not_checked' | 'failed' | string

export interface IpRiskEvidence {
  type: string
  field?: string | null
  text?: string | null
  start?: number | null
  end?: number | null
  asset_id?: string | null
  bbox?: number[] | null
  bbox_format?: string | null
}

export interface IpRiskItem {
  id?: string
  code: string
  category: string
  severity: 'info' | 'low' | 'medium' | 'high' | string
  evidence: IpRiskEvidence
  suggestion: string
  source: string
}

export interface IpRiskReport {
  report_id: string
  status: 'completed' | 'partial' | 'failed' | string
  overall_risk: IpRiskLevel
  coverage: {
    text: IpCoverageState
    image: IpCoverageState
  }
  summary: Record<string, number>
  risks: IpRiskItem[]
  ruleset_version: string
  created_at?: string | null
}

export function ipRiskLabel(risk: IpRiskLevel): string {
  if (risk === 'high') return '高风险'
  if (risk === 'medium') return '中风险'
  if (risk === 'low') return '低风险'
  return '风险未知'
}

export function ipSeverityLabel(severity: string): string {
  if (severity === 'high') return '高风险'
  if (severity === 'medium') return '中风险'
  if (severity === 'low') return '低风险'
  if (severity === 'info') return '提示'
  return '风险未知'
}

export function coverageLabel(value: IpCoverageState): string {
  if (value === 'checked') return '已检查'
  if (value === 'failed') return '检查失败'
  return '未检查'
}

export function isIpPublishBlocked(risk: IpRiskLevel): boolean {
  return risk === 'high'
}
