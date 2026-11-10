// AI 助手对话页
const api = require('../../utils/api')

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

async function waitForAgentTask(taskId) {
  const deadline = Date.now() + 3 * 60 * 1000
  while (Date.now() < deadline) {
    const task = await api.getAgentTask(taskId)
    if (task.status === 'succeeded' || task.status === 'partial') return task
    if (task.status === 'failed') {
      throw new Error(task.error || '任务执行失败')
    }
    await sleep(2000)
  }
  throw new Error('任务执行超时')
}

Page({
  data: {
    messages: [],
    input: '',
    loading: false,
    convId: '',
  },

  onLoad() {
    this.addMessage('assistant', '你好！我是你的 AI 决策助手。\n\n📊 说"蓝牙耳机能不能做"→ 分析市场\n💰 说"算利润"→ 自动计算\n✍️ 说"生成 Listing"→ AI 写文案')
  },

  onInput(e) {
    this.setData({ input: e.detail.value })
  },

  addMessage(role, content) {
    const msgs = this.data.messages
    msgs.push({ role, content })
    this.setData({ messages: msgs })
  },

  async onSend() {
    const text = this.data.input.trim()
    if (!text || this.data.loading) return

    this.addMessage('user', text)
    this.setData({ input: '', loading: true })

    try {
      const submitted = await api.agentRun(text)
      const data = submitted.task_id && submitted.status !== 'succeeded' && submitted.status !== 'partial'
        ? await waitForAgentTask(submitted.task_id)
        : submitted
      if (data.conversation_id) {
        this.setData({ convId: data.conversation_id })
      }
      this.addMessage('assistant', data.summary || '已完成')
    } catch (e) {
      const detail = e && (e.message || (e.detail && (e.detail.message || e.detail)))
      this.addMessage('assistant', typeof detail === 'string' ? detail : '执行失败，请重试')
    }
    this.setData({ loading: false })
  },

  onQuickTap(e) {
    const text = e.currentTarget.dataset.text
    this.setData({ input: text })
  },
})
