import { FileSearch, ImageOff, ShieldAlert } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import {
  coverageLabel,
  ipRiskLabel,
  type IpRiskReport,
} from '@/lib/ipRisk'

export function IpRiskCard({ report }: { report: IpRiskReport | null | undefined }) {
  if (!report) return null

  const badgeVariant =
    report.overall_risk === 'high'
      ? 'destructive'
      : report.overall_risk === 'medium'
        ? 'outline'
        : report.overall_risk === 'low'
          ? 'secondary'
          : 'outline'

  return (
    <div className="border border-border bg-background p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="flex items-center gap-2 text-sm font-medium">
            <ShieldAlert className="h-4 w-4 text-[var(--factory-coral)]" />
            IP 风险初筛
          </p>
          <p className="mt-1 text-[10px] leading-4 text-muted-foreground">
            这是风险初筛，不构成侵权判断或法律意见。
          </p>
        </div>
        <Badge variant={badgeVariant}>{ipRiskLabel(report.overall_risk)}</Badge>
      </div>

      <div className="mt-3 flex flex-wrap gap-2 text-[10px]">
        <Badge variant="outline" className="gap-1">
          <FileSearch className="h-3 w-3" />
          文本：{coverageLabel(report.coverage.text)}
        </Badge>
        <Badge variant="outline" className="gap-1">
          <ImageOff className="h-3 w-3" />
          图片：{coverageLabel(report.coverage.image)}
        </Badge>
        <span className="text-muted-foreground">
          规则版本 {report.ruleset_version}
        </span>
      </div>

      {report.status === 'partial' && (
        <p className="mt-3 border-l-2 border-amber-500 pl-2 text-[10px] leading-4 text-muted-foreground">
          报告为部分完成。未检查的项目不能视为已经通过。
        </p>
      )}

      <div className="mt-3 space-y-2">
        {report.risks.length ? (
          report.risks.slice(0, 8).map((risk, index) => (
            <div
              key={`${risk.code}-${risk.evidence.field || ''}-${risk.evidence.start || index}`}
              className="border border-border px-3 py-2"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-[11px] font-medium">{risk.code}</p>
                <Badge
                  variant={
                    risk.severity === 'high'
                      ? 'destructive'
                      : risk.severity === 'medium'
                        ? 'outline'
                        : 'secondary'
                  }
                >
                  {ipRiskLabel(risk.severity)}
                </Badge>
              </div>
              {risk.evidence.field && (
                <p className="mt-1 text-[9px] text-muted-foreground">
                  {risk.evidence.field}
                  {risk.evidence.text ? `：${risk.evidence.text}` : ''}
                </p>
              )}
              <p className="mt-1 text-[10px] leading-4 text-foreground">
                {risk.suggestion}
              </p>
            </div>
          ))
        ) : (
          <p className="text-[10px] text-muted-foreground">
            本次文本检查未发现需要展示的 IP 风险。
          </p>
        )}
      </div>
    </div>
  )
}
