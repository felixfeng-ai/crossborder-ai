import fs from 'node:fs'
import path from 'node:path'

import { describe, expect, it } from 'vitest'

import {
  agentConversationScope,
  resolveAgentConversationId,
} from './conversation-selection'

describe('agent conversation selection', () => {
  it('restores the newest cached conversation when returning to the page', () => {
    const scope = agentConversationScope('general', '')

    expect(
      resolveAgentConversationId({
        scope,
        selection: { scope: '', id: '' },
        recentConversations: [{ id: 'cached-conversation' }],
        loadHistory: true,
        forceNewConversation: false,
      }),
    ).toBe('cached-conversation')
  })

  it('keeps the current conversation after a new task returns its id', () => {
    const scope = agentConversationScope('general', '')

    expect(
      resolveAgentConversationId({
        scope,
        selection: { scope, id: 'new-conversation' },
        recentConversations: [{ id: 'older-conversation' }],
        loadHistory: false,
        forceNewConversation: true,
      }),
    ).toBe('new-conversation')
  })

  it('ignores a conversation selected for a different campaign', () => {
    const scope = agentConversationScope('marketing', 'campaign-b')

    expect(
      resolveAgentConversationId({
        scope,
        selection: {
          scope: agentConversationScope('marketing', 'campaign-a'),
          id: 'campaign-a-conversation',
        },
        recentConversations: [{ id: 'campaign-b-conversation' }],
        loadHistory: true,
        forceNewConversation: false,
      }),
    ).toBe('campaign-b-conversation')
  })

  it('starts empty for a forced new conversation', () => {
    const scope = agentConversationScope('general', '')

    expect(
      resolveAgentConversationId({
        scope,
        selection: { scope: '', id: '' },
        recentConversations: [{ id: 'cached-conversation' }],
        loadHistory: false,
        forceNewConversation: true,
      }),
    ).toBe('')
  })

  it('uses scoped selection instead of an effect that clears restored context', () => {
    const source = fs.readFileSync(
      path.resolve(process.cwd(), 'src/pages/agent/AgentPage.tsx'),
      'utf8',
    )

    expect(source).toContain('resolveAgentConversationId')
    expect(source).toContain('handleCampaignChange')
    expect(source).not.toContain("setConversationId('')")
  })
})
