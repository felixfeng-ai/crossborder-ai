import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, Loader2, Save } from 'lucide-react'

import apiClient from '@/api/client'
import {
  AdminError,
  AdminLoading,
  AdminPageHeader,
  AdminPanel,
  AdminStatusPill,
} from './AdminPrimitives'

type ProviderField = {
  key: string
  label: string
  secret: boolean
  placeholder?: string
}

type ProviderDefinition = {
  id: string
  label: string
  description: string
  fields: ProviderField[]
}

type ProviderGroup = {
  id: string
  label: string
  description: string
  providers: ProviderDefinition[]
}

type ProviderStatus = {
  configured: boolean
  fields: Record<string, string>
}

type ProviderResponse = Record<string, ProviderStatus>

const PROVIDER_GROUPS: ProviderGroup[] = [
  {
    id: 'ai',
    label: 'AI 模型',
    description: '文本、图片、视频与向量模型，保存后由运行中的服务进程刷新缓存。',
    providers: [
      {
        id: 'deepseek',
        label: 'DeepSeek',
        description: 'Agent、Listing 与经营分析的主文本模型。',
        fields: [
          { key: 'api_key', label: 'API Key', secret: true },
          { key: 'model', label: '模型名称', secret: false },
        ],
      },
      {
        id: 'aliyun',
        label: '阿里云通义万相',
        description: '商品图、IP 视觉检查与政策知识库向量模型。',
        fields: [
          { key: 'api_key', label: 'DashScope API Key', secret: true },
          { key: 'model', label: '图片模型', secret: false },
          { key: 'vision_model', label: 'IP 图片检查模型', secret: false },
          { key: 'embedding_model', label: '政策 RAG Embedding 模型', secret: false },
        ],
      },
      {
        id: 'replicate',
        label: 'Replicate',
        description: '自由创作与商品参考图生成通道。',
        fields: [
          { key: 'api_key', label: 'API Key', secret: true },
          { key: 'model', label: '文生图模型', secret: false },
          { key: 'reference_model', label: '商品参考图模型', secret: false },
          {
            key: 'reference_input_field',
            label: '参考图输入字段',
            secret: false,
          },
          { key: 'inpaint_model', label: '局部重绘模型', secret: false },
          { key: 'outpaint_model', label: '扩图模型', secret: false },
          { key: 'remove_model', label: '消除模型', secret: false },
        ],
      },
      {
        id: 'minimax',
        label: 'MiniMax',
        description: '视频生成、轮询对账与配音能力。',
        fields: [
          { key: 'api_key', label: 'API Key', secret: true },
          { key: 'group_id', label: 'Group ID', secret: true },
          { key: 'base_url', label: '视频 Base URL', secret: false },
          { key: 'tts_base_url', label: '配音 Base URL', secret: false },
          { key: 'model', label: '默认视频模型', secret: false },
          { key: 'tts_model', label: '配音模型', secret: false },
          { key: 'voice_id', label: '默认音色 ID', secret: false },
          { key: 'resolution', label: '默认清晰度', secret: false },
        ],
      },
      {
        id: 'jimeng',
        label: '即梦 / Seedance',
        description: '火山方舟视频生成 Provider。',
        fields: [
          { key: 'api_key', label: '方舟 API Key', secret: true },
          { key: 'base_url', label: 'Base URL', secret: false },
          { key: 'model', label: '默认模型', secret: false },
          { key: 'resolution', label: '默认清晰度', secret: false },
        ],
      },
    ],
  },
  {
    id: 'data',
    label: '商品数据',
    description: '商品详情、供应链与竞品数据来源，优先使用 Just One API。',
    providers: [
      {
        id: 'justone',
        label: 'Just One API',
        description: '1688 商品详情抓取的首选 Provider。',
        fields: [{ key: 'token', label: '访问 Token', secret: true }],
      },
      {
        id: 'onebound',
        label: 'Onebound',
        description: '兼容旧采集链路的数据 Provider。',
        fields: [
          { key: 'api_key', label: 'API Key', secret: true },
          { key: 'api_secret', label: 'API Secret', secret: true },
        ],
      },
    ],
  },
  {
    id: 'commerce',
    label: '电商应用',
    description: '平台级 OAuth 应用凭据；卖家店铺授权仍在卖家设置的平台连接中完成。',
    providers: [
      {
        id: 'shopify',
        label: 'Shopify App',
        description: '平台 Shopify 应用的客户端凭据与回调地址。',
        fields: [
          { key: 'api_key', label: 'API Key', secret: true },
          { key: 'api_secret', label: 'API Secret', secret: true },
          { key: 'redirect_uri', label: 'OAuth 回调地址', secret: false },
        ],
      },
      {
        id: 'amazon',
        label: 'Amazon SP-API App',
        description: '平台 Amazon SP-API 应用凭据与 OAuth 回调地址。',
        fields: [
          { key: 'app_id', label: 'Application ID', secret: false },
          { key: 'client_id', label: 'LWA Client ID', secret: false },
          { key: 'client_secret', label: 'LWA Client Secret', secret: true },
          { key: 'redirect_uri', label: 'OAuth 回调地址', secret: false },
        ],
      },
    ],
  },
]

function providerFieldKey(providerId: string, fieldKey: string): string {
  return `${providerId}:${fieldKey}`
}

