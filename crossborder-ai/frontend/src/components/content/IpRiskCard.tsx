import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  CalendarClock,
  FileSearch,
  Image as ImageIcon,
  ImageOff,
  Loader2,
  Plus,
  RefreshCw,
  ScanSearch,
  ShieldAlert,
  Trash2,
} from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import apiClient from '@/api/client'
import { resolveMediaUrl } from '@/lib/apiUrl'
import {
  coverageLabel,
  evidenceExpiryState,
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
  expires_at: string | null
}

interface IpImageAsset {
  id: string
  name: string
  image_url: string
  width: number
  height: number
}

function riskBboxStyle(bbox: number[] | null | undefined) {
  if (!bbox || bbox.length !== 4) return undefined
  const values = bbox.map(Number)
  if (!values.every(Number.isFinite)) return undefined
  const [x1, y1, x2, y2] = values.map((value) =>
    Math.max(0, Math.min(1000, value)),
  )
  return {
    left: `${x1 / 10}%`,
    top: `${y1 / 10}%`,
    width: `${Math.max(0, x2 - x1) / 10}%`,
    height: `${Math.max(0, y2 - y1) / 10}%`,
  }
}

function EvidenceExpiryLabel({ value }: { value: string | null }) {
  const expiry = evidenceExpiryState(value)
  const tone =
    expiry.status === 'expired'
      ? 'text-destructive'
      : expiry.status === 'expiring'
        ? 'text-amber-500'
        : 'text-muted-foreground'
  return (
    <span className={`flex items-center gap-1 ${tone}`}>
      <CalendarClock className="h-3 w-3 shrink-0" />
      {expiry.label}
    </span>
  )
}

