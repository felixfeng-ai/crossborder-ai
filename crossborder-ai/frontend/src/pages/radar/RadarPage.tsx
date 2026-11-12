import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Radar,
  Plus,
  X,
  Loader2,
  AlertCircle,
  CheckCircle2,
  ExternalLink,
  DollarSign,
  ShoppingBag,
  Store,
  BarChart3,
  TrendingUp,
  TrendingDown,
  Minus,
  Trash2,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import apiClient from '@/api/client'
import { toErrorMessage } from '@/utils/errorMessage'

interface Competitor {
  url: string
  title: string | null
  main_image_url: string | null
  price: number | null
  sales_count: number | null
  shop_name: string | null
  loading?: boolean
  error?: string
}

export default function RadarPage() {
  const [urls, setUrls] = useState<string[]>([''])
  const [competitors, setCompetitors] = useState<Competitor[]>([])

  const addUrl = () => setUrls([...urls, ''])
  const removeUrl = (i: number) => {
    if (urls.length > 1) setUrls(urls.filter((_, idx) => idx !== i))
  }
  const updateUrl = (i: number, val: string) => {
    const next = [...urls]; next[i] = val; setUrls(next)
  }

  // 批量抓取
  const scrapeMutation = useMutation({
    mutationFn: async (targetUrls: string[]) => {
      const results: Competitor[] = []
      for (const url of targetUrls) {
        if (!url.trim()) continue
        try {
          const res = await apiClient.get('/radar/scrape', { params: { url: url.trim() } })
          results.push(res.data.competitor)
        } catch (err: any) {
          results.push({
            url,
            title: null,
            main_image_url: null,
            price: null,
            sales_count: null,
            shop_name: null,
            error: toErrorMessage(err, '抓取失败'),
          })
        }
      }
      return results
    },
    onSuccess: (data) => setCompetitors(data),
  })

  const handleAnalyze = () => {
    const valid = urls.filter(u => u.trim())
    if (valid.length === 0) return
    setCompetitors([])
    scrapeMutation.mutate(valid)
  }

  // 平均价格
  const prices = competitors.filter(c => c.price != null && !c.error).map(c => c.price!)
  const avgPrice = prices.length > 0 ? prices.reduce((a, b) => a + b, 0) / prices.length : 0
  const maxPrice = prices.length > 0 ? Math.max(...prices) : 0
  const minPrice = prices.length > 0 ? Math.min(...prices) : 0

  // 价格区间颜色
  const priceColor = (price: number) => {
    if (prices.length < 2) return 'bg-primary'
    const normalized = (price - minPrice) / (maxPrice - minPrice || 1)
    if (normalized < 0.33) return 'bg-emerald-500'
    if (normalized < 0.66) return 'bg-amber-500'
    return 'bg-destructive'
  }

  return (
    <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
      {/* ── 标题 ────────────────────────────────────────── */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
          <Radar className="h-6 w-6 text-primary" />
          竞品分析
        </h1>
        <p className="text-muted-foreground mt-1">
          输入多个 1688 商品链接，对比分析价格和市场；套餐内赠送额度，超额每次 2 积分
        </p>
      </div>

      {/* ── 输入区域 ────────────────────────────────────── */}
      <Card>
        <CardContent className="pt-6 space-y-3">
          {urls.map((url, i) => (
            <div key={i} className="flex gap-2">
              <Input
                value={url}
                onChange={(e) => updateUrl(i, e.target.value)}
                placeholder={`竞品链接 ${i + 1}`}
                className="flex-1"
              />
              {urls.length > 1 && (
                <Button variant="ghost" size="icon" onClick={() => removeUrl(i)} className="shrink-0">
                  <X className="h-4 w-4" />
                </Button>
              )}
            </div>
          ))}
          <div className="flex gap-2">
            <Button variant="outline" onClick={addUrl} className="gap-1">
              <Plus className="h-4 w-4" />添加竞品
            </Button>
            <Button onClick={handleAnalyze} disabled={scrapeMutation.isPending} className="gap-1 flex-1">
              {scrapeMutation.isPending ? (
                <><Loader2 className="h-4 w-4 animate-spin" />分析中...</>
              ) : (
                <><Radar className="h-4 w-4" />开始对比分析</>
              )}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* ── 分析结果 ────────────────────────────────────── */}
      {competitors.length > 0 && (
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="space-y-4">
          {/* 概览卡片 */}
          <Card className="bg-primary/5 border-primary/20">
            <CardContent className="p-4">
              <div className="grid grid-cols-3 gap-4 text-center">
                <div>
                  <p className="text-xs text-muted-foreground">分析竞品</p>
                  <p className="text-xl font-bold">{competitors.filter(c => !c.error).length}</p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">平均价格</p>
                  <p className="text-xl font-bold">{avgPrice ? `¥${avgPrice.toFixed(0)}` : '-'}</p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">价格区间</p>
                  <p className="text-xl font-bold">{prices.length ? `¥${minPrice} - ¥${maxPrice}` : '-'}</p>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* 价格对比条 */}
          {prices.length > 1 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-sm flex items-center gap-2">
                  <BarChart3 className="h-4 w-4" />
                  价格对比
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {competitors.filter(c => c.price != null && !c.error).map((c, i) => (
                  <div key={i} className="space-y-1">
                    <div className="flex justify-between text-xs">
                      <span className="truncate max-w-[200px]">{c.title?.slice(0, 30) || '未知'}</span>
                      <span className="font-medium">¥{c.price?.toFixed(2)}</span>
                    </div>
                    <div className="h-2 bg-muted rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full transition-all duration-500 ${priceColor(c.price!)}`}
                        style={{ width: `${((c.price! - minPrice) / (maxPrice - minPrice || 1)) * 100}%` }}
                      />
                    </div>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          {/* 详细对比表格 */}
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">详细对比</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {competitors.map((c, i) => (
                  <div key={i} className={`p-3 rounded-lg border ${c.error ? 'border-destructive/30 bg-destructive/5' : 'hover:bg-muted/50'}`}>
                    {c.error ? (
                      <div className="flex items-start gap-2 text-sm">
                        <AlertCircle className="h-4 w-4 text-destructive mt-0.5 shrink-0" />
                        <div>
                          <p className="text-xs text-muted-foreground break-all">{c.url}</p>
                          <p className="text-destructive text-xs mt-1">{c.error}</p>
                        </div>
                      </div>
                    ) : (
                      <div className="flex gap-3">
                        <div className="w-16 h-16 rounded-lg bg-muted flex items-center justify-center overflow-hidden shrink-0">
                          {c.main_image_url ? (
                            <img src={c.main_image_url} alt="" className="w-full h-full object-cover" />
                          ) : (
                            <ShoppingBag className="h-6 w-6 text-muted-foreground/40" />
                          )}
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium leading-snug line-clamp-2">{c.title || '未知商品'}</p>
                          <div className="flex flex-wrap gap-2 mt-1.5">
                            {c.price != null && (
                              <Badge variant="secondary" className="gap-1">
                                <DollarSign className="h-3 w-3" />¥{c.price.toFixed(2)}
                              </Badge>
                            )}
                            {c.shop_name && (
                              <Badge variant="outline" className="gap-1 text-xs">
                                <Store className="h-3 w-3" />{c.shop_name}
                              </Badge>
                            )}
                            {c.sales_count != null && (
                              <Badge variant="outline" className="gap-1 text-xs">
                                已售 {c.sales_count}
                              </Badge>
                            )}
                          </div>
                          <a href={c.url} target="_blank" rel="noopener noreferrer"
                            className="text-xs text-primary hover:underline inline-flex items-center gap-1 mt-1">
                            <ExternalLink className="h-3 w-3" />查看原链接
                          </a>
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* 分析结论 */}
          {prices.length > 1 && (
            <Card className="bg-primary/5 border-primary/20">
              <CardHeader>
                <CardTitle className="text-sm flex items-center gap-2">
                  <TrendingUp className="h-4 w-4" />
                  分析结论
                </CardTitle>
              </CardHeader>
              <CardContent className="text-sm space-y-2 text-muted-foreground">
                <p>📊 共分析 {competitors.filter(c => !c.error).length} 个竞品</p>
                <p>💰 价格区间：¥{minPrice.toFixed(0)} - ¥{maxPrice.toFixed(0)}，均价 ¥{avgPrice.toFixed(0)}</p>
                <p>💡 建议定价：¥{(avgPrice * 0.95).toFixed(0)} - ¥{(avgPrice * 1.05).toFixed(0)}（参考均价 ±5%）</p>
              </CardContent>
            </Card>
          )}
        </motion.div>
      )}

      {/* ── 空状态 ──────────────────────────────────────── */}
      {competitors.length === 0 && !scrapeMutation.isPending && (
        <Card className="bg-muted/30">
          <CardContent className="py-12 text-center text-muted-foreground">
            <Radar className="h-12 w-12 mx-auto mb-3 opacity-30" />
            <p className="text-sm">输入至少一个竞品链接，点击「开始对比分析」</p>
            <p className="text-xs mt-1">系统会自动抓取并对比价格、店铺等信息</p>
          </CardContent>
        </Card>
      )}
    </motion.div>
  )
}
