import { useEffect, useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Sparkles, Copy, CheckCircle2, Loader2, AlertCircle, AlertTriangle, Package, Globe, Image as ImageIcon, ShoppingBag, ExternalLink } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import ListingDescriptionCard from '@/components/content/ListingDescriptionCard'
import ListingSeoCard from '@/components/content/ListingSeoCard'
import apiClient from '@/api/client'
import { toErrorMessage } from '@/utils/errorMessage'
import { createIdempotencyKey } from '@/utils/idempotency'
import {
  waitForImageTask,
  type ImageTaskStatus,
} from '@/lib/images/taskPolling'

interface Product {
  id: string
  title: string | null
  price: number | null
  shop_name: string | null
  main_image_url: string | null
}

interface GenerateResult {
  listing_id: string
  listing_status: 'ready' | 'blocked' | string
  compliance_status: 'pass' | 'block' | 'unknown' | string
  title: string
  description: string
  bullet_points: string[]
  seo_title: string
  seo_description: string
  image_url: string
  image_task_id: string
  blocked: boolean
  violations: string[]
  suggestions: Array<{ word: string; replacement: string }>
}

interface PlatformCapability {
  publish_supported: boolean
  mode: string
  reason: string
}

const PLATFORMS = [
  { id: 'amazon', label: 'Amazon' },
  { id: 'ebay', label: 'eBay' },
  { id: 'shopify', label: 'Shopify' },
  { id: 'etsy', label: 'Etsy' },
  { id: 'shein', label: 'SHEIN' },
  { id: 'temu', label: 'Temu' },
  { id: 'tiktok', label: 'TikTok Shop' },
  { id: 'aliexpress', label: 'AliExpress' },
  { id: 'walmart', label: 'Walmart' },
  { id: 'shopee', label: 'Shopee' },
  { id: 'lazada', label: 'Lazada' },
]

const TONES = [
  { id: 'professional', label: '专业' },
  { id: 'casual', label: '随意' },
  { id: 'luxury', label: '高端' },
  { id: 'friendly', label: '亲切' },
  { id: 'persuasive', label: '说服力' },
  { id: 'humorous', label: '幽默' },
  { id: 'luxury_minimal', label: '极简高端' },
  { id: 'urgent', label: '限时抢购' },
  { id: 'custom', label: '自定义' },
]

const LANGUAGES = [
  { id: 'en', label: 'English (US/UK/AU)' },
  { id: 'ja', label: '日本語' },
  { id: 'es', label: 'Español' },
  { id: 'fr', label: 'Français' },
  { id: 'de', label: 'Deutsch' },
  { id: 'it', label: 'Italiano' },
  { id: 'pt', label: 'Português' },
  { id: 'nl', label: 'Nederlands' },
  { id: 'sv', label: 'Svenska' },
  { id: 'pl', label: 'Polski' },
  { id: 'tr', label: 'Türkçe' },
  { id: 'ar', label: 'العربية' },
  { id: 'ko', label: '한국어' },
  { id: 'zh', label: '中文' },
  { id: 'vi', label: 'Tiếng Việt' },
  { id: 'th', label: 'ไทย' },
  { id: 'ms', label: 'Bahasa Melayu' },
]

