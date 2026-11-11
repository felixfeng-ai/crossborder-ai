import { useState, useEffect } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { Settings, CheckCircle2, Palette, X, KeyRound, Server, Link2, RefreshCw } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import apiClient from '@/api/client'

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState(() => {
    // Amazon OAuth 回调会带 amazon_connected=1，默认打开平台连接页。
    return new URLSearchParams(window.location.search).has('amazon_connected')
      ? 'connections'
      : 'persona'
  })
  const { data: me } = useQuery({
    queryKey: ['current-user'],
    queryFn: async () => {
      const response = await apiClient.get('/auth/me')
      return response.data
    },
  })

  return (
    <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
          <Settings className="h-6 w-6 text-primary" />
          系统设置
        </h1>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="persona">品牌调性</TabsTrigger>
          <TabsTrigger value="connections">平台连接</TabsTrigger>
          {me?.is_admin && <TabsTrigger value="providers">服务商配置</TabsTrigger>}
        </TabsList>

        <TabsContent value="persona" className="space-y-4">
          <PersonaForm />
        </TabsContent>
        <TabsContent value="connections" className="space-y-4">
          <PlatformConnections />
        </TabsContent>
        {me?.is_admin && (
          <TabsContent value="providers" className="space-y-4">
            <ProviderSettings />
          </TabsContent>
        )}
      </Tabs>
    </motion.div>
  )
}

const PROVIDERS = [
  {
    id: 'deepseek',
    label: 'DeepSeek',
    fields: [
      { key: 'api_key', label: 'API Key', secret: true },
      { key: 'model', label: '模型名称', secret: false },
    ],
  },
  {
    id: 'onebound',
    label: 'Onebound',
    fields: [
      { key: 'api_key', label: 'API Key', secret: true },
      { key: 'api_secret', label: 'API Secret', secret: true },
    ],
  },
  {
    id: 'justone',
    label: 'Just One API',
    fields: [
      { key: 'token', label: '访问 Token', secret: true },
    ],
  },
  {
    id: 'aliyun',
    label: '通义万相',
    fields: [
      { key: 'api_key', label: 'DashScope API Key', secret: true },
      { key: 'model', label: '模型名称', secret: false },
    ],
  },
  {
    id: 'replicate',
    label: 'Replicate',
    fields: [
      { key: 'api_key', label: 'API Key', secret: true },
      { key: 'model', label: '模型名称', secret: false },
    ],
  },
  {
    id: 'minimax',
    label: 'MiniMax 视频与配音',
    fields: [
      { key: 'api_key', label: 'API Key', secret: true },
      { key: 'group_id', label: 'GroupId（配音必填）', secret: true },
      { key: 'base_url', label: 'Base URL', secret: false },
      { key: 'tts_base_url', label: 'TTS Base URL', secret: false },
      { key: 'model', label: '默认模型', secret: false },
      { key: 'tts_model', label: '配音模型', secret: false },
      { key: 'voice_id', label: '默认音色 ID', secret: false },
      { key: 'resolution', label: '默认清晰度', secret: false },
    ],
  },
  {
    id: 'shopify',
    label: 'Shopify 应用',
    fields: [
      { key: 'api_key', label: 'API Key', secret: true },
      { key: 'api_secret', label: 'API Secret', secret: true },
      { key: 'redirect_uri', label: 'OAuth 回调地址', secret: false },
    ],
  },
  {
    id: 'amazon',
    label: 'Amazon SP-API 应用',
    fields: [
      { key: 'app_id', label: 'Application ID', secret: false },
      { key: 'client_id', label: 'LWA Client ID', secret: false },
      { key: 'client_secret', label: 'LWA Client Secret', secret: true },
      { key: 'redirect_uri', label: 'OAuth 回调地址', secret: false },
    ],
  },
] as const