export function IpRiskCard({
  report: initialReport,
  productId,
  listingId,
  onReportChange,
}: {
  report: IpRiskReport | null | undefined
  productId: string
  listingId?: string
  onReportChange?: (report: IpRiskReport) => void
}) {
  const queryClient = useQueryClient()
  const [currentReport, setCurrentReport] = useState(initialReport)
  const [claimType, setClaimType] = useState<
    'brand_authorization' | 'certification'
  >('brand_authorization')
  const [claimValue, setClaimValue] = useState('')
  const [evidenceUrl, setEvidenceUrl] = useState('')
  const [expiresAt, setExpiresAt] = useState('')
  const [selectedImageIds, setSelectedImageIds] = useState<string[]>([])
  const [error, setError] = useState('')

  useEffect(() => {
    setCurrentReport(initialReport)
  }, [initialReport])

  useEffect(() => {
    setSelectedImageIds([])
  }, [productId])

  const imagesQuery = useQuery<{ items: IpImageAsset[]; total: number }>({
    queryKey: ['ip-image-assets'],
    queryFn: async () => {
      const response = await apiClient.get('/images/assets')
      return response.data
    },
  })

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
    mutationFn: async (scope: 'text' | 'both') => {
      const response = await apiClient.post('/ip-risk/screen', {
        product_id: productId,
        listing_id: listingId || null,
        scope,
        image_asset_ids: scope === 'both' ? selectedImageIds : [],
        trigger: 'manual',
      })
      return response.data as IpRiskReport
    },
    onMutate: () => setError(''),
    onSuccess: (value) => {
      setCurrentReport(value)
      onReportChange?.(value)
    },
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
        expires_at: expiresAt
          ? new Date(`${expiresAt}T23:59:59`).toISOString()
          : null,
      })
      return response.data
    },
    onMutate: () => setError(''),
    onSuccess: async () => {
      setClaimValue('')
      setEvidenceUrl('')
      setExpiresAt('')
      await queryClient.invalidateQueries({
        queryKey: ['ip-declarations', productId],
      })
      await rerunMutation.mutateAsync(
        selectedImageIds.length ? 'both' : 'text',
      )
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
      await rerunMutation.mutateAsync(
        selectedImageIds.length ? 'both' : 'text',
      )
    },
    onError: () => setError('授权证据删除失败，请稍后重试。'),
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
          onClick={() => rerunMutation.mutate('text')}
        >
          {rerunMutation.isPending ? (
            <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
          ) : (
            <RefreshCw className="mr-1 h-3.5 w-3.5" />
          )}
          重新检查文本
        </Button>
        <Button
          size="sm"
          className="h-8"
          disabled={
            rerunMutation.isPending || selectedImageIds.length === 0
          }
          onClick={() => rerunMutation.mutate('both')}
        >
          {rerunMutation.isPending ? (
            <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
          ) : (
            <ScanSearch className="mr-1 h-3.5 w-3.5" />
          )}
          检查所选图片
        </Button>
      </div>

      <div className="mt-4 border-t border-border pt-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="flex items-center gap-1.5 text-[11px] font-medium">
            <ImageIcon className="h-3.5 w-3.5" />
            从素材库选择本次检查的商品图
          </p>
          <span className="text-[10px] text-muted-foreground">
            已选 {selectedImageIds.length}/6
          </span>
        </div>
        {imagesQuery.isLoading ? (
          <p className="mt-2 text-[10px] text-muted-foreground">
            正在加载最近图片...
          </p>
        ) : (imagesQuery.data?.items || []).length === 0 ? (
          <p className="mt-2 text-[10px] text-muted-foreground">
            素材库暂无图片，请先在图片工作台上传商品图。
          </p>
        ) : (
          <div className="mt-2 grid grid-cols-3 gap-2 sm:grid-cols-6">
            {(imagesQuery.data?.items || []).slice(0, 12).map((asset) => {
              const selected = selectedImageIds.includes(asset.id)
              const riskBoxes = report.risks.filter(
                (risk) =>
                  risk.evidence.asset_id === asset.id &&
                  risk.evidence.bbox?.length === 4,
              )
              return (
                <button
                  key={asset.id}
                  type="button"
                  aria-pressed={selected}
                  aria-label={`${selected ? '取消检查' : '选择检查'} ${asset.name}`}
                  className={`relative aspect-square overflow-hidden border bg-[#d9dad5] transition-colors ${
                    selected
                      ? 'border-[var(--factory-coral)] ring-1 ring-[var(--factory-coral)]'
                      : 'border-border hover:border-foreground/40'
                  }`}
                  onClick={() => {
                    setSelectedImageIds((current) => {
                      if (current.includes(asset.id)) {
                        return current.filter((id) => id !== asset.id)
                      }
                      return current.length >= 6
                        ? current
                        : [...current, asset.id]
                    })
                  }}
                >
                  <img
                    src={resolveMediaUrl(asset.image_url)}
                    alt={asset.name}
                    className="h-full w-full object-contain"
                  />
                  {riskBoxes.map((risk, index) => (
                    <span
                      key={`${risk.code}-${index}`}
                      aria-label={`图片风险区域：${risk.code}`}
                      className="pointer-events-none absolute border-2 border-destructive bg-destructive/10"
                      style={riskBboxStyle(risk.evidence.bbox)}
                    />
                  ))}
                  <span className="absolute inset-x-0 bottom-0 truncate bg-black/65 px-1 py-0.5 text-left text-[9px] text-white">
                    {asset.name}
                  </span>
                </button>
              )
            })}
          </div>
        )}
      </div>

      {report.status === 'partial' && (
        <p className="mt-3 border-l-2 border-amber-500 pl-2 text-[10px] leading-4 text-muted-foreground">
          报告为部分完成。未检查的项目不能视为已经通过。
        </p>
      )}
      {report.coverage.image_required &&
        report.coverage.image !== 'checked' && (
          <p className="mt-3 flex items-start gap-2 border-l-2 border-amber-500 pl-2 text-[10px] leading-4 text-muted-foreground">
            <CalendarClock className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            当前商品类目要求图片检查，选择商品图完成检查后才能发布。
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
                  className="flex items-center justify-between gap-2 border border-border px-2 py-2 text-[10px]"
                >
                  <div className="min-w-0 flex-1">
                    <p className="truncate">
                      {item.claim_type === 'brand_authorization'
                        ? '品牌授权'
                        : '认证'}{' '}
                      · {item.claim_value} · {item.evidence_status}
                    </p>
                    <div className="mt-1">
                      <EvidenceExpiryLabel value={item.expires_at} />
                    </div>
                  </div>
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
            <div className="space-y-1 sm:col-span-2">
              <label
                htmlFor="ip-evidence-expiry"
                className="text-[10px] text-muted-foreground"
              >
                证据有效期（可选，留空表示长期有效）
              </label>
              <Input
                id="ip-evidence-expiry"
                type="date"
                value={expiresAt}
                onChange={(event) => setExpiresAt(event.target.value)}
                className="h-8 text-xs"
                aria-label="证据有效期"
              />
            </div>
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
