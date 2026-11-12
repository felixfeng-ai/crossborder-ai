# VeyaShip 待办事项

更新时间：2026-11-12

## P1：React Native 移动端

状态：未启动，后续处理。

### 产品定位

移动端采用“移动运营助手”，不直接一比一复制桌面 Web：

- AI 助手对话与任务提交
- 营销成片、专业分镜和商品视频的生成进度
- 视频预览、下载、分享与失败重试
- 商品拍照、相册上传和自有商品快速录入
- 审批、待办与任务通知
- 积分、套餐和任务状态摘要

暂不进入首版：

- 完整 Listing 编辑器
- 复杂商品变体表格
- 批量图片工作台
- 专业分镜长文本编辑器
- 管理后台、升级审核和完整账单操作
- 复杂店铺授权和渠道配置

### 技术路线

- Expo + React Native
- monorepo：`apps/web`、`apps/mobile`、`packages/api-client`、
  `packages/domain`、`packages/design-tokens`
- React Query、Zustand、i18next 继续复用
- SecureStore 保存登录令牌
- expo-image-picker / expo-document-picker 处理上传
- expo-video / expo-file-system 处理视频预览和下载
- APNs / FCM 处理任务完成、失败和审批通知

### 启动前置条件

- [ ] 增加 Refresh Token 和令牌轮换
- [ ] 抽出平台无关的 API Client 和领域类型
- [ ] 为图片、CSV、视频上传提供移动端验证
- [ ] 为 Agent 流式输出提供 RN 可用的 SSE 或 WebSocket
- [ ] 增加设备 Token 注册接口
- [ ] 评估 iOS/Google Play 积分和订阅支付合规
- [ ] 完成账号删除、隐私政策和推送授权

### 验收门槛

- iOS 和 Android 都能完成登录、AI 对话、上传和视频任务跟踪
- 弱网、后台切换和 token 过期可以恢复
- 视频任务通过推送通知，不依赖页面持续轮询
- 原生端不依赖 WebView 承载完整产品

## P2：视频模型供应商扩展

状态：Provider 抽象进行中；第二供应商已选定即梦/Seedance，
真实 API 接入尚未开始。不直接同时接入多个模型。

建议顺序：

1. 先抽出通用视频 Provider 接口，解耦当前 MiniMax 专用执行器
2. 接入即梦/Seedance 并用同一脚本做盲测
3. 根据商品一致性、人物稳定性、运动质量、文字保持、失败率和成本决定是否上线
4. 最多保留 2-3 个长期供应商，避免维护面失控

候选：

- 即梦/Seedance 生态：第二供应商，优先验证动态效果、营销视觉和中文场景理解
- 可灵：未选候选，暂不投入接口开发
- MiniMax：多参考图、原生音频、成本和 API 稳定性

接入前必须覆盖：

- 提交、查询、取消和下载适配
- 首帧、尾帧、多参考图和音频能力矩阵
- 供应商专属提示词编译器
- 计费与成本对账
- 失败自动退还积分
- 模型评测和回退策略