function ProviderSettings() {
  const queryClient = useQueryClient()
  const [values, setValues] = useState<Record<string, string>>({})

  const { data, isLoading } = useQuery({
    queryKey: ['provider-settings'],
    queryFn: async () => {
      const response = await apiClient.get('/settings/providers')
      return response.data.providers
    },
  })

  useEffect(() => {
    if (!data) return
    const next: Record<string, string> = {}
    for (const provider of PROVIDERS) {
      for (const field of provider.fields) {
        if (!field.secret) {
          next[`${provider.id}:${field.key}`] = data[provider.id]?.fields?.[field.key] || ''
        }
      }
    }
    setValues(next)
  }, [data])

  const saveMutation = useMutation({
    mutationFn: async ({ provider, payload }: { provider: string; payload: Record<string, string> }) => {
      const response = await apiClient.put(`/settings/providers/${provider}`, payload)
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['provider-settings'] })
    },
  })

  const updateValue = (key: string, value: string) => {
    setValues((current) => ({ ...current, [key]: value }))
  }

  const saveProvider = (providerId: string) => {
    const provider = PROVIDERS.find((item) => item.id === providerId)
    if (!provider) return
    const payload: Record<string, string> = {}
    for (const field of provider.fields) {
      const value = values[`${provider.id}:${field.key}`]?.trim() || ''
      if (field.secret && !value) continue
      payload[field.key] = value
    }
    saveMutation.mutate({ provider: providerId, payload })
  }

  if (isLoading) {
    return <Card><CardContent className="py-10 text-center text-sm text-muted-foreground">加载配置中...</CardContent></Card>
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Server className="h-4 w-4" />服务商运行时配置
          </CardTitle>
          <CardDescription>
            配置加密保存，保存后当前进程立即生效，其他 Worker 周期性同步。
          </CardDescription>
        </CardHeader>
      </Card>

      {PROVIDERS.map((provider) => {
        const status = data?.[provider.id]
        return (
          <Card key={provider.id}>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="text-base flex items-center gap-2">
                <KeyRound className="h-4 w-4" />{provider.label}
              </CardTitle>
              <Badge variant={status?.configured ? 'secondary' : 'outline'}>
                {status?.configured ? '已配置' : '未配置'}
              </Badge>
            </CardHeader>
            <CardContent className="space-y-3">
              {provider.fields.map((field) => {
                const fieldKey = `${provider.id}:${field.key}`
                const masked = status?.fields?.[field.key] || ''
                return (
                  <div key={field.key} className="space-y-1.5">
                    <Label>{field.label}</Label>
                    <Input
                      type={field.secret ? 'password' : 'text'}
                      value={values[fieldKey] || ''}
                      onChange={(event) => updateValue(fieldKey, event.target.value)}
                      placeholder={field.secret && masked ? `已配置 ${masked}，留空不修改` : ''}
                    />
                  </div>
                )
              })}
              <Button
                size="sm"
                onClick={() => saveProvider(provider.id)}
                disabled={saveMutation.isPending}
              >
                {saveMutation.isPending ? '保存中...' : '保存配置'}
              </Button>
            </CardContent>
          </Card>
        )
      })}
      {saveMutation.isSuccess && (
        <p className="text-sm text-emerald-600 flex items-center gap-1">
          <CheckCircle2 className="h-4 w-4" />配置已保存并刷新运行时缓存
        </p>
      )}
      {saveMutation.isError && (
        <p className="text-sm text-destructive">保存失败，请检查配置项后重试</p>
      )}
    </div>
  )
}

function PlatformConnections() {
  const queryClient = useQueryClient()
  const amazonConnected = new URLSearchParams(window.location.search).get('amazon_connected') === '1'
  const { data, isLoading } = useQuery({
    queryKey: ['platform-connections'],
    queryFn: async () => {
      const response = await apiClient.get('/platforms/connections')
      return response.data.connections as Array<{
        id: string
        platform: string
        account_name: string
        external_account_id: string
        marketplace_id: string | null
        status: string
      }>
    },
  })

  const connectMutation = useMutation({
    mutationFn: async () => {
      const response = await apiClient.post('/platforms/amazon/connect-url')
      return response.data as { auth_url: string }
    },
    onSuccess: (response) => {
      window.location.href = response.auth_url
    },
  })

  const testMutation = useMutation({
    mutationFn: async () => {
      const response = await apiClient.post('/platforms/amazon/test')
      return response.data
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['platform-connections'] }),
  })

  const amazon = data?.find((item) => item.platform === 'amazon')

  if (isLoading) {
    return <Card><CardContent className="py-8 text-sm text-muted-foreground">加载平台连接中...</CardContent></Card>
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base flex items-center gap-2">
          <Link2 className="h-4 w-4" />Amazon 店铺
        </CardTitle>
        <CardDescription>
          通过 Amazon SP-API 授权后，可逐步启用 Listing、库存和订单能力。
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {amazonConnected && (
          <p className="text-sm text-emerald-600 flex items-center gap-1">
            <CheckCircle2 className="h-4 w-4" />Amazon 店铺授权成功
          </p>
        )}
        {amazon ? (
          <div className="rounded-lg border p-4 space-y-2">
            <div className="flex items-center justify-between">
              <p className="font-medium text-sm">{amazon.account_name}</p>
              <Badge variant={amazon.status === 'active' ? 'secondary' : 'destructive'}>
                {amazon.status === 'active' ? '已连接' : '授权异常'}
              </Badge>
            </div>
            <p className="text-xs text-muted-foreground">
              Seller ID：{amazon.external_account_id} · Marketplace：{amazon.marketplace_id || '-'}
            </p>
            <div className="flex gap-2">
              <Button
                size="sm"
                variant="outline"
                onClick={() => testMutation.mutate()}
                disabled={testMutation.isPending}
              >
                <RefreshCw className={`h-4 w-4 mr-1 ${testMutation.isPending ? 'animate-spin' : ''}`} />
                测试连接
              </Button>
              <Button size="sm" onClick={() => connectMutation.mutate()}>
                重新授权
              </Button>
            </div>
          </div>
        ) : (
          <div className="flex items-center justify-between rounded-lg border p-4">
            <div>
              <p className="text-sm font-medium">尚未连接 Amazon</p>
              <p className="text-xs text-muted-foreground mt-1">需要管理员先配置 Amazon SP-API 应用参数</p>
            </div>
            <Button
              size="sm"
              onClick={() => connectMutation.mutate()}
              disabled={connectMutation.isPending}
            >
              连接 Amazon
            </Button>
          </div>
        )}
        {connectMutation.isError && (
          <p className="text-sm text-destructive">发起 Amazon 授权失败，请检查应用配置。</p>
        )}
        {testMutation.isSuccess && (
          <p className="text-sm text-emerald-600">Amazon 授权验证成功</p>
        )}
        {testMutation.isError && (
          <p className="text-sm text-destructive">Amazon 授权验证失败，请重新授权。</p>
        )}
      </CardContent>
    </Card>
  )
}

