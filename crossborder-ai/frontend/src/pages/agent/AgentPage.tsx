import { useState, useRef, useEffect } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import { Link, useSearchParams } from 'react-router-dom'
import {
  Bot,
  Send,
  UserRound,
  Loader2,
  Sparkles,
  ShoppingCart,
  CheckCircle2,
  AlertCircle,
  ExternalLink,
  ChevronDown,
  FileText,
  Image as ImageIcon,
  Clapperboard,
  FolderOpen,
  Megaphone,
  type LucideIcon,
} from 'lucide-react'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import Markdown from '@/components/common/Markdown'
import ProductReportCard from '@/components/agent/ProductReportCard'
import type { AgentStep } from '@/types'
import apiClient, { API_BASE } from '@/api/client'
import { MarketingCampaignBar } from '@/components/agent/MarketingCampaignBar'
import { readSseUntil, TaskTimeoutError } from '@/api/sse'
import { toErrorMessage } from '@/utils/errorMessage'
import { getActionLabel } from '@/lib/agent/actionLabels'
import {
  agentWorkspaceCopy,
  type AgentActionIcon,
  type AgentWorkspaceMode,
} from '@/lib/agent/workspace'
import { useAuthStore } from '@/stores/authStore'

/**
 * AgentPage - AI 智能助手聊天页
 *
 * 像 ChatGPT 一样对话，但背后执行的是真实的业务操作。
 * 跨境卖家直接说需求，Agent 自动完成。
 */

// ── 消息类型 ──────────────────────────────────────────────────
interface Message {
  role: 'user' | 'assistant'
  content: string
  steps?: AgentStep[]
  actionResults?: AgentStep[]
  timestamp: Date
}

const ACTION_ICONS: Record<AgentActionIcon, LucideIcon> = {
  'shopping-cart': ShoppingCart,
  'file-text': FileText,
  image: ImageIcon,
  sparkles: Sparkles,
  clapperboard: Clapperboard,
  folder: FolderOpen,
  megaphone: Megaphone,
}

// ── 任务进度：SSE 实时推流（替代 2s 轮询），连接失败自动回退轮询 ──
const TASK_POLL_INTERVAL_MS = 2000 // 轮询兜底：每 2 秒查一次任务状态
const TASK_TIMEOUT_MS = 3 * 60 * 1000 // 3 分钟总超时（SSE 与轮询共用）

