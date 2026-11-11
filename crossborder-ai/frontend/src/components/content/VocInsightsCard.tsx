import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertCircle,
  FileText,
  Loader2,
  MessageSquareQuote,
  Sparkles,
  Upload,
} from 'lucide-react'
import apiClient from '@/api/client'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  dominantSentiment,
  sentimentLabel,
  sentimentPercent,
} from '@/lib/voc'
import { toErrorMessage } from '@/utils/errorMessage'


interface VocAnalysis {
  id: string
  product_id: string | null
  platform: string
  language: string
  review_count: number
  summary: string
  pain_points: string[]
  selling_points: string[]
  objections: string[]
  keywords: string[]
  sentiment: Record<string, unknown>
  recommendations: string[]
  model_used: string
  created_at: string
}

interface VocInsightsCardProps {
  productId: string
  platform: string
}

export default function VocInsightsCard({
  productId,
  platform,
}: VocInsightsCardProps) {
  const queryClient = useQueryClient()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [reviews, setReviews] = useState('')
  const [selectedId, setSelectedId] = useState('')
  const [showComposer, setShowComposer] = useState(false)

  const analysesQuery = useQuery<VocAnalysis[]>({
    queryKey: ['voc-analyses', productId],
    queryFn: async () => {
      const response = await apiClient.get('/voc/analyses', {
        params: { product_id: productId, limit: 20 },
      })
      return response.data.items || []
    },
    enabled: Boolean(productId),
  })

  const analyses = analysesQuery.data || []

  useEffect(() => {
    setSelectedId('')
    setReviews('')
    setShowComposer(false)
  }, [productId])

  useEffect(() => {
    if (!analyses.length) {
      setSelectedId('')
      return
    }
    if (!analyses.some((item) => item.id === selectedId)) {
      setSelectedId(analyses[0].id)
    }
  }, [analyses, selectedId])

  const current = analyses.find((item) => item.id === selectedId) || analyses[0]

  const analyzeMutation = useMutation({
    mutationFn: async () => {
      const response = await apiClient.post<VocAnalysis>('/voc/analyze', {
        product_id: productId,
        platform,
        language: 'en',
        reviews,
      })
      return response.data
    },
    onSuccess: (created) => {
      setSelectedId(created.id)
      setReviews('')
      setShowComposer(false)
      queryClient.setQueryData<VocAnalysis[]>(
        ['voc-analyses', productId],
        (existing = []) => [
          created,
          ...existing.filter((item) => item.id !== created.id),
        ],
      )
      queryClient.invalidateQueries({ queryKey: ['voc-analyses', productId] })
    },
  })

  const importFile = async (file: File | undefined) => {
    if (!file) return
    const text = await file.text()
    setReviews(text.slice(0, 200_000))
    setShowComposer(true)
  }

  const sentiment = current?.sentiment || {}
  const dominant = dominantSentiment(sentiment)

  return (
    <Card>
      <CardHeader className="space-y-2">
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="flex items-center gap-2 text-sm">
            <MessageSquareQuote className="h-4 w-4 text-primary" />
            评论洞察 VOC
          </CardTitle>
          {current && (
            <Badge variant="outline" className="metric-number text-[10px]">
              {current.review_count} 条
            </Badge>
          )}
        </div>
        {current && (
          <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
            <span>{current.platform.toUpperCase()}</span>
            <span>·</span>
            <span>{new Date(current.created_at).toLocaleString('zh-CN')}</span>
            {analyses.length > 1 && (
              <select
                aria-label="切换 VOC 历史分析"
                value={selectedId}
                onChange={(event) => setSelectedId(event.target.value)}
                className="ml-auto h-7 max-w-36 border border-input bg-background px-1.5 text-[11px] outline-none focus:ring-2 focus:ring-ring"
              >
                {analyses.map((item, index) => (
                  <option key={item.id} value={item.id}>
                    {index === 0 ? '最新分析' : `${item.review_count} 条评论`} ·{' '}
                    {new Date(item.created_at).toLocaleDateString('zh-CN')}
                  </option>
                ))}
              </select>
            )}
          </div>
        )}
      </CardHeader>
      <CardContent className="space-y-3">
        {!productId && (
          <p className="text-xs leading-5 text-muted-foreground">
            选择商品后可导入评论并分析真实买家反馈。
          </p>
        )}

        {productId && !showComposer && current && (
          <>
            <p className="text-xs leading-5 text-foreground">{current.summary}</p>
            <div className="flex flex-wrap gap-1.5">
              <Badge variant="secondary">{sentimentLabel(dominant)}反馈</Badge>
              {(['positive', 'neutral', 'negative'] as const).map((key) => (
                <span
                  key={key}
                  className="border border-border px-1.5 py-0.5 text-[10px] text-muted-foreground"
                >
                  {sentimentLabel(key)} {sentimentPercent(sentiment, key)}%
                </span>
              ))}
            </div>
            <InsightList title="主要痛点" items={current.pain_points} />
            <InsightList title="可转化卖点" items={current.selling_points} />
            <InsightList title="成交异议" items={current.objections} />
            {current.recommendations[0] && (
              <p className="border-l-2 border-primary/45 pl-2 text-[11px] leading-5 text-muted-foreground">
                {current.recommendations[0]}
              </p>
            )}
            <Button
              variant="outline"
              size="sm"
              className="w-full"
              onClick={() => setShowComposer(true)}
            >
              <Sparkles className="mr-2 h-3.5 w-3.5" />
              用新评论重新分析
            </Button>
          </>
        )}

        {productId && (!current || showComposer) && (
          <>
            <textarea
              value={reviews}
              maxLength={200_000}
              onChange={(event) => setReviews(event.target.value)}
              placeholder="粘贴评论，每行一条；也支持 CSV 的 review/comment/评论列。"
              className="min-h-28 w-full resize-y border border-input bg-background px-2.5 py-2 text-xs leading-5 outline-none placeholder:text-muted-foreground focus:ring-2 focus:ring-ring"
            />
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv,.txt,text/csv,text/plain"
              className="hidden"
              onChange={(event) => {
                void importFile(event.target.files?.[0])
                event.target.value = ''
              }}
            />
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                className="flex-1"
                onClick={() => fileInputRef.current?.click()}
              >
                <Upload className="mr-1.5 h-3.5 w-3.5" />
                导入 CSV / TXT
              </Button>
              <Button
                size="sm"
                className="flex-1"
                disabled={!reviews.trim() || analyzeMutation.isPending}
                onClick={() => analyzeMutation.mutate()}
              >
                {analyzeMutation.isPending ? (
                  <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                ) : (
                  <FileText className="mr-1.5 h-3.5 w-3.5" />
                )}
                {analyzeMutation.isPending ? '分析中' : '分析评论 1 积分'}
              </Button>
            </div>
            {current && (
              <Button
                variant="ghost"
                size="sm"
                className="w-full"
                onClick={() => setShowComposer(false)}
              >
                返回最近洞察
              </Button>
            )}
          </>
        )}

        {analysesQuery.isError && (
          <p className="flex items-start gap-2 text-xs text-destructive">
            <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            {toErrorMessage(analysesQuery.error, '评论洞察加载失败')}
          </p>
        )}
        {analyzeMutation.isError && (
          <p className="flex items-start gap-2 text-xs text-destructive">
            <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            {toErrorMessage(analyzeMutation.error, '评论分析失败')}
          </p>
        )}
      </CardContent>
    </Card>
  )
}


function InsightList({ title, items }: { title: string; items: string[] }) {
  if (!items.length) return null
  return (
    <div>
      <p className="text-[10px] font-medium text-muted-foreground">{title}</p>
      <ul className="mt-1 space-y-1">
        {items.slice(0, 3).map((item) => (
          <li key={item} className="flex gap-1.5 text-[11px] leading-5">
            <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-primary" />
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
