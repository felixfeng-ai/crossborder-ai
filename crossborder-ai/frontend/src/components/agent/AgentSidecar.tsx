import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Maximize2, Plus, X } from 'lucide-react'
import { useLocation, useNavigate } from 'react-router-dom'
import { AssistantMark } from '@/components/brand/AssistantMark'
import AgentPage from '@/pages/agent/AgentPage'
import {
  buildAgentContextLabels,
  deriveAgentPageContext,
  isAgentFullPage,
} from '@/lib/agent/sidecar'
import { useAgentSidecarStore } from '@/stores/agentSidecarStore'

/**
 * 全局 AI 决策助手侧栏。
 * 组件始终挂载，关闭时只移出视口，保证运行中的 Agent 任务不被取消。
 */
export function AgentSidecar() {
  const location = useLocation()
  const navigate = useNavigate()
  const launcherRef = useRef<HTMLButtonElement>(null)
  const panelRef = useRef<HTMLElement>(null)
  const [sessionKey, setSessionKey] = useState(0)
  const [hasOpened, setHasOpened] = useState(false)

  const isOpen = useAgentSidecarStore((state) => state.isOpen)
  const context = useAgentSidecarStore((state) => state.context)
  const open = useAgentSidecarStore((state) => state.open)
  const close = useAgentSidecarStore((state) => state.close)
  const setContext = useAgentSidecarStore((state) => state.setContext)
  const removeContextDetail = useAgentSidecarStore(
    (state) => state.removeContextDetail,
  )

  const hiddenOnFullPage = isAgentFullPage(location.pathname)
  const effectiveContext =
    context.route === location.pathname
      ? context
      : deriveAgentPageContext(location.pathname)
  const contextLabels = buildAgentContextLabels(effectiveContext)

  // 路由切换先写入基础上下文，页面级 Hook 随后补充素材和模式详情。
  useLayoutEffect(() => {
    setContext(deriveAgentPageContext(location.pathname))
  }, [location.pathname, setContext])

  useEffect(() => {
    if (hiddenOnFullPage && isOpen) close()
  }, [hiddenOnFullPage, isOpen, close])

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.altKey && event.key.toLowerCase() === 'a') {
        event.preventDefault()
        if (hiddenOnFullPage) {
          navigate('/app/agent')
          return
        }
        if (useAgentSidecarStore.getState().isOpen) {
          close()
        } else {
          setHasOpened(true)
          open()
        }
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [hiddenOnFullPage, navigate, close, open])

  useEffect(() => {
    if (!isOpen) return
    panelRef.current?.focus()
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      close()
      window.requestAnimationFrame(() => launcherRef.current?.focus())
    }
    window.addEventListener('keydown', handleEscape)
    return () => window.removeEventListener('keydown', handleEscape)
  }, [isOpen, close])

  useEffect(() => {
    const panel = panelRef.current
    if (!panel) return
    if (isOpen) {
      panel.removeAttribute('inert')
    } else {
      panel.setAttribute('inert', '')
    }
  }, [isOpen])

  useEffect(() => {
    if (isOpen) setHasOpened(true)
  }, [isOpen])

  if (hiddenOnFullPage) return null

  const handleClose = () => {
    close()
    window.requestAnimationFrame(() => launcherRef.current?.focus())
  }

  return (
    <>
      <button
        ref={launcherRef}
        type="button"
        onClick={() => {
          setHasOpened(true)
          open()
        }}
        aria-label="打开 AI 决策助手"
        aria-expanded={isOpen}
        aria-controls="agent-sidecar-panel"
        tabIndex={isOpen ? -1 : 0}
        title="AI 决策助手（Alt+A）"
        className={[
          'fixed bottom-5 right-5 z-40 flex h-[72px] w-[72px] flex-col items-center justify-center gap-0.5',
          'lg:h-[78px] lg:w-[78px]',
          'rounded-full border-[1.5px] border-[var(--factory-accent)] bg-[var(--factory-panel)] text-foreground',
          'shadow-[0_12px_32px_rgba(0,0,0,0.3)] transition-all duration-200',
          'hover:-translate-y-0.5 hover:bg-[var(--factory-raised)] hover:shadow-[0_15px_38px_rgba(0,0,0,0.34)]',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background',
          isOpen
            ? 'pointer-events-none translate-y-2 opacity-0'
            : 'translate-y-0 opacity-100',
        ].join(' ')}
      >
        <AssistantMark className="h-[31px] w-[31px]" />
        <span className="text-[12px] font-semibold leading-[15px]">问 AI</span>
      </button>

      <button
        type="button"
        aria-label="关闭 AI 决策助手"
        aria-hidden={!isOpen}
        tabIndex={isOpen ? 0 : -1}
        onClick={handleClose}
        className={[
          'fixed inset-0 z-40 bg-black/55 transition-opacity duration-200 lg:hidden',
          isOpen
            ? 'pointer-events-auto opacity-100'
            : 'pointer-events-none opacity-0',
        ].join(' ')}
      />

      <aside
        id="agent-sidecar-panel"
        ref={panelRef}
        tabIndex={-1}
        aria-label="AI 决策助手"
        aria-hidden={!isOpen}
        className={[
          'fixed z-50 flex flex-col overflow-hidden border-border bg-[#111411]',
          'border-t shadow-[0_-24px_70px_rgba(0,0,0,0.48)] transition-transform duration-300 [transition-timing-function:var(--ease-drawer)]',
          'inset-x-0 bottom-0 h-[min(90dvh,860px)] rounded-t-2xl',
          'lg:inset-x-auto lg:right-0 lg:top-[58px] lg:bottom-0 lg:h-auto lg:w-[420px]',
          'lg:rounded-none lg:border-l lg:border-t-0 lg:shadow-[-22px_0_70px_rgba(0,0,0,0.38)]',
          isOpen
            ? 'pointer-events-auto translate-y-0 lg:translate-x-0'
            : 'pointer-events-none translate-y-full lg:translate-x-full',
          !isOpen && 'invisible delay-300',
        ].join(' ')}
      >
        <header className="flex min-h-[72px] shrink-0 items-center justify-between gap-3 border-b border-border px-4">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex h-11 w-11 shrink-0 items-center justify-center border border-[rgba(216,181,109,0.46)] bg-[var(--factory-panel)]">
              <AssistantMark className="h-8 w-8" />
            </div>
            <div className="min-w-0">
              <div className="truncate text-sm font-semibold leading-[22px]">
                AI 决策助手
              </div>
              <div className="mt-0.5 flex items-center gap-1.5 text-[11px] leading-4 text-[var(--factory-mint)]">
                <span className="h-1.5 w-1.5 rounded-full bg-[var(--factory-mint)]" />
                随当前页面工作
              </div>
            </div>
          </div>

          <div className="-mr-1 flex shrink-0 items-center">
            <button
              type="button"
              onClick={() => setSessionKey((value) => value + 1)}
              className="flex h-11 w-11 items-center justify-center text-muted-foreground transition-colors hover:text-foreground"
              aria-label="新建对话"
              title="新建对话"
            >
              <Plus className="h-[18px] w-[18px]" />
            </button>
            <button
              type="button"
              onClick={() => {
                close()
                navigate('/app/agent')
              }}
              className="flex h-11 w-11 items-center justify-center text-muted-foreground transition-colors hover:text-foreground"
              aria-label="展开完整 Agent 页面"
              title="展开完整页面"
            >
              <Maximize2 className="h-[17px] w-[17px]" />
            </button>
            <button
              type="button"
              onClick={handleClose}
              className="flex h-11 w-11 items-center justify-center text-muted-foreground transition-colors hover:text-foreground"
              aria-label="关闭 AI 决策助手"
            >
              <X className="h-[18px] w-[18px]" />
            </button>
          </div>
        </header>

        {contextLabels.length > 0 && (
          <div className="flex shrink-0 flex-wrap gap-1.5 border-b border-border px-4 py-2.5">
            {contextLabels.map((label, index) => {
              const removable = index > 0
              return (
                <span
                  key={label}
                  className="inline-flex min-h-7 items-center gap-1.5 border border-[rgba(216,181,109,0.26)] bg-[rgba(216,181,109,0.1)] px-2.5 text-[11px] font-medium leading-4 text-[#d8cfba]"
                >
                  <span className="h-1 w-1 rounded-full bg-[var(--factory-accent)]" />
                  <span className="max-w-[220px] truncate">{label}</span>
                  {removable && (
                    <button
                      type="button"
                      onClick={() => removeContextDetail(label)}
                      className="relative z-10 -mr-1 ml-0.5 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-sm text-[var(--factory-faint)] hover:bg-white/5 hover:text-foreground"
                      aria-label={`移除上下文：${label}`}
                    >
                      <X className="h-3 w-3" />
                    </button>
                  )}
                </span>
              )
            })}
          </div>
        )}

        {hasOpened && (
          <div className="min-h-0 flex-1">
            <AgentPage
              key={sessionKey}
              variant="sidecar"
              pageContext={effectiveContext}
              forceNewConversation={sessionKey > 0}
              loadHistory={false}
            />
          </div>
        )}
      </aside>
    </>
  )
}
