// API 服务
const app = getApp()

function request(method, path, data = {}) {
  return new Promise((resolve, reject) => {
    const token = app.globalData.token
    const header = { 'Content-Type': 'application/json' }
    if (token) header['Authorization'] = `Bearer ${token}`

    wx.request({
      url: app.globalData.apiBase + path,
      method,
      header,
      data,
      timeout: 30000,
      success: (res) => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data)
        } else if (res.statusCode === 401) {
          wx.removeStorageSync('token')
          wx.reLaunch({ url: '/pages/index/index' })
          reject(res.data)
        } else {
          reject(res.data)
        }
      },
      fail: reject,
    })
  })
}

module.exports = {
  // 微信登录
  wxLogin: (code) => request('POST', '/auth/wx-login', { code }),

  // 品类分析
  categoryAnalysis: (keyword) =>
    request('GET', `/analytics/category?keyword=${encodeURIComponent(keyword)}`),

  // 利润计算
  calculateProfit: (data) => request('POST', '/ledger/calculate', data),

  // Dashboard
  getDashboard: () => request('GET', '/analytics/dashboard'),

  // 合规检查
  complianceCheck: (text) => request('POST', '/shopify/compliance', { text }),

  // AI 助手
  agentRun: (instruction) => request('POST', '/agent/run', { instruction }),
  getAgentTask: (taskId) => request('GET', `/agent/tasks/${taskId}`),

  // 整店巡检
  getStoreCheckHistory: () => request('GET', '/analytics/store-check-history'),
  runStoreCheck: () => request('POST', '/analytics/store-check'),

  // Shopify 渠道 / 订单
  getChannels: () => request('GET', '/shopify/channels'),
  getOrders: (channelId) => request('GET', `/shopify/orders?channel_id=${channelId}`),
}