export default function ContentPage() {
  const [searchParams] = useSearchParams()
  const [selectedProduct, setSelectedProduct] = useState(searchParams.get('product') || '')
  const [platform, setPlatform] = useState(searchParams.get('platform') || 'amazon')
  const [tone, setTone] = useState('professional')
  const [language, setLanguage] = useState('en')
  const [generateImage, setGenerateImage] = useState(false)
  const [imagePrompt, setImagePrompt] = useState('')
  const [expertMode, setExpertMode] = useState(false)
  const [customTone, setCustomTone] = useState('')
  const [copied, setCopied] = useState('')
  const [selectedChannel, setSelectedChannel] = useState('')
  const [imageTask, setImageTask] = useState<ImageTaskStatus | null>(null)
  const [imageTaskLoading, setImageTaskLoading] = useState(false)
  const [imageTaskError, setImageTaskError] = useState('')

  const { data: capabilities } = useQuery<Record<string, PlatformCapability>>({
    queryKey: ['platform-capabilities'],
    queryFn: async () => {
      const response = await apiClient.get('/platforms/capabilities')
      return response.data.platforms
    },
  })

  // 商品列表
  const { data: products } = useQuery({
    queryKey: ['products-for-content'],
    queryFn: async () => {
      const res = await apiClient.get('/products', { params: { page_size: 50 } })
      return res.data.items as Product[]
    },
  })

  // Shopify 店铺列表
  const { data: channels } = useQuery({
    queryKey: ['shopify-channels'],
    queryFn: async () => {
      const res = await apiClient.get('/shopify/channels')
      return res.data
    },
  })

  // 发布到 Shopify
  const publishMutation = useMutation({
    mutationFn: async () => {
      const res = await apiClient.post('/shopify/push', {
        listing_id: generateMutation.data?.listing_id,
        channel_id: selectedChannel,
      }, {
        headers: { 'Idempotency-Key': createIdempotencyKey() },
      })
      return res.data
    },
  })

  const handlePublish = () => {
    if (
      !generateMutation.data?.listing_id ||
      generateMutation.data.compliance_status !== 'pass' ||
      !selectedChannel
    ) return
    publishMutation.mutate()
  }

  // AI 生成
  const generateMutation = useMutation({
    onMutate: () => {
      // 新一轮生成开始时清理上一轮的任务和图片状态，避免旧结果闪现。
      setImageTask(null)
      setImageTaskError('')
      setImageTaskLoading(false)
    },
    mutationFn: async () => {
      const actualTone = tone === 'custom' ? (customTone || 'professional') : tone
      const res = await apiClient.post('/content/generate', {
        product_id: selectedProduct,
        platform,
        tone: actualTone,
        language,
        generate_image: generateImage,
        image_prompt: imagePrompt || undefined,
        expert_mode: expertMode,
      })
      return res.data as GenerateResult
    },
  })

  useEffect(() => {
    const taskId = generateMutation.data?.image_task_id
    if (!taskId) {
      setImageTask(null)
      setImageTaskLoading(false)
      setImageTaskError('')
      return
    }

    let cancelled = false
    setImageTask(null)
    setImageTaskError('')
    setImageTaskLoading(true)

    waitForImageTask(taskId, async (id) => {
      const response = await apiClient.get(`/images/status/${id}`)
      return response.data as ImageTaskStatus
    })
      .then((task) => {
        if (!cancelled) setImageTask(task)
      })
      .catch((error) => {
        if (!cancelled) {
          setImageTaskError(toErrorMessage(error, '图片生成失败，请稍后重试'))
        }
      })
      .finally(() => {
        if (!cancelled) setImageTaskLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [generateMutation.data?.image_task_id])

  const copyText = (text: string, label: string) => {
    navigator.clipboard.writeText(text)
    setCopied(label)
    setTimeout(() => setCopied(''), 2000)
  }

  const selected = products?.find((p) => p.id === selectedProduct)

  return (
    <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <Sparkles className="h-6 w-6 text-primary" />
            AI 生成 Listing
          </h1>
          <p className="text-muted-foreground">选择商品，AI 自动生成标题、描述、卖点</p>
        </div>
      </div>

      <div className="rounded-lg border border-amber-500/25 bg-amber-500/5 px-4 py-3 text-sm">
        <span className="font-medium text-amber-700 dark:text-amber-300">发布能力：</span>
        <span className="text-muted-foreground">
          当前仅 Shopify 支持真实发布；Amazon、Temu、SHEIN 支持生成文案，发布接口仍在接入中。
        </span>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* 左侧：配置区 */}
        <div className="space-y-4 lg:col-span-1">
          {/* 选择商品 */}
          <Card>
            <CardHeader><CardTitle className="text-sm">选择商品</CardTitle></CardHeader>
            <CardContent className="space-y-2">
              {products?.length === 0 ? (
                <p className="text-sm text-muted-foreground">还没有商品，先去录入吧</p>
              ) : (
                <select
                  value={selectedProduct}
                  onChange={(e) => setSelectedProduct(e.target.value)}
                  className="w-full rounded-md border bg-background px-3 py-2 text-sm"
                >
                  <option value="">-- 选择商品 --</option>
                  {products?.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.title?.slice(0, 40) || '无标题'}
                    </option>
                  ))}
                </select>
              )}
              {selected && (
                <div className="text-xs text-muted-foreground">
                  <p>价格: {selected.price ? `¥${selected.price}` : '-'}</p>
                  <p>店铺: {selected.shop_name || '-'}</p>
                </div>
              )}
            </CardContent>
          </Card>

          {/* 平台选择 */}
          <Card>
            <CardHeader><CardTitle className="text-sm">目标平台</CardTitle></CardHeader>
            <CardContent className="flex flex-wrap gap-2">
              {PLATFORMS.map((p) => (
                <Badge
                  key={p.id}
                  variant={platform === p.id ? 'default' : 'outline'}
                  className="cursor-pointer"
                  onClick={() => setPlatform(p.id)}
                >
                  {p.label}
                </Badge>
              ))}
            </CardContent>
          </Card>

          {/* 语气选择 */}
          <Card>
            <CardHeader><CardTitle className="text-sm">语气风格</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              <div className="flex flex-wrap gap-2">
                {TONES.map((t) => (
                  <Badge
                    key={t.id}
                    variant={tone === t.id ? 'default' : 'outline'}
                    className="cursor-pointer"
                    onClick={() => setTone(t.id)}
                  >
                    {t.label}
                  </Badge>
                ))}
              </div>
              {tone === 'custom' && (
                <Input
                  placeholder="输入自定义语气，例如：夸张促销、环保理念、科技感..."
                  value={customTone}
                  onChange={(e) => setCustomTone(e.target.value)}
                />
              )}
            </CardContent>
          </Card>

          {/* 语言选择 */}
          <Card>
            <CardHeader><CardTitle className="text-sm">输出语言</CardTitle></CardHeader>
            <CardContent className="flex flex-wrap gap-2">
              {LANGUAGES.map((l) => (
                <Badge
                  key={l.id}
                  variant={language === l.id ? 'default' : 'outline'}
                  className="cursor-pointer"
                  onClick={() => setLanguage(l.id)}
                >
                  <Globe className="h-3 w-3 mr-1" />
                  {l.label}
                </Badge>
              ))}
            </CardContent>
          </Card>

          {/* 专家模式 */}
          <Card>
            <CardHeader><CardTitle className="text-sm">生成模式</CardTitle></CardHeader>
            <CardContent>
              <label className="flex items-center gap-2 cursor-pointer">
                <input type="checkbox" checked={expertMode} onChange={(e) => setExpertMode(e.target.checked)}
                  className="rounded border-gray-300" />
                <span className="text-sm">专家模式（多轮自检+优化，质量更高但较慢）</span>
              </label>
            </CardContent>
          </Card>

          {/* 生成主图 */}
          <Card>
            <CardHeader><CardTitle className="text-sm">商品主图</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              <label className="flex items-center gap-2 cursor-pointer">
                <input type="checkbox" checked={generateImage} onChange={(e) => setGenerateImage(e.target.checked)}
                  className="rounded border-gray-300" />
                <span className="text-sm">AI 生成商品主图（FLUX 模型）</span>
              </label>
              {generateImage && (
                <Input
                  value={imagePrompt}
                  onChange={(e) => setImagePrompt(e.target.value)}
                  placeholder="图片描述（留空自动根据商品标题生成）"
                  className="text-sm"
                />
              )}
            </CardContent>
          </Card>

          <Button
            className="w-full"
            size="lg"
            disabled={!selectedProduct || generateMutation.isPending}
            onClick={() => generateMutation.mutate()}
          >
            {generateMutation.isPending ? (
              <><Loader2 className="mr-2 h-4 w-4 animate-spin" />AI 生成中...</>
            ) : (
              <><Sparkles className="mr-2 h-4 w-4" />AI 生成 Listing</>
            )}
          </Button>
        </div>

        {/* 右侧：结果区 */}
        <div className="space-y-4 lg:col-span-2">
          {generateMutation.isError && (
            <Card className="border-destructive/50">
              <CardContent className="pt-6 flex items-start gap-3">
                <AlertCircle className="h-5 w-5 text-destructive shrink-0 mt-0.5" />
                <div>
                  <p className="font-medium text-destructive">生成失败</p>
                  <p className="text-sm text-muted-foreground mt-1">
                    {toErrorMessage(generateMutation.error)}
                  </p>
                </div>
              </CardContent>
            </Card>
          )}

          {generateMutation.isPending && (
            <Card>
              <CardContent className="flex flex-col items-center justify-center py-16">
                <Loader2 className="h-8 w-8 animate-spin text-primary mb-4" />
                <p className="text-sm text-muted-foreground">AI 正在生成内容，请稍候...</p>
              </CardContent>
            </Card>
          )}

          {generateMutation.data && (
            <>
              {generateMutation.data.blocked && (
                <Card className="border-destructive/40 bg-destructive/5">
                  <CardContent className="pt-6 flex items-start gap-3">
                    <AlertTriangle className="h-5 w-5 text-destructive shrink-0 mt-0.5" />
                    <div>
                      <p className="font-medium text-destructive">合规审查未通过，当前 Listing 已禁止发布</p>
                      <p className="text-sm text-muted-foreground mt-1">
                        命中：{generateMutation.data.violations.join('、') || '平台合规规则'}
                      </p>
                    </div>
                  </CardContent>
                </Card>
              )}

              {imageTaskLoading && (
                <Card>
                  <CardContent className="py-6 flex items-center gap-3 text-sm text-muted-foreground">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    正在生成商品图片，Listing 文案已经可以使用
                  </CardContent>
                </Card>
              )}

              {imageTaskError && (
                <Card className="border-amber-500/30 bg-amber-500/5">
                  <CardContent className="py-4 text-sm text-amber-700 dark:text-amber-300 flex items-center gap-2">
                    <AlertCircle className="h-4 w-4" />
                    {imageTaskError}
                  </CardContent>
                </Card>
              )}

              {imageTask?.image_urls?.length ? (
                <Card>
                  <CardHeader>
                    <CardTitle className="text-sm flex items-center gap-2">
                      <ImageIcon className="h-4 w-4" />AI 生成图片
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="grid gap-3 sm:grid-cols-2">
                    {imageTask.image_urls.map((url, index) => (
                      <img
                        key={`${url}-${index}`}
                        src={url}
                        alt={`AI 生成商品图 ${index + 1}`}
                        className="w-full rounded-lg border object-cover"
                      />
                    ))}
                  </CardContent>
                </Card>
              ) : null}

              {/* 兼容旧的同步 image_url 返回 */}
              {generateMutation.data.image_url && (
                <Card>
                  <CardHeader><CardTitle className="text-sm flex items-center gap-2">
                    <ImageIcon className="h-4 w-4" />生成的主图
                  </CardTitle></CardHeader>
                  <CardContent>
                    <img src={generateMutation.data.image_url} alt="Generated product image"
                      className="w-full max-w-sm rounded-lg border" />
                  </CardContent>
                </Card>
              )}
              {/* 标题 */}
              <Card>
                <CardHeader className="flex flex-row items-start justify-between">
                  <CardTitle className="text-sm">商品标题</CardTitle>
                  <Button variant="ghost" size="icon" onClick={() => copyText(generateMutation.data.title, 'title')}>
                    {copied === 'title' ? <CheckCircle2 className="h-4 w-4 text-emerald-500" /> : <Copy className="h-4 w-4" />}
                  </Button>
                </CardHeader>
                <CardContent>
                  <p className="text-sm">{generateMutation.data.title || '无'}</p>
                </CardContent>
              </Card>

              {/* 卖点 */}
              <Card>
                <CardHeader className="flex flex-row items-start justify-between">
                  <CardTitle className="text-sm">卖点（Bullet Points）</CardTitle>
                  <Button variant="ghost" size="icon" onClick={() => copyText(generateMutation.data.bullet_points.join('\n'), 'bullets')}>
                    {copied === 'bullets' ? <CheckCircle2 className="h-4 w-4 text-emerald-500" /> : <Copy className="h-4 w-4" />}
                  </Button>
                </CardHeader>
                <CardContent>
                  <ul className="space-y-1">
                    {generateMutation.data.bullet_points.map((b, i) => (
                      <li key={i} className="text-sm flex items-start gap-2">
                        <span className="text-primary mt-1.5 h-1.5 w-1.5 rounded-full bg-primary shrink-0" />
                        {b}
                      </li>
                    ))}
                  </ul>
                </CardContent>
              </Card>

              {/* 详情使用安全富文本预览，源码放在独立视图，避免格式标记直接铺开。 */}
              <ListingDescriptionCard
                description={generateMutation.data.description}
                copied={copied}
                onCopy={copyText}
              />

              {/* SEO 描述保持摘要形态，并对历史超长数据提供折叠。 */}
              {(generateMutation.data.seo_title || generateMutation.data.seo_description) && (
                <ListingSeoCard
                  seoTitle={generateMutation.data.seo_title}
                  seoDescription={generateMutation.data.seo_description}
                  copied={copied}
                  onCopy={copyText}
                />
              )}

              {/* 原文对照 */}
              {selected && language !== 'zh' && (
                <Card className="border-amber-500/20 bg-amber-500/5">
                  <CardHeader>
                    <CardTitle className="text-sm flex items-center gap-2 text-amber-500">
                      <Globe className="h-4 w-4" />
                      原文 vs 译文对照
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="grid md:grid-cols-2 gap-4">
                      <div className="space-y-3">
                        <p className="text-xs font-medium text-muted-foreground">原文（中文）</p>
                        <div className="rounded-lg border bg-background p-3 space-y-1">
                          <p className="text-sm font-medium">{selected.title || '-'}</p>
                          {selected.price != null && <p className="text-xs text-muted-foreground">价格：¥{selected.price}</p>}
                          {selected.shop_name && <p className="text-xs text-muted-foreground">店铺：{selected.shop_name}</p>}
                        </div>
                      </div>
                      <div className="space-y-3">
                        <p className="text-xs font-medium text-muted-foreground">译文（{language.toUpperCase()}）</p>
                        <div className="rounded-lg border bg-background p-3 space-y-1">
                          <p className="text-sm font-medium">{generateMutation.data.title || '-'}</p>
                          {generateMutation.data.bullet_points?.slice(0, 3).map((b: string, i: number) => (
                            <p key={i} className="text-xs text-muted-foreground">• {b}</p>
                          ))}
                        </div>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              )}
            </>
          )}

          {generateMutation.data && platform !== 'shopify' && capabilities && (
            <Card className="border-amber-500/20 bg-amber-500/5">
              <CardContent className="pt-6 text-sm text-muted-foreground">
                {capabilities[platform]?.reason || '该平台暂不支持一键发布，当前仅生成 Listing 文案。'}
              </CardContent>
            </Card>
          )}

          {generateMutation.data && platform === 'shopify' && capabilities?.shopify?.publish_supported && channels && channels.length > 0 && (
            <Card className="border-emerald-500/20 bg-emerald-500/5">
              <CardHeader>
                <CardTitle className="text-sm flex items-center gap-2">
                  <Globe className="h-4 w-4 text-emerald-500" />
                  发布到 Shopify
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <select
                  value={selectedChannel}
                  onChange={(e) => setSelectedChannel(e.target.value)}
                  className="w-full rounded-md border bg-background px-3 py-2 text-sm"
                >
                  <option value="">-- 选择店铺 --</option>
                  {channels.map((c: any) => (
                    <option key={c.id} value={c.id}>{c.shop_name}</option>
                  ))}
                </select>
                <Button
                  className="w-full"
                  disabled={
                    !selectedChannel ||
                    publishMutation.isPending ||
                    generateMutation.data.compliance_status !== 'pass' ||
                    !generateMutation.data.listing_id
                  }
                  onClick={handlePublish}
                >
                  {publishMutation.isPending ? (
                    <><Loader2 className="mr-2 h-4 w-4 animate-spin" />发布中...</>
                  ) : generateMutation.data.compliance_status !== 'pass' ? (
                    <><AlertTriangle className="mr-2 h-4 w-4" />合规未通过，禁止发布</>
                  ) : (
                    <><ShoppingBag className="mr-2 h-4 w-4" />发布到 Shopify</>
                  )}
                </Button>
                {publishMutation.data && (
                  <p className="text-sm text-emerald-600 flex items-center gap-1">
                    <CheckCircle2 className="h-4 w-4" />{publishMutation.data.message}
                  </p>
                )}
                {publishMutation.error && (
                  <p className="text-sm text-destructive flex items-center gap-1">
                    <AlertCircle className="h-4 w-4" />
                    {toErrorMessage(publishMutation.error, '发布失败').substring(0, 100)}
                  </p>
                )}
              </CardContent>
            </Card>
          )}

          {!generateMutation.data && !generateMutation.isPending && (
            <Card>
              <CardContent className="flex flex-col items-center justify-center py-20 text-muted-foreground">
                <Sparkles className="h-12 w-12 mb-4 opacity-30" />
                <p className="text-sm">选择一个商品，点击「AI 生成 Listing」</p>
                <p className="text-xs mt-1">AI 会自动生成标题、描述和卖点</p>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </motion.div>
  )
}