function PersonaForm() {
  const queryClient = useQueryClient()
  const [brandName, setBrandName] = useState('')
  const [tagline, setTagline] = useState('')
  const [description, setDescription] = useState('')
  const [tone, setTone] = useState('professional')
  const [toneCustom, setToneCustom] = useState('')
  const [bannedWords, setBannedWords] = useState<string[]>([])
  const [newWord, setNewWord] = useState('')

  const { data } = useQuery({
    queryKey: ['persona'],
    queryFn: async () => { const r = await apiClient.get('/settings/persona'); return r.data },
  })

  useEffect(() => {
    if (data) {
      setBrandName(data.brand_name || '')
      setTagline(data.tagline || '')
      setDescription(data.description || '')
      setTone(data.tone || 'professional')
      setToneCustom(data.tone_custom || '')
      setBannedWords(data.banned_words || [])
    }
  }, [data])

  const saveMutation = useMutation({
    mutationFn: async (body: any) => { const r = await apiClient.put('/settings/persona', body); return r.data },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['persona'] }),
  })

  const addWord = () => {
    const w = newWord.trim()
    if (w && !bannedWords.includes(w)) { setBannedWords([...bannedWords, w]); setNewWord('') }
  }

  const handleSave = () => {
    saveMutation.mutate({
      brand_name: brandName, tagline, description, tone,
      tone_custom: tone === 'custom' ? toneCustom : '',
      banned_words: bannedWords,
    })
  }

  return (
    <Card>
      <CardHeader><CardTitle className="text-base flex items-center gap-2"><Palette className="h-4 w-4" />品牌调性</CardTitle>
      <CardDescription>配置后，AI 生成的内容会自动按品牌风格输出</CardDescription></CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-2"><Label>品牌名</Label><Input value={brandName} onChange={e => setBrandName(e.target.value)} placeholder="如：ABC Store" /></div>
          <div className="space-y-2"><Label>标语</Label><Input value={tagline} onChange={e => setTagline(e.target.value)} placeholder="如：Quality You Can Trust" /></div>
        </div>
        <div className="space-y-2"><Label>品牌描述</Label>
          <textarea value={description} onChange={e => setDescription(e.target.value)} placeholder="简单描述你的品牌定位、目标客户..."
            className="flex min-h-[80px] w-full rounded-md border bg-background px-3 py-2 text-sm" />
        </div>
        <div className="space-y-2">
          <Label>默认语气</Label>
          <div className="flex flex-wrap gap-2">
            {['professional','casual','luxury','friendly','persuasive','humorous','custom'].map(t => (
              <Badge key={t} variant={tone === t ? 'default' : 'outline'} className="cursor-pointer" onClick={() => setTone(t)}>{t}</Badge>
            ))}
          </div>
          {tone === 'custom' && <Input value={toneCustom} onChange={e => setToneCustom(e.target.value)} placeholder="自定义语气描述" className="mt-2" />}
        </div>
        <div className="space-y-2">
          <Label>违禁词（AI 生成时会自动避免使用）</Label>
          <div className="flex gap-2">
            <Input value={newWord} onChange={e => setNewWord(e.target.value)} onKeyDown={e => e.key === 'Enter' && addWord()} placeholder="输入违禁词，回车添加" />
            <Button variant="outline" onClick={addWord}>添加</Button>
          </div>
          {bannedWords.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-2">
              {bannedWords.map((w, i) => (
                <Badge key={i} variant="secondary" className="gap-1">
                  {w}
                  <X className="h-3 w-3 cursor-pointer" onClick={() => setBannedWords(bannedWords.filter((_, j) => j !== i))} />
                </Badge>
              ))}
            </div>
          )}
        </div>
        <Button onClick={handleSave} disabled={saveMutation.isPending}>
          {saveMutation.isPending ? '保存中...' : '保存品牌配置'}
        </Button>
        {saveMutation.isSuccess && <p className="text-sm text-emerald-600 flex items-center gap-1"><CheckCircle2 className="h-4 w-4" />已保存</p>}
      </CardContent>
    </Card>
  )
}

