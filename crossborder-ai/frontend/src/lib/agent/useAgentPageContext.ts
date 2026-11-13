import { useEffect, useMemo } from 'react'
import { useAgentSidecarStore } from '@/stores/agentSidecarStore'
import type { AgentPageContext } from './sidecar'

/**
 * 页面把安全元数据注册到全局侧栏。
 * 只允许短文本和资源 ID，不传 File、图片内容或令牌。
 */
export function useAgentPageContext(context: AgentPageContext) {
  const setContext = useAgentSidecarStore((state) => state.setContext)
  const serialized = useMemo(() => JSON.stringify(context), [context])

  useEffect(() => {
    setContext(JSON.parse(serialized) as AgentPageContext)
  }, [serialized, setContext])
}
