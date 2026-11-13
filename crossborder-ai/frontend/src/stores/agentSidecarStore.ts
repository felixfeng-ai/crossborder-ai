import { create } from 'zustand'
import {
  deriveAgentPageContext,
  normalizeAgentPageContext,
  type AgentPageContext,
} from '@/lib/agent/sidecar'

interface AgentSidecarStore {
  isOpen: boolean
  context: AgentPageContext
  suppressedDetails: string[]
  open: () => void
  close: () => void
  setContext: (context: Partial<AgentPageContext>) => void
  removeContextDetail: (detail: string) => void
}

const initialContext = deriveAgentPageContext('/app/dashboard')

export const useAgentSidecarStore = create<AgentSidecarStore>((set) => ({
  isOpen: false,
  context: initialContext,
  suppressedDetails: [],
  open: () => set({ isOpen: true }),
  close: () => set({ isOpen: false }),
  setContext: (context) =>
    set((state) => {
      const normalized = normalizeAgentPageContext(context)
      const routeChanged = normalized.route !== state.context.route
      const suppressedDetails = routeChanged ? [] : state.suppressedDetails
      return {
        context: {
          ...normalized,
          details: normalized.details.filter(
            (item) => !suppressedDetails.includes(item),
          ),
        },
        suppressedDetails,
      }
    }),
  removeContextDetail: (detail) =>
    set((state) => ({
      context: {
        ...state.context,
        details: state.context.details.filter((item) => item !== detail),
      },
      suppressedDetails: Array.from(
        new Set([...state.suppressedDetails, detail]),
      ),
    })),
}))
