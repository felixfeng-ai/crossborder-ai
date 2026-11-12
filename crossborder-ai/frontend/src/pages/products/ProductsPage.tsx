import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import {
  Link as LinkIcon,
  Search,
  ExternalLink,
  ShoppingBag,
  Loader2,
  AlertCircle,
  CheckCircle2,
  Package,
  Plus,
  FileInput,
  Settings,
  Sparkles,
  Trash2,
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
  Upload,
  ImagePlus,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import apiClient from '@/api/client'
import { resolveMediaUrl } from '@/lib/apiUrl'
import {
  buildOwnProductPayload,
  productOriginLabel,
} from '@/lib/products/entry'
import {
  imageUploadErrorMessage,
  uploadImageFile,
  validateImageUpload,
} from '@/lib/images/upload'
import { cn } from '@/utils/cn'
import { toErrorMessage } from '@/utils/errorMessage'

interface Product {
  id: string
  url: string
  title: string | null
  main_image_url: string | null
  price: number | null
  sales_count: number | null
  shop_name: string | null
  description: string | null
  origin_type: '1688' | 'own'
  brand_name: string | null
  cost_currency: string
  moq: number | null
  lead_time_days: number | null
  created_at: string
  updated_at: string
}

interface ProductListResponse {
  items: Product[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export default function ProductsPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [url, setUrl] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [entryMode, setEntryMode] = useState<'1688' | 'own'>('1688')
  const [imageUploading, setImageUploading] = useState(false)
  const [imageProgress, setImageProgress] = useState(0)
  const [manualError, setManualError] = useState('')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [confirmDelete, setConfirmDelete] = useState<'single' | 'batch' | 'all' | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null)

  // 手动输入表单
  const [manualForm, setManualForm] = useState({
    url: '',
    title: '',
    description: '',
    price: '',
    currency: 'CNY',
    brandName: '',
    moq: '',
    leadTimeDays: '',
    sku: '',
    stockQuantity: '',
    mainImageUrl: '',
  })

  // 商品列表
  const { data, isLoading } = useQuery<ProductListResponse>({
    queryKey: ['products', page, search],
    queryFn: async () => {
      const params: Record<string, unknown> = { page, page_size: 20 }
      if (search) params.search = search
      const res = await apiClient.get('/products', { params })
      return res.data
    },
  })

  // 自动抓取
  const scrapeMutation = useMutation({
    mutationFn: async (productUrl: string) => {
      // Just One/数据源可能耗时较长，单独放宽抓取请求超时，避免前端先断开。
      const res = await apiClient.post(
        '/products/scrape',
        { url: productUrl },
        { timeout: 120000 },
      )
      return res.data
    },
    onSuccess: () => { setUrl(''); queryClient.invalidateQueries({ queryKey: ['products'] }) },
  })

  // 手动创建
  const manualMutation = useMutation({
    mutationFn: async (data: Record<string, unknown>) => {
      const res = await apiClient.post('/products/manual', data)
      return res.data
    },
    onMutate: () => {
      setManualError('')
    },
    onSuccess: () => {
      setManualForm({
        url: '',
        title: '',
        description: '',
        price: '',
        currency: 'CNY',
        brandName: '',
        moq: '',
        leadTimeDays: '',
        sku: '',
        stockQuantity: '',
        mainImageUrl: '',
      })
      queryClient.invalidateQueries({ queryKey: ['products'] })
    },
    onError: (error) => {
      setManualError(toErrorMessage(error, '自有商品创建失败'))
    },
  })

  // 删除单个
  const deleteMutation = useMutation({
    mutationFn: async (id: string) => {
      await apiClient.delete(`/products/${id}`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['products'] })
      setSelected(new Set())
    },
  })

  // 批量删除
  const batchDeleteMutation = useMutation({
    mutationFn: async (ids: string[]) => {
      await apiClient.post('/products/batch-delete', { ids })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['products'] })
      setSelected(new Set())
    },
  })

  // 全量删除
  const deleteAllMutation = useMutation({
    mutationFn: async () => {
      await apiClient.delete('/products')
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['products'] })
      setSelected(new Set())
    },
  })

  const handleScrape = () => {
    if (!url.trim()) return
    scrapeMutation.mutate(url.trim())
  }

  const handleOwnImageUpload = async (
    event: React.ChangeEvent<HTMLInputElement>,
  ) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    const validationError = validateImageUpload(file)
    if (validationError) {
      setManualError(validationError)
      return
    }
    setManualError('')
    setImageUploading(true)
    setImageProgress(0)
    try {
      const asset = await uploadImageFile<{ image_url: string }>(file, {
        onProgress: setImageProgress,
      })
      setManualForm((current) => ({
        ...current,
        mainImageUrl: asset.image_url,
      }))
    } catch (error) {
      setManualError(imageUploadErrorMessage(error))
    } finally {
      setImageUploading(false)
    }
  }

  const toggleSelect = (id: string) => {
    const next = new Set(selected)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    setSelected(next)
  }

  const toggleAll = () => {
    if (!data?.items) return
    if (selected.size === data.items.length) {
      setSelected(new Set())
    } else {
      setSelected(new Set(data.items.map(p => p.id)))
    }
  }

  const handleDeleteClick = (id: string) => {
    setDeleteTarget(id)
    setConfirmDelete('single')
  }

  const executeDelete = () => {
    if (confirmDelete === 'single' && deleteTarget) {
      deleteMutation.mutate(deleteTarget)
    } else if (confirmDelete === 'batch') {
      batchDeleteMutation.mutate(Array.from(selected))
    } else if (confirmDelete === 'all') {
      deleteAllMutation.mutate()
    }
    setConfirmDelete(null)
    setDeleteTarget(null)
  }

  const isDeleting = deleteMutation.isPending || batchDeleteMutation.isPending || deleteAllMutation.isPending

  return (
    <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
      {/* 标题 + 操作栏 */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <Package className="h-6 w-6 text-primary" />
            商品库
          </h1>
          <p className="text-muted-foreground text-sm">1688 链接自动抓取，或录入图片、成本、库存完整的自有货源商品</p>
        </div>
        <div className="flex gap-2">
          {selected.size > 0 && (
            <>
              <span className="text-sm text-muted-foreground self-center">已选 {selected.size} 个</span>
              <Button variant="destructive" size="sm" onClick={() => setConfirmDelete('batch')} className="gap-1">
                <Trash2 className="h-4 w-4" />删除选中
              </Button>
            </>
          )}
          {data && data.total > 0 && (
            <Button variant="outline" size="sm" onClick={() => setConfirmDelete('all')} className="gap-1 text-destructive">
              <Trash2 className="h-4 w-4" />删除全部
            </Button>
          )}
          <Button variant="outline" size="sm" onClick={() => navigate('/app/batch')} className="gap-1">
            <Upload className="mr-1 h-4 w-4" />CSV 批量导入
          </Button>
          <Button variant="outline" size="sm" onClick={() => setEntryMode('own')}>
            <FileInput className="mr-1 h-4 w-4" />录入自有商品
          </Button>
        </div>
      </div>

      <div className="grid overflow-hidden border border-border bg-[var(--factory-panel)] sm:grid-cols-2">
        <button
          type="button"
          aria-pressed={entryMode === '1688'}
          onClick={() => setEntryMode('1688')}
          className={cn(
            'flex min-h-16 items-center gap-3 border-b border-border px-4 py-3 text-left sm:border-b-0 sm:border-r',
            entryMode === '1688'
              ? 'bg-[color:var(--factory-accent)]/8'
              : 'hover:bg-accent/40',
          )}
        >
          <span className="flex h-9 w-9 items-center justify-center border border-border bg-background">
            <LinkIcon className="h-4 w-4 text-[color:var(--factory-accent)]" />
          </span>
          <span>
            <span className="block text-sm font-medium">1688 货源</span>
            <span className="mt-0.5 block text-[11px] text-muted-foreground">
              粘贴链接，自动获取标题、图片、价格和销量
            </span>
          </span>
        </button>
        <button
          type="button"
          aria-pressed={entryMode === 'own'}
          onClick={() => setEntryMode('own')}
          className={cn(
            'flex min-h-16 items-center gap-3 px-4 py-3 text-left',
            entryMode === 'own'
              ? 'bg-[color:var(--factory-accent)]/8'
              : 'hover:bg-accent/40',
          )}
        >
          <span className="flex h-9 w-9 items-center justify-center border border-border bg-background">
            <Package className="h-4 w-4 text-[color:var(--factory-accent)]" />
          </span>
          <span>
            <span className="block text-sm font-medium">自有货源</span>
            <span className="mt-0.5 block text-[11px] text-muted-foreground">
              无需商品链接，支持图片、成本、MOQ、库存和描述
            </span>
          </span>
        </button>
      </div>

      {/* 确认弹窗 */}
      {confirmDelete && (
        <Card className={`${confirmDelete === 'all' ? 'border-destructive' : 'border-destructive/50'} bg-destructive/5`}>
          <CardContent className="pt-4 flex items-start justify-between">
            <div className="flex items-start gap-3">
              <AlertTriangle className="h-5 w-5 text-destructive mt-0.5 shrink-0" />
              <div>
                <p className="font-medium text-sm">
                  {confirmDelete === 'single' ? '确认删除此商品？' :
                   confirmDelete === 'batch' ? `确认删除选中的 ${selected.size} 个商品？` :
                   '确认删除全部商品？'}
                </p>
                <p className="text-xs text-muted-foreground mt-0.5">此操作不可撤销</p>
              </div>
            </div>
            <div className="flex gap-2 shrink-0">
              <Button size="sm" variant="destructive" onClick={executeDelete} disabled={isDeleting}>
                {isDeleting ? '删除中...' : '确认删除'}
              </Button>
              <Button size="sm" variant="outline" onClick={() => setConfirmDelete(null)}>取消</Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* 自动抓取 */}
      {entryMode === '1688' && (
      <Card>
        <CardContent className="pt-6">
          <div className="mb-3">
            <p className="text-sm font-medium">自动抓取仅支持 1688 商品链接</p>
            <p className="mt-1 text-[11px] text-muted-foreground">
              自有商品请切换到“自有货源”，无需填写外部链接。
            </p>
          </div>
          <div className="flex gap-3">
            <div className="relative flex-1">
              <LinkIcon className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="粘贴 1688 商品详情页链接..."
                className="pl-10"
                onKeyDown={(e) => e.key === 'Enter' && handleScrape()}
              />
            </div>
            <Button onClick={handleScrape} disabled={!url.trim() || scrapeMutation.isPending}>
              {scrapeMutation.isPending ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />抓取中</> : <><ExternalLink className="mr-2 h-4 w-4" />自动抓取</>}
            </Button>
          </div>
          {scrapeMutation.data && <p className="mt-2 text-sm text-emerald-600 flex items-center gap-1"><CheckCircle2 className="h-4 w-4" />{scrapeMutation.data.message}</p>}
          {scrapeMutation.error && (
            <div className="mt-2 flex items-start gap-2 text-sm bg-amber-500/10 p-3 rounded-md">
              <AlertCircle className="h-4 w-4 mt-0.5 shrink-0 text-amber-600" />
              <div>
                <p className="text-amber-600 font-medium">抓取失败</p>
                <p className="text-muted-foreground">{toErrorMessage(scrapeMutation.error)}</p>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
      )}

      {/* 自有货源录入 */}
      {entryMode === 'own' && (
        <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }}>
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Plus className="h-4 w-4" />录入自有货源商品
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {manualError && (
                <p className="border border-destructive/30 bg-destructive/8 px-3 py-2 text-xs text-destructive">
                  {manualError}
                </p>
              )}
              <div className="grid gap-4 md:grid-cols-[160px_minmax(0,1fr)]">
                <div>
                  <Label>商品主图</Label>
                  <div className="mt-2 flex aspect-square items-center justify-center overflow-hidden border border-dashed border-border bg-secondary">
                    {manualForm.mainImageUrl ? (
                      <img
                        src={resolveMediaUrl(manualForm.mainImageUrl)}
                        alt="自有商品主图"
                        className="h-full w-full object-contain p-2"
                      />
                    ) : (
                      <ImagePlus className="h-6 w-6 text-muted-foreground" />
                    )}
                  </div>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="mt-2 w-full"
                    disabled={imageUploading}
                    onClick={() => document.getElementById('own-product-image')?.click()}
                  >
                    {imageUploading ? (
                      <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Upload className="mr-2 h-3.5 w-3.5" />
                    )}
                    {imageUploading ? `上传 ${imageProgress}%` : '上传商品图'}
                  </Button>
                  <input
                    id="own-product-image"
                    type="file"
                    accept="image/jpeg,image/png,image/webp"
                    className="hidden"
                    onChange={handleOwnImageUpload}
                  />
                </div>
                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="space-y-2 sm:col-span-2">
                    <Label>商品名称 *</Label>
                    <Input
                      value={manualForm.title}
                      onChange={(event) => setManualForm({ ...manualForm, title: event.target.value })}
                      placeholder="例如：自有品牌 304 不锈钢保温杯 500ml"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>品牌</Label>
                    <Input
                      value={manualForm.brandName}
                      onChange={(event) => setManualForm({ ...manualForm, brandName: event.target.value })}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>商品链接（可选）</Label>
                    <Input
                      value={manualForm.url}
                      onChange={(event) => setManualForm({ ...manualForm, url: event.target.value })}
                      placeholder="没有官网或店铺链接可留空"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>成本价</Label>
                    <Input
                      type="number"
                      min="0"
                      step="0.01"
                      value={manualForm.price}
                      onChange={(event) => setManualForm({ ...manualForm, price: event.target.value })}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>币种</Label>
                    <select
                      value={manualForm.currency}
                      onChange={(event) => setManualForm({ ...manualForm, currency: event.target.value })}
                      className="h-9 w-full border border-input bg-background px-2 text-xs outline-none focus:ring-2 focus:ring-ring"
                    >
                      {['CNY', 'USD', 'EUR', 'GBP', 'JPY'].map((currency) => (
                        <option key={currency} value={currency}>{currency}</option>
                      ))}
                    </select>
                  </div>
                  <div className="space-y-2">
                    <Label>MOQ</Label>
                    <Input
                      type="number"
                      min="0"
                      value={manualForm.moq}
                      onChange={(event) => setManualForm({ ...manualForm, moq: event.target.value })}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>交付周期（天）</Label>
                    <Input
                      type="number"
                      min="0"
                      value={manualForm.leadTimeDays}
                      onChange={(event) => setManualForm({ ...manualForm, leadTimeDays: event.target.value })}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>初始 SKU</Label>
                    <Input
                      value={manualForm.sku}
                      onChange={(event) => setManualForm({ ...manualForm, sku: event.target.value })}
                      placeholder="例如 OWN-CUP-500"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>初始库存</Label>
                    <Input
                      type="number"
                      min="0"
                      value={manualForm.stockQuantity}
                      onChange={(event) => setManualForm({ ...manualForm, stockQuantity: event.target.value })}
                    />
                  </div>
                  <div className="space-y-2 sm:col-span-2">
                    <Label>商品描述</Label>
                    <textarea
                      value={manualForm.description}
                      onChange={(event) => setManualForm({ ...manualForm, description: event.target.value })}
                      className="min-h-24 w-full resize-y border border-input bg-background px-3 py-2 text-sm leading-6 outline-none focus:ring-2 focus:ring-ring"
                      placeholder="材质、尺寸、规格、包装和核心卖点"
                    />
                  </div>
                </div>
              </div>
              <div className="flex gap-2 justify-end">
                <Button variant="outline" onClick={() => setEntryMode('1688')}>取消</Button>
                <Button
                  onClick={() => manualMutation.mutate(buildOwnProductPayload(manualForm))}
                  disabled={!manualForm.title.trim() || manualMutation.isPending || imageUploading}
                >
                  {manualMutation.isPending ? '保存中...' : '保存自有商品'}
                </Button>
              </div>
            </CardContent>
          </Card>
        </motion.div>
      )}

      {/* 搜索与商品总量 */}
      <div className="flex items-center justify-between">
        <div className="relative max-w-sm flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input value={search} onChange={(e) => { setSearch(e.target.value); setPage(1) }} placeholder="搜索商品…" className="pl-10" />
        </div>
        {data && (
          <span className="metric-number text-xs text-muted-foreground">
            {data.total} 个商品
          </span>
        )}
      </div>

      {/* 商品目录 */}
      {isLoading ? (
        <div className="flex justify-center py-12"><Loader2 className="h-8 w-8 animate-spin text-muted-foreground" /></div>
      ) : data?.items?.length ? (
        <>
          <Card className="overflow-hidden">
            <div className="flex items-center justify-between gap-4 border-b border-border px-4 py-3">
              <label className="flex items-center gap-2 text-xs text-muted-foreground">
                <input
                  type="checkbox"
                  checked={selected.size === data.items.length}
                  onChange={toggleAll}
                  aria-label="全选当前页商品"
                  className="rounded border-input"
                />
                全选
              </label>
              <div className="flex items-center gap-3">
                {selected.size > 0 && (
                  <span className="text-xs text-muted-foreground">已选 {selected.size} 个</span>
                )}
                <span className="text-xs text-muted-foreground">按最近录入排序</span>
              </div>
            </div>
            <div className="divide-y divide-border">
              {data.items.map((product) => (
                <div
                  key={product.id}
                  className="grid grid-cols-[20px_56px_minmax(0,1fr)_36px] items-center gap-3 px-4 py-3 hover:bg-accent/60"
                >
                  <input
                    type="checkbox"
                    checked={selected.has(product.id)}
                    onChange={() => toggleSelect(product.id)}
                    aria-label={`选择 ${product.title || '无标题商品'}`}
                    className="rounded border-input"
                  />
                  <button
                    type="button"
                    onClick={() => navigate(`/app/products/${product.id}`)}
                    className="flex h-14 w-14 items-center justify-center overflow-hidden rounded border border-border bg-secondary"
                    aria-label={`打开 ${product.title || '无标题商品'}`}
                  >
                    {product.main_image_url ? (
                      <img
                        src={resolveMediaUrl(product.main_image_url)}
                        alt=""
                        className="h-full w-full object-cover"
                        loading="lazy"
                      />
                    ) : (
                      <ShoppingBag className="h-6 w-6 text-muted-foreground" aria-hidden="true" />
                    )}
                  </button>
                  <div className="min-w-0">
                    <button
                      type="button"
                      onClick={() => navigate(`/app/products/${product.id}`)}
                      className="block max-w-full truncate text-left text-[13px] font-medium hover:underline"
                    >
                      {product.title || '无标题商品'}
                    </button>
                    <div className="mt-1 flex items-center gap-2">
                      <Badge variant="outline" className="text-[9px]">
                        {productOriginLabel(product.origin_type)}
                      </Badge>
                      {product.brand_name && (
                        <span className="truncate text-[10px] text-muted-foreground">
                          {product.brand_name}
                        </span>
                      )}
                    </div>
                    <p className="mt-1 truncate text-xs text-muted-foreground">
                      {product.shop_name || (product.origin_type === 'own' ? '卖家自有货源' : '1688 来源商品')}
                      {product.sales_count != null ? ` · 已售 ${product.sales_count}` : ''}
                      {` · ${new Date(product.created_at).toLocaleDateString('zh-CN')}`}
                    </p>
                    <div className="mt-1.5 flex items-center gap-3">
                      {product.price != null && (
                        <span className="metric-number text-sm font-medium">
                          {product.origin_type === 'own' ? '成本' : '供货'}{' '}
                          {product.cost_currency || 'CNY'} {product.price.toFixed(2)}
                        </span>
                      )}
                      {product.moq != null && (
                        <span className="text-[10px] text-muted-foreground">
                          MOQ {product.moq}
                        </span>
                      )}
                    </div>
                  </div>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 text-muted-foreground hover:text-destructive"
                    onClick={() => handleDeleteClick(product.id)}
                    aria-label={`删除 ${product.title || '无标题商品'}`}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              ))}
            </div>
          </Card>
          {data.total_pages > 1 && (
            <div className="flex justify-center gap-2 mt-4">
              <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>上一页</Button>
              <span className="flex items-center text-sm px-2 text-muted-foreground">{page} / {data.total_pages}</span>
              <Button variant="outline" size="sm" disabled={page >= data.total_pages} onClick={() => setPage(page + 1)}>下一页</Button>
            </div>
          )}
        </>
      ) : (
        <div className="flex flex-col items-center py-16 text-muted-foreground">
          <ShoppingBag className="h-12 w-12 mb-3 opacity-50" />
          <p className="text-sm">暂无商品</p>
          <p className="text-xs mt-1">粘贴 1688 链接，或切换到自有货源录入商品</p>
        </div>
      )}
    </motion.div>
  )
}
