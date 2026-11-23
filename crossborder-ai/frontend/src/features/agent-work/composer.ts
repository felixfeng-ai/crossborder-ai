export type AgentComposerMode = 'text' | 'link' | 'order'

export interface AgentComposerDraft {
  mode: AgentComposerMode
  text: string
  imageAssetIds: string[]
  audioAssetId: string | null
  recording: boolean
}

export interface AgentTurnPayload {
  input_type: 'text' | 'voice' | 'image' | 'link'
  text?: string
  source_url?: string
  asset_ids?: string[]
  audio_asset_id?: string
}

function isHttpUrl(value: string): boolean {
  try {
    const url = new URL(value)
    return url.protocol === 'https:' || url.protocol === 'http:'
  } catch {
    return false
  }
}

export function detectAgentInputType(
  text: string,
  mode: AgentComposerMode,
): 'text' | 'link' {
  return mode !== 'order' && isHttpUrl(text.trim()) ? 'link' : 'text'
}

export function canSubmitAgentDraft(draft: AgentComposerDraft): boolean {
  if (draft.recording) return false
  const text = draft.text.trim()
  if (draft.imageAssetIds.length || draft.audioAssetId) return true
  if (!text) return false
  if (draft.mode === 'link') return isHttpUrl(text)
  return true
}

export function buildAgentTurnPayload(
  draft: AgentComposerDraft,
): AgentTurnPayload {
  const text = draft.text.trim()
  const inputType = detectAgentInputType(text, draft.mode)

  if (draft.imageAssetIds.length) {
    return {
      input_type: 'image',
      text: text || undefined,
      asset_ids: draft.imageAssetIds,
      audio_asset_id: draft.audioAssetId || undefined,
    }
  }
  if (draft.audioAssetId) {
    return {
      input_type: 'voice',
      text: text || undefined,
      audio_asset_id: draft.audioAssetId,
    }
  }
  if (inputType === 'link') {
    return {
      input_type: 'link',
      text,
      source_url: text,
    }
  }
  return { input_type: 'text', text }
}
