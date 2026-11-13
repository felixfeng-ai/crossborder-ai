import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  FileSearch,
  ImageOff,
  Loader2,
  Plus,
  RefreshCw,
  ShieldAlert,
  Trash2,
} from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import apiClient from '@/api/client'
import {
  coverageLabel,
  ipRiskLabel,
  ipSeverityLabel,
  type IpRiskReport,
} from '@/lib/ipRisk'

interface IpDeclaration {
  id: string
  claim_type: 'brand_authorization' | 'certification' | string
  claim_value: string
  evidence_url: string | null
  evidence_status: string
}

export function IpRiskCard({
  report: initialReport,
  productId,
  listingId,
}: {
  report: IpRiskReport | null | undefined
  productId: string
  listingId?: string
}) {
  const queryClient = useQueryClient()
  const [currentReport, setCurrentReport] = useState(initialReport)
  const [claimType, setClaimType] = useState<
    'brand_authorization' | 'certification'
  >('brand_authorization')
  const [claimValue, setClaimValue] = useState('')
  const [evidenceUrl, setEvidenceUrl] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    setCurrentReport(initialReport)
  }, [initialReport])

  const declarationsQuery = useQuery<{ items: IpDeclaration[] }>({
    queryKey: ['ip-declarations', productId],
    queryFn: async () => {
      const response = await apiClient.get('/ip-risk/declarations', {
        params: { product_id: productId },
      })
      return response.data
    },
  })

  const rerunMutation = useMutation({
    mutationFn: async () => {
      const response = await apiClient.post('/ip-risk/screen', {
        product_id: productId,
        listing_id: listingId || null,
        scope: 'text',
        trigger: 'manual',
      })
      return response.data as IpRiskReport
    },
    onMutate: () => setError(''),
    onSuccess: (value) => setCurrentReport(value),
    onError: () => setError('IP 风险重新检查失败，请稍后重试。'),
  })

  const saveDeclarationMutation = useMutation({
    mutationFn: async () => {
      const response = await apiClient.post('/ip-risk/declarations', {
        product_id: productId,
        claim_type: claimType,
        claim_value: claimValue,
        evidence_url: evidenceUrl || null,
        evidence_status: 'provided',
      })
      return response.data
    },
    onMutate: () => setError(''),
    onSuccess: async () => {
      setClaimValue('')
      setEvidenceUrl('')
      await queryClient.invalidateQueries({
        queryKey: ['ip-declarations', productId],
      })
      await rerunMutation.mutateAsync()
    },
    onError: () => setError('授权证据保存失败，请检查后重试。'),
  })

  const deleteDeclarationMutation = useMutation({
    mutationFn: async (declarationId: string) => {
      await apiClient.delete(`/ip-risk/declarations/${declarationId}`)
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ['ip-declarations', productId],
      })
      await rerunMutation.mutateAsync()
    },
  })

  if (!currentReport) return null
  const report = currentReport

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
        <span className="w-full break-all leading-4 text-muted-foreground">
          规则版本 {report.ruleset_version}
        </span>
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        <Button
          size="sm"
          variant="outline"
          className="h-8"
          disabled={rerunMutation.isPending}
          onClick={() => rerunMutation.mutate()}
        >
          {rerunMutation.isPending ? (
            <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
          ) : (
            <RefreshCw className="mr-1 h-3.5 w-3.5" />
          )}
          重新检查
        </Button>
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
                  {ipSeverityLabel(risk.severity)}
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

      <details className="mt-3 border-t border-border pt-3">
        <summary className="cursor-pointer text-[11px] font-medium">
          管理品牌授权与认证证据
        </summary>
        <div className="mt-3 space-y-3">
          {(declarationsQuery.data?.items || []).length > 0 && (
            <div className="space-y-1">
              {(declarationsQuery.data?.items || []).map((item) => (
                <div
                  key={item.id}
                  className="flex items-center justify-between gap-2 border border-border px-2 py-1.5 text-[10px]"
                >
                  <span className="min-w-0 truncate">
                    {item.claim_type === 'brand_authorization'
                      ? '品牌授权'
                      : '认证'}{' '}
                    · {item.claim_value} · {item.evidence_status}
                  </span>
                  <button
                    type="button"
                    className="shrink-0 text-muted-foreground hover:text-destructive"
                    aria-label={`删除 ${item.claim_value} 证据`}
                    onClick={() => deleteDeclarationMutation.mutate(item.id)}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              ))}
            </div>
          )}
          <div className="grid gap-2 sm:grid-cols-2">
            <select
              aria-label="证据类型"
              value={claimType}
              onChange={(event) =>
                setClaimType(
                  event.target.value as
                    | 'brand_authorization'
                    | 'certification',
                )
              }
              className="h-8 border border-input bg-background px-2 text-xs"
            >
              <option value="brand_authorization">品牌授权</option>
              <option value="certification">认证证书</option>
            </select>
            <Input
              value={claimValue}
              onChange={(event) => setClaimValue(event.target.value)}
              placeholder={claimType === 'certification' ? '例如 FDA' : '例如 Nike'}
              className="h-8 text-xs"
              aria-label="授权或认证名称"
            />
            <Input
              value={evidenceUrl}
              onChange={(event) => setEvidenceUrl(event.target.value)}
              placeholder="证据链接，可选"
              className="h-8 text-xs sm:col-span-2"
              aria-label="证据链接"
            />
          </div>
          <Button
            size="sm"
            className="h-8"
            disabled={
              !claimValue.trim()
              || saveDeclarationMutation.isPending
              || rerunMutation.isPending
            }
            onClick={() => saveDeclarationMutation.mutate()}
          >
            {saveDeclarationMutation.isPending ? (
              <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
            ) : (
              <Plus className="mr-1 h-3.5 w-3.5" />
            )}
            保存证据并重新检查
          </Button>
          {error && <p className="text-[10px] text-destructive">{error}</p>}
        </div>
      </details>
    </div>
  )
}
