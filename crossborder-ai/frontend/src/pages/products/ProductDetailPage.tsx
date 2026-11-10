import { useEffect, useState } from 'react'
import { useParams, useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import {
  ArrowLeft,
  ExternalLink,
  Sparkles,
  ShoppingBag,
  Globe,
  Loader2,
  Clock,
  ChevronDown,
  ChevronUp,
  Trash2,
  AlertTriangle,
  Plus,
  Layers,
  Boxes,
  Save,
  X,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import apiClient from '@/api/client'
import { toErrorMessage } from '@/utils/errorMessage'

const PLATFORMS = [
  { id: 'amazon', label: 'Amazon', color: 'bg-amber-500/10 text-amber-600' },
  { id: 'ebay', label: 'eBay', color: 'bg-amber-500/10 text-amber-500' },
  { id: 'shopify', label: 'Shopify', color: 'bg-emerald-500/10 text-emerald-600' },
  { id: 'etsy', label: 'Etsy', color: 'bg-orange-500/10 text-orange-600' },
  { id: 'shein', label: 'SHEIN', color: 'bg-green-600/10 text-green-600' },
  { id: 'temu', label: 'Temu', color: 'bg-red-500/10 text-red-600' },
  { id: 'tiktok', label: 'TikTok Shop', color: 'bg-purple-500/10 text-purple-600' },
  { id: 'aliexpress', label: 'AliExpress', color: 'bg-rose-500/10 text-rose-600' },
  { id: 'walmart', label: 'Walmart', color: 'bg-sky-500/10 text-sky-600' },
  { id: 'shopee', label: 'Shopee', color: 'bg-orange-600/10 text-orange-600' },
  { id: 'lazada', label: 'Lazada', color: 'bg-amber-500/10 text-amber-500' },
]

interface ProductVariant {
  id: string
  sku: string
  name: string | null
  attributes: Record<string, string>
  price: number | null
  cost_price: number | null
  stock_quantity: number
  barcode: string | null
  image_url: string | null
  is_active: boolean
}

function parseAttributes(text: string): Record<string, string> {
  const attributes: Record<string, string> = {}
  for (const part of text.split(/[,，]/)) {
    const [rawKey, ...rawValue] = part.split(/[=:：]/)
    const key = rawKey?.trim()
    const value = rawValue.join('=').trim()
    if (key && value) attributes[key] = value
  }
  return attributes
}

export default function ProductDetailPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const queryClient = useQueryClient()
  const [showAllPlatforms, setShowAllPlatforms] = useState(false)
  const [editingListingId, setEditingListingId] = useState(searchParams.get('listing') || '')
  const [editTitle, setEditTitle] = useState('')
  const [editDescription, setEditDescription] = useState('')
  const [editBullets, setEditBullets] = useState('')
  const [editingVariantId, setEditingVariantId] = useState('')
  const [variantSku, setVariantSku] = useState('')
  const [variantName, setVariantName] = useState('')
  const [variantAttributes, setVariantAttributes] = useState('')
  const [variantPrice, setVariantPrice] = useState('')
  const [variantCost, setVariantCost] = useState('')
  const [variantStock, setVariantStock] = useState('0')
  const [isBatchStockEditing, setIsBatchStockEditing] = useState(false)
  const [batchStockValues, setBatchStockValues] = useState<Record<string, string>>({})

  const { data: product, isLoading } = useQuery({
    queryKey: ['product', id],
    queryFn: async () => {
      const res = await apiClient.get(`/products/${id}`)
      return res.data
    },
    enabled: !!id,
  })

  const { data: history } = useQuery({
    queryKey: ['product-history', id],
    queryFn: async () => {
      const res = await apiClient.get(`/products/${id}/listings`)
      return res.data
    },
    enabled: !!id,
  })

  const { data: variantsData } = useQuery({
    queryKey: ['product-variants', id],
    queryFn: async () => {
      const response = await apiClient.get(`/products/${id}/variants`)
      return response.data as { items: ProductVariant[]; total: number }
    },
    enabled: !!id,
  })

  const { data: editingListing } = useQuery({
    queryKey: ['listing-detail', editingListingId],
    queryFn: async () => {
      const res = await apiClient.get(`/listings/${editingListingId}`)
      return res.data
    },
    enabled: !!editingListingId,
  })

  useEffect(() => {
    if (!editingListing) return
    setEditTitle(editingListing.title || '')
    setEditDescription(editingListing.description || '')
    setEditBullets((editingListing.bullet_points || []).join('\n'))
  }, [editingListing])

  const saveAndRecheckMutation = useMutation({
    mutationFn: async () => {
      await apiClient.put(`/listings/${editingListingId}`, {
        title: editTitle,
        description: editDescription,
        bullet_points: editBullets.split('\n').map((line) => line.trim()).filter(Boolean),
      })
      const checked = await apiClient.post(`/listings/${editingListingId}/compliance`)
      return checked.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['product-history', id] })
      queryClient.invalidateQueries({ queryKey: ['listing-detail', editingListingId] })
    },
  })

  // 删除商品
  const deleteMutation = useMutation({
    mutationFn: async () => {
      await apiClient.delete(`/products/${id}`)
    },
    onSuccess: () => navigate('/app/products'),
  })
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)

  const resetVariantForm = () => {
    setEditingVariantId('')
    setVariantSku('')
    setVariantName('')
    setVariantAttributes('')
    setVariantPrice('')
    setVariantCost('')
    setVariantStock('0')
  }

  const startEditVariant = (variant: ProductVariant) => {
    setEditingVariantId(variant.id)
    setVariantSku(variant.sku)
    setVariantName(variant.name || '')
    setVariantAttributes(
      Object.entries(variant.attributes || {}).map(([key, value]) => `${key}=${value}`).join(','),
    )
    setVariantPrice(variant.price == null ? '' : String(variant.price))
    setVariantCost(variant.cost_price == null ? '' : String(variant.cost_price))
    setVariantStock(String(variant.stock_quantity))
  }

  const saveVariantMutation = useMutation({
    mutationFn: async () => {
      const payload = {
        sku: variantSku.trim(),
        name: variantName.trim() || null,
        attributes: parseAttributes(variantAttributes),
        price: variantPrice ? Number(variantPrice) : null,
        cost_price: variantCost ? Number(variantCost) : null,
        stock_quantity: Number(variantStock || 0),
      }
      if (editingVariantId) {
        const response = await apiClient.put(
          `/products/${id}/variants/${editingVariantId}`,
          payload,
        )
        return response.data
      }
      const response = await apiClient.post(`/products/${id}/variants`, payload)
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['product-variants', id] })
      resetVariantForm()
    },
  })

  const deleteVariantMutation = useMutation({
    mutationFn: async (variantId: string) => {
      await apiClient.delete(`/products/${id}/variants/${variantId}`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['product-variants', id] })
      if (editingVariantId) resetVariantForm()
    },
  })

  const batchStockMutation = useMutation({
    mutationFn: async () => {
      const items = (variantsData?.items || []).map((variant) => ({
        variant_id: variant.id,
        stock_quantity: Number(batchStockValues[variant.id] ?? variant.stock_quantity),
      }))
      const response = await apiClient.patch(`/products/${id}/variants/batch-stock`, {
        items,
      })
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['product-variants', id] })
      setIsBatchStockEditing(false)
      setBatchStockValues({})
    },
  })

  const startBatchStockEditing = () => {
    // 以当前库存为初值，只提交用户真正调整后的整组库存。
    setBatchStockValues(
      Object.fromEntries(
        (variantsData?.items || []).map((variant) => [
          variant.id,
          String(variant.stock_quantity),
        ]),
      ),
    )
    setIsBatchStockEditing(true)
  }

  const cancelBatchStockEditing = () => {
    setIsBatchStockEditing(false)
    setBatchStockValues({})
    batchStockMutation.reset()
  }

  const hasInvalidBatchStock = (variantsData?.items || []).some((variant) => {
    const value = Number(batchStockValues[variant.id] ?? variant.stock_quantity)
    return !Number.isInteger(value) || value < 0
  })

  if (isLoading) {
    return (
      <div className="flex justify-center py-20">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (!product) {
    return (
      <div className="flex flex-col items-center py-20 text-muted-foreground">
        <ShoppingBag className="h-12 w-12 mb-4 opacity-50" />
        <p>商品不存在</p>
        <Button variant="link" onClick={() => navigate('/app/products')}>返回商品列表</Button>
      </div>
    )
  }

  return (
    <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
      {/* 返回按钮 */}
      <Button variant="ghost" size="sm" onClick={() => navigate('/app/products')}>
        <ArrowLeft className="h-4 w-4 mr-1" /> 返回商品列表
      </Button>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* 左：商品信息 */}
        <div className="space-y-4 lg:col-span-1">
          <Card>
            <div className="aspect-square bg-muted flex items-center justify-center overflow-hidden rounded-t-xl">
              {product.main_image_url ? (
                <img src={product.main_image_url} alt={product.title} className="h-full w-full object-cover" />
              ) : (
                <ShoppingBag className="h-16 w-16 text-muted-foreground/30" />
              )}
            </div>
            <CardContent className="p-4 space-y-3">
              <h1 className="font-semibold leading-snug">{product.title || '无标题'}</h1>
              <div className="flex items-center justify-between">
                {product.price != null && (
                  <span className="text-2xl font-bold text-primary">¥{product.price.toFixed(2)}</span>
                )}
                {product.sales_count != null && (
                  <Badge variant="secondary">已售 {product.sales_count}</Badge>
                )}
              </div>
              {product.shop_name && (
                <p className="text-sm text-muted-foreground">店铺: {product.shop_name}</p>
              )}
              <a
                href={product.url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1 text-xs text-primary hover:underline"
              >
                <ExternalLink className="h-3 w-3" />
                查看 1688 原链接
              </a>
            </CardContent>
          </Card>
        </div>

        {/* 右：操作区 */}
        <div className="space-y-4 lg:col-span-2">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="text-base flex items-center gap-2">
                <Layers className="h-4 w-4" />SKU 变体
              </CardTitle>
              <div className="flex items-center gap-2">
                <Badge variant="secondary">{variantsData?.total || 0} 个</Badge>
                {isBatchStockEditing ? (
                  <>
                    <Button
                      size="sm"
                      onClick={() => batchStockMutation.mutate()}
                      disabled={batchStockMutation.isPending || hasInvalidBatchStock}
                    >
                      <Save className="h-3.5 w-3.5 mr-1" />
                      {batchStockMutation.isPending ? '保存中' : '保存库存'}
                    </Button>
                    <Button
                      size="icon"
                      variant="ghost"
                      onClick={cancelBatchStockEditing}
                      disabled={batchStockMutation.isPending}
                      aria-label="取消批量库存编辑"
                    >
                      <X className="h-4 w-4" />
                    </Button>
                  </>
                ) : (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={startBatchStockEditing}
                    disabled={!variantsData?.items?.length}
                  >
                    <Boxes className="h-3.5 w-3.5 mr-1" />
                    批量库存
                  </Button>
                )}
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              {batchStockMutation.isError && (
                <p className="text-xs text-destructive">
                  {toErrorMessage(batchStockMutation.error, '批量库存保存失败')}
                </p>
              )}
              {variantsData?.items?.length ? (
                <div className="space-y-2">
                  {variantsData.items.map((variant) => (
                    <div key={variant.id} className="rounded-md border p-3 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                      <div className="min-w-0 w-full">
                        <div className="flex items-center gap-2">
                          <p className="text-sm font-medium truncate">{variant.sku}</p>
                          <Badge
                            variant={variant.is_active ? 'secondary' : 'outline'}
                            className="shrink-0 whitespace-nowrap"
                          >
                            {variant.is_active ? '启用' : '停用'}
                          </Badge>
                        </div>
                        <p className="text-xs text-muted-foreground mt-1">
                          {Object.entries(variant.attributes || {}).map(([key, value]) => `${key}:${value}`).join(' · ') || variant.name || '无属性'}
                        </p>
                        <div className="mt-1 flex items-center gap-1 text-xs text-muted-foreground">
                          <span>售价 {variant.price == null ? '-' : `¥${variant.price}`}</span>
                          <span>·</span>
                          <span>库存</span>
                          {isBatchStockEditing ? (
                            <Input
                              type="number"
                              min="0"
                              step="1"
                              value={batchStockValues[variant.id] ?? String(variant.stock_quantity)}
                              onChange={(event) =>
                                setBatchStockValues((current) => ({
                                  ...current,
                                  [variant.id]: event.target.value,
                                }))
                              }
                              className="h-7 w-24"
                              aria-label={`${variant.sku} 库存`}
                            />
                          ) : (
                            <span>{variant.stock_quantity}</span>
                          )}
                        </div>
                      </div>
                      <div className="flex items-center gap-1 shrink-0 self-end sm:self-auto">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => startEditVariant(variant)}
                          disabled={isBatchStockEditing}
                        >
                          编辑
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="text-destructive"
                          disabled={deleteVariantMutation.isPending || isBatchStockEditing}
                          onClick={() => deleteVariantMutation.mutate(variant.id)}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">暂无 SKU 变体</p>
              )}

              <div className="rounded-lg border bg-muted/20 p-3 space-y-3">
                <p className="text-sm font-medium flex items-center gap-1">
                  {editingVariantId ? '编辑变体' : <><Plus className="h-4 w-4" />新增变体</>}
                </p>
                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="space-y-1.5"><Label>SKU *</Label><Input value={variantSku} onChange={(e) => setVariantSku(e.target.value)} /></div>
                  <div className="space-y-1.5"><Label>名称</Label><Input value={variantName} onChange={(e) => setVariantName(e.target.value)} /></div>
                  <div className="space-y-1.5 sm:col-span-2"><Label>属性（颜色=白色,尺寸=L）</Label><Input value={variantAttributes} onChange={(e) => setVariantAttributes(e.target.value)} /></div>
                  <div className="space-y-1.5"><Label>售价</Label><Input type="number" min="0" value={variantPrice} onChange={(e) => setVariantPrice(e.target.value)} /></div>
                  <div className="space-y-1.5"><Label>成本价</Label><Input type="number" min="0" value={variantCost} onChange={(e) => setVariantCost(e.target.value)} /></div>
                  <div className="space-y-1.5"><Label>库存</Label><Input type="number" min="0" value={variantStock} onChange={(e) => setVariantStock(e.target.value)} /></div>
                </div>
                <div className="flex gap-2">
                  <Button size="sm" onClick={() => saveVariantMutation.mutate()} disabled={!variantSku.trim() || saveVariantMutation.isPending}>
                    {saveVariantMutation.isPending ? '保存中...' : editingVariantId ? '保存修改' : '添加变体'}
                  </Button>
                  {editingVariantId && <Button size="sm" variant="outline" onClick={resetVariantForm}>取消编辑</Button>}
                </div>
                {saveVariantMutation.isError && <p className="text-xs text-destructive">保存失败，请检查 SKU 是否重复。</p>}
              </div>
            </CardContent>
          </Card>

          {/* 一键生成 */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-primary" />
                AI 生成 Listing
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground mb-4">
                选择平台，AI 自动生成适配的标题、描述和卖点
              </p>
              <div className="grid gap-3 grid-cols-2 sm:grid-cols-3">
                {(showAllPlatforms ? PLATFORMS : PLATFORMS.slice(0, 4)).map((p) => (
                  <Button
                    key={p.id}
                    variant="outline"
                    className="justify-start h-auto py-3 px-4"
                    onClick={() => navigate(`/app/content?product=${id}&platform=${p.id}`)}
                  >
                    <Globe className="h-4 w-4 mr-2 shrink-0" />
                    <div className="text-left">
                      <p className="text-sm font-medium">{p.label}</p>
                      <p className="text-xs text-muted-foreground">生成 Listing</p>
                    </div>
                  </Button>
                ))}
              </div>
              <Button
                variant="ghost"
                size="sm"
                className="mt-2"
                onClick={() => setShowAllPlatforms(!showAllPlatforms)}
              >
                {showAllPlatforms ? (
                  <>收起 <ChevronUp className="h-3 w-3 ml-1" /></>
                ) : (
                  <>全部平台 ({PLATFORMS.length}) <ChevronDown className="h-3 w-3 ml-1" /></>
                )}
              </Button>
            </CardContent>
          </Card>

          {/* 生成历史 */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Clock className="h-4 w-4 text-muted-foreground" />
                生成历史
              </CardTitle>
            </CardHeader>
            <CardContent>
              {history?.items?.length > 0 ? (
                <div className="space-y-2">
                  {history.items.map((item: any) => (
                    <div key={item.id} className="flex items-center justify-between rounded-md border p-3">
                      <div>
                        <div className="flex items-center gap-2">
                          <p className="text-sm font-medium">{item.platform}</p>
                          <Badge variant={item.compliance_status === 'pass' ? 'secondary' : 'destructive'}>
                            {item.compliance_status === 'pass' ? '合规通过' : '禁止发布'}
                          </Badge>
                        </div>
                        <p className="text-xs text-muted-foreground line-clamp-1 mt-0.5">{item.title}</p>
                        <p className="text-xs text-muted-foreground">{item.created_at}</p>
                      </div>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setEditingListingId(item.id)}
                      >
                        编辑并复审
                      </Button>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="flex flex-col items-center py-8 text-muted-foreground">
                  <Clock className="h-8 w-8 mb-2 opacity-40" />
                  <p className="text-sm">暂无生成记录</p>
                  <p className="text-xs mt-1">点击上方按钮生成第一个 Listing</p>
                </div>
              )}
            </CardContent>
          </Card>

          {editingListingId && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">编辑 Listing</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {saveAndRecheckMutation.isSuccess && (
                  <div className="rounded-md border bg-muted/30 p-3">
                    <div className="flex items-center gap-2 mb-1">
                      <Badge variant={saveAndRecheckMutation.data?.compliance_status === 'pass' ? 'secondary' : 'destructive'}>
                        {saveAndRecheckMutation.data?.compliance_status === 'pass' ? '合规通过' : '禁止发布'}
                      </Badge>
                      <span className="text-xs text-muted-foreground">版本 {saveAndRecheckMutation.data?.version}</span>
                    </div>
                    {saveAndRecheckMutation.data?.violations?.length > 0 && (
                      <p className="text-xs text-destructive">
                        命中：{saveAndRecheckMutation.data.violations.join('、')}
                      </p>
                    )}
                  </div>
                )}
                {saveAndRecheckMutation.isError && (
                  <p className="text-sm text-destructive">
                    {toErrorMessage(saveAndRecheckMutation.error, '保存失败')}
                  </p>
                )}
                <div className="space-y-2">
                  <Label>标题</Label>
                  <Input value={editTitle} onChange={(e) => setEditTitle(e.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label>描述</Label>
                  <textarea
                    value={editDescription}
                    onChange={(e) => setEditDescription(e.target.value)}
                    className="min-h-28 w-full rounded-md border bg-background px-3 py-2 text-sm outline-none focus:border-primary/50"
                  />
                </div>
                <div className="space-y-2">
                  <Label>卖点（每行一条）</Label>
                  <textarea
                    value={editBullets}
                    onChange={(e) => setEditBullets(e.target.value)}
                    className="min-h-24 w-full rounded-md border bg-background px-3 py-2 text-sm outline-none focus:border-primary/50"
                  />
                </div>
                <div className="flex gap-2">
                  <Button
                    className="flex-1"
                    onClick={() => saveAndRecheckMutation.mutate()}
                    disabled={!editTitle.trim() || saveAndRecheckMutation.isPending}
                  >
                    {saveAndRecheckMutation.isPending ? (
                      <><Loader2 className="h-4 w-4 mr-2 animate-spin" />保存并检查</>
                    ) : (
                      '保存并重新合规'
                    )}
                  </Button>
                  <Button variant="outline" onClick={() => setEditingListingId('')}>
                    关闭
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}

          {/* 删除商品 */}
          <Card className="border-destructive/20">
            <CardContent className="pt-4">
              {showDeleteConfirm ? (
                <div className="space-y-3">
                  <div className="flex items-start gap-2 text-sm">
                    <AlertTriangle className="h-4 w-4 text-destructive mt-0.5 shrink-0" />
                    <p>确定要删除这个商品吗？此操作不可撤销。</p>
                  </div>
                  <div className="flex gap-2">
                    <Button variant="destructive" size="sm" onClick={() => deleteMutation.mutate()} disabled={deleteMutation.isPending}>
                      {deleteMutation.isPending ? '删除中...' : '确认删除'}
                    </Button>
                    <Button variant="outline" size="sm" onClick={() => setShowDeleteConfirm(false)}>取消</Button>
                  </div>
                </div>
              ) : (
                <Button variant="outline" size="sm" className="text-destructive gap-1 w-full" onClick={() => setShowDeleteConfirm(true)}>
                  <Trash2 className="h-4 w-4" />删除商品
                </Button>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </motion.div>
  )
}