export default function AdminProvidersPage() {
  const queryClient = useQueryClient()
  const [values, setValues] = useState<Record<string, string>>({})
  const [savedProvider, setSavedProvider] = useState('')

  const query = useQuery<ProviderResponse>({
    queryKey: ['admin-provider-settings'],
    queryFn: async () => {
      const response = await apiClient.get('/settings/providers')
      return response.data.providers
    },
  })

  useEffect(() => {
    if (!query.data) return
    const next: Record<string, string> = {}
    for (const group of PROVIDER_GROUPS) {
      for (const provider of group.providers) {
        for (const field of provider.fields) {
          if (!field.secret) {
            next[providerFieldKey(provider.id, field.key)] =
              query.data[provider.id]?.fields?.[field.key] || ''
          }
        }
      }
    }
    setValues(next)
  }, [query.data])

  const saveMutation = useMutation({
    mutationFn: async ({
      provider,
      payload,
    }: {
      provider: string
      payload: Record<string, string>
    }) => {
      const response = await apiClient.put(`/settings/providers/${provider}`, payload)
      return response.data
    },
    onSuccess: (_, variables) => {
      setSavedProvider(variables.provider)
      void queryClient.invalidateQueries({ queryKey: ['admin-provider-settings'] })
      void queryClient.invalidateQueries({ queryKey: ['admin-audits'] })
    },
  })

  if (query.isLoading) return <AdminLoading label="正在读取服务商配置" />
  if (query.isError || !query.data) {
    return <AdminError onRetry={() => void query.refetch()} />
  }

  const saveProvider = (provider: ProviderDefinition) => {
    const payload: Record<string, string> = {}
    for (const field of provider.fields) {
      const value = values[providerFieldKey(provider.id, field.key)]?.trim() || ''
      if (field.secret && !value) continue
      payload[field.key] = value
    }
    saveMutation.mutate({ provider: provider.id, payload })
  }

  return (
    <div className="space-y-6">
      <AdminPageHeader
        title="服务商配置"
        description="平台级模型、数据与电商应用凭据；密钥只显示掩码，留空表示不修改"
      />

      <div className="border border-[color:color-mix(in_srgb,var(--factory-accent)_30%,var(--factory-line))] bg-[color:color-mix(in_srgb,var(--factory-accent)_6%,var(--factory-panel))] px-4 py-3">
        <p className="text-sm font-medium text-foreground">平台基础设施，不属于卖家偏好</p>
        <p className="mt-1 text-xs leading-5 text-muted-foreground">
          配置修改会影响全平台调用。卖家侧只保留品牌调性、个人自动化开关和店铺授权。
        </p>
      </div>

      {PROVIDER_GROUPS.map((group) => (
        <AdminPanel
          key={group.id}
          title={group.label}
          description={group.description}
        >
          <div className="divide-y divide-border">
            {group.providers.map((provider) => {
              const status = query.data[provider.id]
              const isSaving =
                saveMutation.isPending && saveMutation.variables?.provider === provider.id
              return (
                <section key={provider.id} className="grid gap-5 px-4 py-5 xl:grid-cols-[260px_minmax(0,1fr)]">
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="text-sm font-semibold text-foreground">{provider.label}</h3>
                      <AdminStatusPill tone={status?.configured ? 'good' : 'neutral'}>
                        {status?.configured ? '已配置' : '未配置'}
                      </AdminStatusPill>
                    </div>
                    <p className="mt-2 text-xs leading-5 text-muted-foreground">
                      {provider.description}
                    </p>
                  </div>

                  <div className="grid gap-3 md:grid-cols-2">
                    {provider.fields.map((field) => {
                      const key = providerFieldKey(provider.id, field.key)
                      const masked = status?.fields?.[field.key] || ''
                      return (
                        <label
                          key={field.key}
                          className={field.key.endsWith('_url') || field.key === 'redirect_uri' ? 'space-y-1.5 md:col-span-2' : 'space-y-1.5'}
                        >
                          <span className="text-xs text-muted-foreground">{field.label}</span>
                          <input
                            type={field.secret ? 'password' : 'text'}
                            value={values[key] || ''}
                            onChange={(event) => {
                              setSavedProvider('')
                              setValues((current) => ({
                                ...current,
                                [key]: event.target.value,
                              }))
                            }}
                            placeholder={
                              field.secret && masked
                                ? `已配置 ${masked}，留空不修改`
                                : field.placeholder || ''
                            }
                            autoComplete="off"
                            className="h-10 w-full rounded-md border border-border bg-[var(--factory-ground)] px-3 text-sm text-foreground outline-none placeholder:text-muted-foreground focus:ring-2 focus:ring-ring"
                          />
                        </label>
                      )
                    })}
                    <div className="flex items-center gap-3 md:col-span-2">
                      <button
                        type="button"
                        onClick={() => saveProvider(provider)}
                        disabled={isSaving}
                        className="inline-flex h-9 items-center justify-center rounded-md border border-transparent bg-primary px-4 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:pointer-events-none disabled:opacity-50"
                      >
                        {isSaving ? (
                          <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <Save className="mr-1.5 h-3.5 w-3.5" />
                        )}
                        保存配置
                      </button>
                      {savedProvider === provider.id && !saveMutation.isError && (
                        <span className="inline-flex items-center gap-1 text-xs text-[var(--factory-success)]">
                          <CheckCircle2 className="h-3.5 w-3.5" />
                          已保存并刷新运行时缓存
                        </span>
                      )}
                    </div>
                  </div>
                </section>
              )
            })}
          </div>
        </AdminPanel>
      ))}

      {saveMutation.isError && (
        <p role="alert" className="text-sm text-[var(--factory-coral)]">
          配置保存失败。留空密钥不会覆盖旧值，请检查字段后重试。
        </p>
      )}
    </div>
  )
}