// 生成幂等键：防网络重试 / 用户重复点击导致双扣积分、双建对话
function genIdempotencyKey(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`
}

// 轮询兜底：SSE 连接失败 / 流中断时回退（与原逻辑一致）
async function pollTaskStatus(taskId: string): Promise<any> {
  const deadline = Date.now() + TASK_TIMEOUT_MS
  for (;;) {
    const r = await apiClient.get(`/agent/tasks/${taskId}`)
    const t = r.data
    if (t.status === 'succeeded' || t.status === 'partial') return t
    if (t.status === 'failed') throw new Error(t.error || '任务执行失败，请重试')
    if (Date.now() >= deadline) throw new Error('任务执行超时，请稍后到对话历史查看结果')
    await new Promise((resolve) => setTimeout(resolve, TASK_POLL_INTERVAL_MS))
  }
}

// 主路径：SSE 订阅任务流。event:step 实时回调累积步骤；event:done 收最终结果。
// 失败（done.status=failed）抛错走 onError；超时抛超时；连接失败回退轮询。
async function streamTaskStatus(
  taskId: string,
  onProgress: (steps: AgentStep[]) => void,
): Promise<any> {
  const url = `${API_BASE}/agent/tasks/${taskId}/stream`
  try {
    const payload = await readSseUntil(url, {
      timeoutMs: TASK_TIMEOUT_MS,
      onEvent: (ev) => {
        if (ev.event === 'step') {
          onProgress(((ev.data as { steps?: AgentStep[] })?.steps) || [])
          return false
        }
        return ev.event === 'done' // 收到 done 停止流，返回最终 payload
      },
    })
    const t = payload as { status?: string; error?: string }
    if (t.status === 'failed') {
      throw new Error(t.error || '任务执行失败，请重试')
    }
    return payload
  } catch (err) {
    if (err instanceof TaskTimeoutError) {
      throw new Error('任务执行超时，请稍后到对话历史查看结果')
    }
    // SSE 连接失败（网络/鉴权/流中断）→ 回退轮询兜底
    return pollTaskStatus(taskId)
  }
}

export default function AgentPage({
  mode = 'general',
}: {
  mode?: AgentWorkspaceMode
}) {
  const workspace = agentWorkspaceCopy(mode)
  const user = useAuthStore((state) => state.user)
  const [searchParams] = useSearchParams()
  const promptFromQuery = searchParams.get('prompt') || ''
  const [messages, setMessages] = useState<Message[]>([
    {
      role: 'assistant',
      content: workspace.intro,
      timestamp: new Date(),
    },
  ])
  const [input, setInput] = useState(promptFromQuery)
  const [conversationId, setConversationId] = useState<string>('')
  const [campaignId, setCampaignId] = useState('')
  const [liveSteps, setLiveSteps] = useState<AgentStep[]>([]) // SSE 实时推进度
  const chatEndRef = useRef<HTMLDivElement>(null)

  // 加载最近的对话
  const { data: convList } = useQuery({
    queryKey: ['agent-conversations', mode, campaignId],
    queryFn: async () => {
      const r = await apiClient.get('/agent/conversations', {
        params: {
          workspace: mode,
          campaign_id: campaignId,
        },
      })
      return r.data.items || []
    },
  })

  // 如果有对话，加载第一条
  useEffect(() => {
    if (convList && convList.length > 0 && !conversationId) {
      setConversationId(convList[0].id)
    }
  }, [convList])

  // 加载对话历史消息
  const { data: convData } = useQuery({
    queryKey: ['agent-conversation', mode, campaignId, conversationId],
    queryFn: async () => {
      if (!conversationId) return null
      const r = await apiClient.get(`/agent/conversations/${conversationId}`)
      return r.data
    },
    enabled: !!conversationId,
  })

  // 对话历史加载后更新消息列表
  useEffect(() => {
    if (convData?.messages && convData.messages.length > 0) {
      setMessages(convData.messages.map((m: any) => ({
        role: m.role,
        content: m.content,
        actionResults: m.steps,
        timestamp: new Date(m.created_at),
      })))
    }
  }, [convData])

  // 自动滚动到底部
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  useEffect(() => {
    if (promptFromQuery) setInput(promptFromQuery)
  }, [promptFromQuery])

  useEffect(() => {
    setConversationId('')
    setMessages([
      {
        role: 'assistant',
        content: workspace.intro,
        timestamp: new Date(),
      },
    ])
  }, [campaignId, mode, workspace.intro])

  // Agent 执行：POST 提交异步任务（带幂等键防重复扣积分）→ SSE 实时推进度，
  // 连接失败自动回退轮询到 succeeded/failed
  const agentMutation = useMutation({
    mutationFn: async (instruction: string) => {
      const res = await apiClient.post(
        '/agent/run',
        {
          instruction,
          conversation_id: conversationId,
          workspace: mode,
          campaign_id: campaignId,
        },
        { headers: { 'Idempotency-Key': genIdempotencyKey() } },
      )
      return streamTaskStatus(res.data.task_id, setLiveSteps)
    },
    onSuccess: (data) => {
      setLiveSteps([]) // 任务结束，实时步骤已落入消息 actionResults
      if (data.conversation_id) setConversationId(data.conversation_id)
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: data.summary || '已完成',
          actionResults: data.steps,
          timestamp: new Date(),
        },
      ])
    },
    onError: (err: any) => {
      setLiveSteps([])
      // 轮询抛出的普通 Error 没有 response；后端 HTTP 错误走 detail，都要兜底
      const detail = toErrorMessage(err, '执行失败，请重试')
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: `❌ ${detail}`,
          timestamp: new Date(),
        },
      ])
    },
  })

  const handleSend = () => {
    if (!input.trim() || agentMutation.isPending) return
    const msg = input.trim()

    // 添加用户消息
    setMessages((prev) => [...prev, { role: 'user', content: msg, timestamp: new Date() }])
    setLiveSteps([]) // 新一轮任务，清空上一轮实时步骤
    setInput('')

    // 执行 Agent
    agentMutation.mutate(msg)
  }

  // 快捷指令点击
  const handleQuickAction = (prompt: string) => {
    setInput(prompt)
  }

  // 渲染消息
  const renderMessage = (msg: Message, i: number) => {
    const isUser = msg.role === 'user'
    // 报告卡片步骤：所有带结构化数据的步骤都渲染为数据卡（品类分析 + 选品可并存）；
    // 历史消息的完整报告折叠为"文字版"
    const reportSteps = (msg.actionResults || []).filter((s) => s.data?.structured != null)
    const plainSteps = (msg.actionResults || []).filter((s) => s.data?.structured == null)
    const hasReportCard = reportSteps.length > 0
    const collapseText = hasReportCard && msg.content.length > 400
    return (
      <motion.div
        key={i}
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className={`flex gap-3 ${isUser ? 'flex-row-reverse' : ''}`}
      >
        {/* 用品牌标识和用户首字母替代通用机器人/用户图标。 */}
        {isUser ? <UserAvatar user={user} /> : <AgentAvatar label={workspace.label} />}

        {/* 消息内容 */}
        <div className={`max-w-[80%] space-y-2 ${isUser ? 'items-end' : ''}`}>
          {collapseText ? (
            // 长报告折叠：独立浅色容器承载文字版，避免灰色气泡上灰上加灰看不清
            <details className="group rounded-xl bg-background border border-primary/10 px-4 py-3">
              <summary className="cursor-pointer select-none text-xs text-primary flex items-center gap-1">
                <ChevronDown className="h-3 w-3 transition-transform group-open:rotate-180" />
                查看文字版报告
              </summary>
              <div className="mt-3 pt-3 border-t border-border/60">
                <Markdown content={msg.content} />
              </div>
            </details>
          ) : (
            <div className={`rounded-2xl px-4 py-3 text-sm ${
              isUser
                ? 'bg-primary text-primary-foreground rounded-tr-[4px]'
                : 'bg-muted rounded-tl-[4px]'
            }`}>
              {/* inverted：主色底气泡内链接须用反色，否则 text-primary 与背景同色不可见 */}
              <Markdown content={msg.content} inverted={isUser} />
            </div>
          )}

          {/* 结构化报告卡片（品类分析 + 选品可并存，逐张渲染） */}
          {reportSteps.map((step, idx) => (
            <ProductReportCard key={idx} report={step.data!.structured!} />
          ))}

          {/* 执行步骤（非报告步骤） */}
          {plainSteps.length > 0 && (
            <Card className="p-3 space-y-2 text-sm bg-background border">
              {plainSteps.map((step, j) => (
                <div key={j} className="flex items-start gap-2">
                  {step.status === 'success' ? (
                    <CheckCircle2 className="h-4 w-4 text-emerald-500 mt-0.5 shrink-0" />
                  ) : step.status === 'failed' ? (
                    <AlertCircle className="h-4 w-4 text-destructive mt-0.5 shrink-0" />
                  ) : (
                    <Loader2 className="h-4 w-4 animate-spin mt-0.5 shrink-0" />
                  )}
                  <div>
                    <span className="font-medium text-xs">{getActionLabel(step.action)}</span>
                    {step.summary && <p className="text-xs text-muted-foreground">{step.summary}</p>}
                    {step.error && <p className="text-xs text-destructive">{step.error}</p>}
                    <StepLinks step={step} />
                  </div>
                </div>
              ))}
            </Card>
          )}
        </div>
      </motion.div>
    )
  }

  return (
    <div className="flex flex-col h-[calc(100vh-6rem)] max-w-3xl mx-auto">
      {mode === 'marketing' && (
        <>
          <MarketingCampaignBar
            campaignId={campaignId}
            onCampaignChange={setCampaignId}
          />
          <div className="flex items-center gap-4 overflow-x-auto border-b px-4 py-2 text-[11px] text-muted-foreground">
            <span className="shrink-0 font-medium text-foreground">工作区</span>
            <Link to="/app/images" className="shrink-0 hover:text-foreground">图片工作台</Link>
            <Link to="/app/videos" className="shrink-0 hover:text-foreground">视频工作台</Link>
            <Link to="/app/assets" className="shrink-0 hover:text-foreground">素材中心</Link>
          </div>
        </>
      )}

      {/* ── 聊天消息区 ────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto space-y-4 px-4 py-4">
        <AnimatePresence>
          {messages.map((msg, i) => renderMessage(msg, i))}
        </AnimatePresence>

        {/* 加载中：SSE 实时推进度，无进度时仅显示 spinner */}
        {agentMutation.isPending && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex gap-3"
          >
            <AgentAvatar label={workspace.label} />
            <div className="flex-1 space-y-2">
              <div className="bg-muted rounded-2xl rounded-tl-[4px] px-4 py-3 w-fit">
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  正在分析并执行...
                </div>
              </div>
              {liveSteps.length > 0 && (
                <Card className="p-3 space-y-2 text-sm bg-background border">
                  {liveSteps.map((step, j) => (
                    <div key={j} className="flex items-start gap-2">
                      {step.status === 'success' ? (
                        <CheckCircle2 className="h-4 w-4 text-emerald-500 mt-0.5 shrink-0" />
                      ) : step.status === 'failed' ? (
                        <AlertCircle className="h-4 w-4 text-destructive mt-0.5 shrink-0" />
                      ) : (
                        <Loader2 className="h-4 w-4 animate-spin mt-0.5 shrink-0" />
                      )}
                      <div>
                        <span className="font-medium text-xs">{getActionLabel(step.action)}</span>
                        {step.summary && <p className="text-xs text-muted-foreground">{step.summary}</p>}
                        {step.error && <p className="text-xs text-destructive">{step.error}</p>}
                        <StepLinks step={step} />
                      </div>
                    </div>
                  ))}
                </Card>
              )}
            </div>
          </motion.div>
        )}

        <div ref={chatEndRef} />
      </div>

      {/* 快捷指令独立于消息数量，历史加载或长对话时保持可见。 */}
      <div className="px-4 pb-2">
        <div className="flex gap-2 overflow-x-auto pb-1">
          {workspace.actions.map((action) => {
            const Icon = ACTION_ICONS[action.icon]
            return (
              <Button
                key={action.label}
                variant="outline"
                size="sm"
                className="shrink-0 gap-1.5"
                disabled={agentMutation.isPending}
                onClick={() => handleQuickAction(action.prompt)}
              >
                <Icon className="h-3.5 w-3.5" />
                {action.label}
              </Button>
            )
          })}
        </div>
      </div>

      {/* ── 输入框 ────────────────────────────────────────── */}
      <div className="border-t bg-background px-4 py-3">
        <div className="flex gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && handleSend()}
            placeholder={workspace.placeholder}
            className="flex-1 h-11 rounded-xl border bg-muted px-4 text-sm outline-none focus:border-primary/50 focus:ring-1 focus:ring-primary/20"
            disabled={agentMutation.isPending}
          />
          <Button
            onClick={handleSend}
            disabled={!input.trim() || agentMutation.isPending}
            className="h-11 w-11 rounded-xl"
            size="icon"
          >
            <Send className="h-4 w-4" />
          </Button>
        </div>
        <p className="text-[11px] text-muted-foreground mt-1.5 text-center">
          {workspace.footer}
        </p>
      </div>
    </div>
  )
}

function AgentAvatar({ label }: { label: string }) {
  return (
    <div
      className="relative flex h-9 w-9 shrink-0 items-center justify-center rounded-[10px] border border-[var(--factory-accent)]/45 bg-[var(--factory-panel)]"
      aria-label={`VeyaShip ${label}`}
    >
      <Bot className="h-[18px] w-[18px] text-[var(--factory-accent)]" strokeWidth={1.7} />
      <Sparkles
        className="absolute -right-1 -top-1 h-3 w-3 text-[var(--factory-mint)]"
        strokeWidth={1.8}
        aria-hidden="true"
      />
      <span className="absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full border-2 border-[var(--factory-ground)] bg-[var(--factory-mint)]" />
    </div>
  )
}

function UserAvatar({
  user,
}: {
  user: { username?: string | null; full_name?: string | null; email?: string | null } | null
}) {
  const name = user?.username || user?.full_name || user?.email || '你'
  const initial = name.trim().charAt(0).toUpperCase() || '你'

  return (
    <div
      className="relative flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-border bg-[var(--factory-raised)]"
      aria-label={`${name} 的头像`}
    >
      <UserRound className="h-[18px] w-[18px] text-foreground" strokeWidth={1.7} />
      <span className="absolute -bottom-0.5 -right-0.5 flex h-3.5 w-3.5 items-center justify-center rounded-full border-2 border-[var(--factory-ground)] bg-[var(--factory-accent)] text-[7px] font-bold text-[var(--factory-ground)]">
        {initial}
      </span>
    </div>
  )
}

function StepLinks({ step }: { step: AgentStep }) {
  const links = (step.links || []).filter((link) => link.href)
  if (!links.length) return null

  return (
    <div className="mt-1.5 flex flex-wrap gap-1.5">
      {links.map((link) => {
        const className = "inline-flex items-center gap-1 rounded-md border border-primary/20 bg-primary/5 px-2 py-1 text-[11px] font-medium text-primary transition-colors hover:bg-primary/10"
        const content = (
          <>
            {link.label}
            <ExternalLink className="h-3 w-3" />
          </>
        )
        return link.href.startsWith('http') ? (
          <a
            key={`${link.href}-${link.label}`}
            href={link.href}
            target="_blank"
            rel="noreferrer"
            className={className}
          >
            {content}
          </a>
        ) : (
          <Link
            key={`${link.href}-${link.label}`}
            to={link.href}
            className={className}
          >
            {content}
          </Link>
        )
      })}
    </div>
  )
}
