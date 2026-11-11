import { useDeferredValue, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import {
  CheckCircle2,
  ChevronRight,
  CircleDot,
  Layers,
  Loader2,
  PackageSearch,
  Plus,
  Search,
  Sparkles,
  Table2,
} from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import apiClient from '@/api/client'
import {
  buildBulkVariantPatch,
  parseAttributeGroups,
  type BulkEditableFields,
  type CatalogListing,
  type CatalogVariant,
} from '@/lib/catalog/catalog'
import type { WorkbenchAsset } from '@/lib/images/workbench'
import { toErrorMessage } from '@/utils/errorMessage'

interface ProductOption {
  id: string
  title: string | null
}

interface MatrixResponse {
  created: number
  skipped: number
}

const EMPTY_BULK_FIELDS: BulkEditableFields = {
  price: '',
  cost_price: '',
  stock_quantity: '',
  is_active: '',
  image_url: '',
}

const PLATFORM_LABELS: Record<string, string> = {
  amazon: 'Amazon',
  shopify: 'Shopify',
  ebay: 'eBay',
  temu: 'Temu',
  shein: 'SHEIN',
  tiktok: 'TikTok Shop',
  aliexpress: 'AliExpress',
  walmart: 'Walmart',
}

export default function CatalogPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [tab, setTab] = useState('variants')
  const [search, setSearch] = useState('')
  const deferredSearch = useDeferredValue(search)
  const [stockFilter, setStockFilter] = useState<'all' | 'active' | 'inactive' | 'low'>('all')
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [bulkFields, setBulkFields] = useState<BulkEditableFields>(EMPTY_BULK_FIELDS)
  const [showMatrix, setShowMatrix] = useState(false)
  const [matrixProductId, setMatrixProductId] = useState('')
  const [matrixGroups, setMatrixGroups] = useState('颜色=黑色,白色\n尺寸=M,L')
  const [matrixPrefix, setMatrixPrefix] = useState('SKU')
  const [matrixPrice, setMatrixPrice] = useState('')
  const [matrixCost, setMatrixCost] = useState('')
  const [matrixStock, setMatrixStock] = useState('0')
  const [matrixMessage, setMatrixMessage] = useState('')
  const [actionError, setActionError] = useState('')
  const [platformFilter, setPlatformFilter] = useState('all')
  const [listingSearch, setListingSearch] = useState('')

  const variantsQuery = useQuery<{ items: CatalogVariant[]; total: number }>({
    queryKey: ['catalog-variants'],
    queryFn: async () => {
      const response = await apiClient.get('/catalog/variants', {
        params: { limit: 500 },
      })
      return response.data
    },
  })

  const listingsQuery = useQuery<{ items: CatalogListing[]; total: number }>({
    queryKey: ['catalog-listings'],
    queryFn: async () => {
      const response = await apiClient.get('/catalog/listings', {
        params: { limit: 500 },
      })
      return response.data
    },
    enabled: tab === 'listings',
  })

  const productsQuery = useQuery<{ items: ProductOption[] }>({
    queryKey: ['catalog-product-options'],
    queryFn: async () => {
      const response = await apiClient.get('/products', {
        params: { page_size: 100 },
      })
      return response.data
    },
  })

  const assetsQuery = useQuery<WorkbenchAsset[]>({
    queryKey: ['catalog-image-assets'],
    queryFn: async () => {
      const response = await apiClient.get('/images/assets')
      return response.data.items || []
    },
  })

  const variants = variantsQuery.data?.items || []
  const filteredVariants = useMemo(() => {
    const keyword = deferredSearch.trim().toLowerCase()
    return variants.filter((variant) => {
      if (keyword) {
        const haystack = `${variant.product_title} ${variant.sku} ${variant.name || ''}`.toLowerCase()
        if (!haystack.includes(keyword)) return false
      }
      if (stockFilter === 'active' && !variant.is_active) return false
      if (stockFilter === 'inactive' && variant.is_active) return false
      if (stockFilter === 'low' && variant.stock_quantity >= 10) return false
      return true
    })
  }, [deferredSearch, stockFilter, variants])

  const listings = useMemo(() => {
    const keyword = listingSearch.trim().toLowerCase()
    return (listingsQuery.data?.items || []).filter((listing) => {
      if (platformFilter !== 'all' && listing.platform !== platformFilter) return false
      if (!keyword) return true
      return `${listing.product_title} ${listing.title}`.toLowerCase().includes(keyword)
    })
  }, [listingSearch, listingsQuery.data?.items, platformFilter])

  const summary = useMemo(() => {
    const lowStock = variants.filter((item) => item.stock_quantity < 10).length
    const active = variants.filter((item) => item.is_active).length
    const averageMarginValues = variants
      .filter((item) => item.price && item.cost_price != null)
      .map((item) => (((item.price || 0) - (item.cost_price || 0)) / (item.price || 1)) * 100)
    const averageMargin = averageMarginValues.length
      ? averageMarginValues.reduce((sum, value) => sum + value, 0) / averageMarginValues.length
      : null
    return { total: variants.length, active, lowStock, averageMargin }
  }, [variants])

  const matrixMutation = useMutation({
    mutationFn: async () => {
      const attributeGroups = parseAttributeGroups(matrixGroups)
      if (!matrixProductId) throw new Error('请选择商品')
      if (!Object.keys(attributeGroups).length) throw new Error('请填写有效的属性组合')
      const response = await apiClient.post<MatrixResponse>(
        `/catalog/products/${matrixProductId}/variants/generate`,
        {
          attribute_groups: attributeGroups,
          sku_prefix: matrixPrefix,
          price: matrixPrice ? Number(matrixPrice) : null,
          cost_price: matrixCost ? Number(matrixCost) : null,
          stock_quantity: Number(matrixStock || 0),
        },
      )
      return response.data
    },
    onMutate: () => {
      setActionError('')
      setMatrixMessage('')
    },
    onSuccess: (data) => {
      setMatrixMessage(`已生成 ${data.created} 个变体，跳过 ${data.skipped} 个重复组合`)
      queryClient.invalidateQueries({ queryKey: ['catalog-variants'] })
    },
    onError: (error) => setActionError(toErrorMessage(error, '变体矩阵生成失败')),
  })

  const bulkMutation = useMutation({
    mutationFn: async () => {
      const payload = buildBulkVariantPatch(selectedIds, bulkFields)
      if (Object.keys(payload).length === 1) throw new Error('请至少填写一个修改字段')
      const response = await apiClient.patch('/catalog/variants/bulk', payload)
      return response.data
    },
    onMutate: () => setActionError(''),
    onSuccess: () => {
      setBulkFields(EMPTY_BULK_FIELDS)
      setSelectedIds([])
      queryClient.invalidateQueries({ queryKey: ['catalog-variants'] })
    },
    onError: (error) => setActionError(toErrorMessage(error, '批量修改失败')),
  })

  const toggleVariant = (variantId: string) => {
    setSelectedIds((current) =>
      current.includes(variantId)
        ? current.filter((id) => id !== variantId)
        : [...current, variantId],
    )
  }

  const allVisibleSelected =
    filteredVariants.length > 0 &&
    filteredVariants.every((variant) => selectedIds.includes(variant.id))

  const toggleAllVisible = () => {
    const visibleIds = filteredVariants.map((variant) => variant.id)
    if (allVisibleSelected) {
      setSelectedIds((current) => current.filter((id) => !visibleIds.includes(id)))
    } else {
      setSelectedIds((current) => [...new Set([...current, ...visibleIds])])
    }
  }

  const imageAssets = (assetsQuery.data || []).filter((asset) => asset.image_url)

  return (
    <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="page-title flex items-center gap-2">
            <Layers className="h-6 w-6 text-primary" />
            Listing 中心
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            管理变体、价格、库存、素材和多平台 Listing 就绪状态。
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={() => navigate('/app/content')}>
            <Sparkles className="mr-2 h-4 w-4" />
            AI 生成 Listing
          </Button>
          <Button onClick={() => setShowMatrix((value) => !value)}>
            <Plus className="mr-2 h-4 w-4" />
            生成变体矩阵
          </Button>
        </div>
      </div>

      {actionError && (
        <div className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {actionError}
        </div>
      )}

      {showMatrix && (
        <Card className="border-primary/20 bg-primary/5">
          <CardHeader>
            <CardTitle className="text-sm">变体矩阵生成</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              <div className="space-y-1.5">
                <Label>商品</Label>
                <select
                  value={matrixProductId}
                  onChange={(event) => setMatrixProductId(event.target.value)}
                  className="h-10 w-full rounded-md border bg-background px-3 text-sm"
                >
                  <option value="">选择商品</option>
                  {(productsQuery.data?.items || []).map((product) => (
                    <option key={product.id} value={product.id}>
                      {product.title || '无标题商品'}
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-1.5">
                <Label>SKU 前缀</Label>
                <Input value={matrixPrefix} onChange={(event) => setMatrixPrefix(event.target.value)} />
              </div>
              <div className="space-y-1.5">
                <Label>默认售价</Label>
                <Input type="number" min="0" value={matrixPrice} onChange={(event) => setMatrixPrice(event.target.value)} />
              </div>
              <div className="space-y-1.5">
                <Label>默认库存</Label>
                <Input type="number" min="0" step="1" value={matrixStock} onChange={(event) => setMatrixStock(event.target.value)} />
              </div>
            </div>
            <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_220px]">
              <div className="space-y-1.5">
                <Label>属性组合</Label>
                <textarea
                  value={matrixGroups}
                  onChange={(event) => setMatrixGroups(event.target.value)}
                  rows={5}
                  className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  placeholder="颜色=黑色,白色&#10;尺寸=M,L"
                />
                <p className="text-xs text-muted-foreground">每行一个属性，用等号分隔属性名和值。</p>
              </div>
              <div className="space-y-1.5">
                <Label>默认成本</Label>
                <Input type="number" min="0" value={matrixCost} onChange={(event) => setMatrixCost(event.target.value)} />
                <Button
                  className="mt-2 w-full"
                  onClick={() => matrixMutation.mutate()}
                  disabled={matrixMutation.isPending}
                >
                  {matrixMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Sparkles className="mr-2 h-4 w-4" />}
                  {matrixMutation.isPending ? '生成中...' : '生成变体'}
                </Button>
              </div>
            </div>
            {matrixMessage && (
              <p className="flex items-center gap-2 text-sm text-emerald-500">
                <CheckCircle2 className="h-4 w-4" />
                {matrixMessage}
              </p>
            )}
          </CardContent>
        </Card>
      )}

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="variants">SKU 与变体</TabsTrigger>
          <TabsTrigger value="listings">Listing 就绪</TabsTrigger>
        </TabsList>

        <TabsContent value="variants" className="space-y-4">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Metric label="SKU 总数" value={summary.total} />
            <Metric label="启用中" value={summary.active} />
            <Metric label="低库存" value={summary.lowStock} tone={summary.lowStock > 0 ? 'warning' : 'default'} />
            <Metric
              label="平均毛利率"
              value={summary.averageMargin == null ? '-' : `${summary.averageMargin.toFixed(1)}%`}
            />
          </div>

          <Card>
            <CardHeader className="gap-3 border-b border-border">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <CardTitle className="text-sm">全部变体</CardTitle>
                <div className="flex flex-wrap items-center gap-2">
                  <div className="relative">
                    <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                    <Input
                      value={search}
                      onChange={(event) => setSearch(event.target.value)}
                      placeholder="搜索商品、SKU 或属性"
                      className="h-9 w-60 pl-8"
                    />
                  </div>
                  <div className="flex rounded-md border bg-background p-0.5">
                    {[
                      ['all', '全部'],
                      ['active', '启用'],
                      ['inactive', '停用'],
                      ['low', '低库存'],
                    ].map(([value, label]) => (
                      <Button
                        key={value}
                        variant={stockFilter === value ? 'secondary' : 'ghost'}
                        size="sm"
                        className="h-7 px-2.5 text-xs"
                        onClick={() => setStockFilter(value as typeof stockFilter)}
                      >
                        {label}
                      </Button>
                    ))}
                  </div>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              {selectedIds.length > 0 && (
                <BulkVariantEditor
                  selectedCount={selectedIds.length}
                  fields={bulkFields}
                  setFields={setBulkFields}
                  assets={imageAssets}
                  isSaving={bulkMutation.isPending}
                  onApply={() => bulkMutation.mutate()}
                  onClear={() => {
                    setSelectedIds([])
                    setBulkFields(EMPTY_BULK_FIELDS)
                  }}
                />
              )}

              {filteredVariants.length > 0 ? (
                <>
                  <div className="hidden overflow-x-auto md:block">
                    <table className="w-full min-w-[900px] text-left text-sm">
                      <thead className="border-b text-xs text-muted-foreground">
                        <tr>
                          <th className="w-10 py-2">
                            <input
                              type="checkbox"
                              checked={allVisibleSelected}
                              onChange={toggleAllVisible}
                              aria-label="选择当前所有变体"
                            />
                          </th>
                          <th className="py-2 font-medium">商品 / SKU</th>
                          <th className="py-2 font-medium">属性</th>
                          <th className="py-2 font-medium">售价 / 成本</th>
                          <th className="py-2 font-medium">库存</th>
                          <th className="py-2 font-medium">状态</th>
                          <th className="py-2 font-medium">素材</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border">
                        {filteredVariants.map((variant) => (
                          <tr key={variant.id} className="align-top">
                            <td className="py-3">
                              <input
                                type="checkbox"
                                checked={selectedIds.includes(variant.id)}
                                onChange={() => toggleVariant(variant.id)}
                                aria-label={`选择 ${variant.sku}`}
                              />
                            </td>
                            <td className="max-w-[280px] py-3 pr-3">
                              <p className="truncate text-xs text-muted-foreground">{variant.product_title}</p>
                              <p className="mt-0.5 font-mono text-xs font-medium">{variant.sku}</p>
                              {variant.name && <p className="mt-0.5 truncate text-xs text-muted-foreground">{variant.name}</p>}
                            </td>
                            <td className="py-3 pr-3 text-xs text-muted-foreground">
                              {Object.entries(variant.attributes).map(([key, value]) => `${key}:${value}`).join(' · ') || '-'}
                            </td>
                            <td className="metric-number py-3 pr-3 text-xs">
                              <p>{variant.price == null ? '-' : `¥${variant.price}`}</p>
                              <p className="text-muted-foreground">{variant.cost_price == null ? '-' : `成本 ¥${variant.cost_price}`}</p>
                            </td>
                            <td className={`metric-number py-3 pr-3 text-xs ${variant.stock_quantity < 10 ? 'text-[var(--factory-coral)]' : ''}`}>
                              {variant.stock_quantity}
                            </td>
                            <td className="py-3 pr-3">
                              <Badge variant={variant.is_active ? 'secondary' : 'outline'}>
                                {variant.is_active ? '启用' : '停用'}
                              </Badge>
                            </td>
                            <td className="py-3">
                              {variant.image_url ? (
                                <img src={variant.image_url} alt="" className="h-10 w-10 rounded border object-cover" />
                              ) : (
                                <span className="text-xs text-muted-foreground">未绑定</span>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  <div className="space-y-2 md:hidden">
                    {filteredVariants.map((variant) => (
                      <div key={variant.id} className="rounded-md border p-3">
                        <div className="flex items-start gap-3">
                          <input
                            type="checkbox"
                            checked={selectedIds.includes(variant.id)}
                            onChange={() => toggleVariant(variant.id)}
                            className="mt-1"
                          />
                          {variant.image_url ? (
                            <img src={variant.image_url} alt="" className="h-12 w-12 rounded border object-cover" />
                          ) : (
                            <div className="flex h-12 w-12 items-center justify-center rounded border bg-muted">
                              <PackageSearch className="h-4 w-4 text-muted-foreground" />
                            </div>
                          )}
                          <div className="min-w-0 flex-1">
                            <p className="truncate text-xs text-muted-foreground">{variant.product_title}</p>
                            <p className="font-mono text-xs font-medium">{variant.sku}</p>
                            <p className="mt-1 text-xs text-muted-foreground">
                              {Object.entries(variant.attributes).map(([key, value]) => `${key}:${value}`).join(' · ') || '-'}
                            </p>
                          </div>
                        </div>
                        <div className="mt-3 grid grid-cols-3 gap-2 text-xs">
                          <span>售价 {variant.price == null ? '-' : `¥${variant.price}`}</span>
                          <span>成本 {variant.cost_price == null ? '-' : `¥${variant.cost_price}`}</span>
                          <span className={variant.stock_quantity < 10 ? 'text-[var(--factory-coral)]' : ''}>
                            库存 {variant.stock_quantity}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </>
              ) : (
                <EmptyState message="没有符合条件的 SKU" />
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="listings" className="space-y-4">
          <Card>
            <CardHeader className="gap-3 border-b border-border">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <CardTitle className="text-sm">Listing 列表</CardTitle>
                <div className="flex flex-wrap items-center gap-2">
                  <Input
                    value={listingSearch}
                    onChange={(event) => setListingSearch(event.target.value)}
                    placeholder="搜索商品或 Listing"
                    className="h-9 w-56"
                  />
                  <select
                    value={platformFilter}
                    onChange={(event) => setPlatformFilter(event.target.value)}
                    className="h-9 rounded-md border bg-background px-3 text-sm"
                  >
                    <option value="all">全部平台</option>
                    {Object.entries(PLATFORM_LABELS).map(([value, label]) => (
                      <option key={value} value={value}>{label}</option>
                    ))}
                  </select>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-2">
              {listingsQuery.isLoading ? (
                <div className="flex justify-center py-12">
                  <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                </div>
              ) : listings.length > 0 ? (
                listings.map((listing) => (
                  <ListingRow
                    key={listing.id}
                    listing={listing}
                    onOpen={() => navigate(`/app/products/${listing.product_id}?listing=${listing.id}`)}
                  />
                ))
              ) : (
                <EmptyState message="当前筛选下没有 Listing" />
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </motion.div>
  )
}

function Metric({
  label,
  value,
  tone = 'default',
}: {
  label: string
  value: string | number
  tone?: 'default' | 'warning'
}) {
  return (
    <div className="rounded-md border bg-card px-3 py-2.5">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className={`metric-number mt-1 text-lg font-semibold ${tone === 'warning' ? 'text-[var(--factory-coral)]' : ''}`}>
        {value}
      </p>
    </div>
  )
}

function BulkVariantEditor({
  selectedCount,
  fields,
  setFields,
  assets,
  isSaving,
  onApply,
  onClear,
}: {
  selectedCount: number
  fields: BulkEditableFields
  setFields: (fields: BulkEditableFields) => void
  assets: WorkbenchAsset[]
  isSaving: boolean
  onApply: () => void
  onClear: () => void
}) {
  return (
    <div className="rounded-md border border-primary/30 bg-primary/5 p-3">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-medium">已选择 {selectedCount} 个 SKU</p>
        <Button variant="ghost" size="sm" onClick={onClear}>取消选择</Button>
      </div>
      <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-6">
        <div className="space-y-1.5">
          <Label>售价</Label>
          <Input type="number" min="0" value={fields.price} onChange={(event) => setFields({ ...fields, price: event.target.value })} />
        </div>
        <div className="space-y-1.5">
          <Label>成本</Label>
          <Input type="number" min="0" value={fields.cost_price} onChange={(event) => setFields({ ...fields, cost_price: event.target.value })} />
        </div>
        <div className="space-y-1.5">
          <Label>库存</Label>
          <Input type="number" min="0" step="1" value={fields.stock_quantity} onChange={(event) => setFields({ ...fields, stock_quantity: event.target.value })} />
        </div>
        <div className="space-y-1.5">
          <Label>状态</Label>
          <select
            value={fields.is_active}
            onChange={(event) => setFields({ ...fields, is_active: event.target.value as BulkEditableFields['is_active'] })}
            className="h-10 w-full rounded-md border bg-background px-3 text-sm"
          >
            <option value="">不修改</option>
            <option value="true">启用</option>
            <option value="false">停用</option>
          </select>
        </div>
        <div className="space-y-1.5 md:col-span-2">
          <Label>绑定素材</Label>
          <select
            value={fields.image_url}
            onChange={(event) => setFields({ ...fields, image_url: event.target.value })}
            className="h-10 w-full rounded-md border bg-background px-3 text-sm"
          >
            <option value="">不修改</option>
            {assets.map((asset) => (
              <option key={asset.id} value={asset.image_url}>
                {asset.name} · {asset.platform || (asset.kind === 'processed' ? '处理后' : '原图')}
              </option>
            ))}
          </select>
        </div>
      </div>
      <Button className="mt-3" size="sm" onClick={onApply} disabled={isSaving}>
        {isSaving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
        {isSaving ? '保存中...' : '应用到选中 SKU'}
      </Button>
    </div>
  )
}

function ListingRow({ listing, onOpen }: { listing: CatalogListing; onOpen: () => void }) {
  const problem = listing.readiness.checks.find((check) => check.status === 'error')
  const warning = listing.readiness.checks.find((check) => check.status === 'warning')
  return (
    <button
      type="button"
      onClick={onOpen}
      className="flex w-full items-center gap-3 rounded-md border px-3 py-3 text-left transition-colors hover:bg-accent/40"
    >
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded border bg-background">
        <Table2 className="h-4 w-4 text-primary" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="secondary">{PLATFORM_LABELS[listing.platform] || listing.platform}</Badge>
          <Badge variant={listing.compliance_status === 'pass' ? 'secondary' : 'destructive'}>
            {listing.compliance_status === 'pass' ? '合规通过' : '合规阻断'}
          </Badge>
          <span className="text-xs text-muted-foreground">v{listing.version}</span>
        </div>
        <p className="mt-1 truncate text-sm font-medium">{listing.title}</p>
        <p className="truncate text-xs text-muted-foreground">{listing.product_title}</p>
        <div className="mt-1 flex flex-wrap gap-2 text-[11px]">
          {problem && <span className="text-destructive">{problem.message}</span>}
          {!problem && warning && <span className="text-amber-500">{warning.message}</span>}
          {!problem && !warning && (
            <span className="flex items-center gap-1 text-emerald-500">
              <CheckCircle2 className="h-3 w-3" />平台字段就绪
            </span>
          )}
        </div>
      </div>
      <div className="hidden shrink-0 text-right sm:block">
        <p className={`metric-number text-sm font-semibold ${listing.readiness.ok ? 'text-emerald-500' : 'text-destructive'}`}>
          {listing.readiness.score}
        </p>
        <p className="text-[10px] text-muted-foreground">就绪分</p>
      </div>
      <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
    </button>
  )
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-center text-muted-foreground">
      <CircleDot className="mb-2 h-8 w-8 opacity-40" />
      <p className="text-sm">{message}</p>
    </div>
  )
}
