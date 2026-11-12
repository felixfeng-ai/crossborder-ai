# 营销 Agent 与快捷指令稳定性

## 目标

将通用 Agent 能力复用到营销垂直场景，提供独立“营销 Agent”入口；
同时修复对话历史异步加载导致快捷指令闪现后消失的问题。

本阶段复用现有 Agent、图片生成、视频生成和素材查询工具，不复制执行引擎。

## 能力一：营销 Agent

### Requirement

营销 Agent 与通用 AI 助手共用 `/agent/run` 和任务流，但使用营销专用欢迎语、
快捷指令、输入提示和工作区导航。

### Scenario: 进入营销 Agent

- Given 用户从侧栏进入“营销 Agent”
- Then 页面展示营销目标和多素材能力
- And 提供营销方案、商品主图、场景图、营销视频、广告文案快捷指令
- And 可以跳转图片工作台、视频工作台和素材中心
- And 对话历史与通用 AI 助手分开

### Scenario: 复用执行引擎

- Given 用户提交营销需求
- When Agent 选择工具
- Then 继续使用现有图片、视频和素材能力
- And 不创建第二套任务队列或积分逻辑

## 能力二：快捷指令稳定展示

### Requirement

快捷指令不得因为历史对话异步加载而闪现后消失。

### Scenario: 加载历史对话

- Given 页面首屏正在加载历史消息
- When 历史加载完成并替换消息列表
- Then 快捷指令仍然保持可见
- And 不产生布局跳动

### Scenario: 长对话

- Given 当前对话已经有多条消息
- Then 快捷指令仍作为紧凑横向工具条显示在输入框上方
- And 不占用主要对话空间

## 能力三：营销活动上下文

### Requirement

营销 Agent 的工作必须绑定可选营销活动；活动保存商品、目标、平台、市场、
语言、预算和状态，并在执行任务时注入 Agent 上下文。

### Scenario: 创建活动

- Given 用户填写活动名称、营销目标、平台、市场和预算
- When 创建营销活动
- Then 活动归属当前用户
- And 可选绑定当前用户商品

### Scenario: 使用活动执行 Agent

- Given 营销 Agent 已选中活动
- When 提交 Agent 指令
- Then 请求携带 `campaign_id`
- And 后端验证活动归属
- And 执行器把活动与商品上下文注入 Agent

### Scenario: 跨用户访问

- Given 其他用户的活动 ID
- When 当前用户查询或使用该活动
- Then 返回 404

## 能力四：活动素材归属与回查

### Requirement

营销活动必须聚合在活动上下文中生成的图片、商品视频和营销成片，
并提供只读素材查询接口。素材归属由生成任务上的 `campaign_id` 持久化，
不能依赖对话历史或前端临时状态推断。

### Scenario: Agent 生成素材自动绑定活动

- Given 营销 Agent 已选择当前用户的活动
- When Agent 生成商品图片、商品视频或营销视频方案
- Then 对应任务和项目保存 `campaign_id`
- And 任务完成后出现在该活动的素材列表中

### Scenario: 查询活动素材

- Given 当前用户拥有一个营销活动
- When 请求 `GET /api/v1/marketing-campaigns/{campaign_id}/assets`
- Then 返回图片、视频和营销成片的数量统计
- And 每项素材包含类型、状态、提示词、文件 URL、缩略图 URL、积分和创建时间
- And 运行中的素材支持前端定时刷新

### Scenario: 素材严格隔离

- Given 其他用户的活动或素材记录
- When 当前用户查询该活动素材
- Then 返回 404
- And 不返回其他用户或其他活动的素材

## 能力五：生成图片入库与直接图生视频

### Requirement

图片生成任务成功后，每个结果必须自动规范化为用户可复用的图片素材，
并通过生成任务和变体序号保证幂等。活动内的生成图片应能直接作为
商品图生视频的首帧，不需要用户下载后重新上传。

### Scenario: 生成结果自动入库

- Given 当前用户的图片生成任务已完成
- When 图片供应商返回一个或多个图片 URL
- Then 每个结果下载并保存为 `ImageAsset`
- And 素材保存 `generation_task_id` 和 `variant_index`
- And 重复执行不会创建重复素材

### Scenario: 素材导入失败不回滚生成结果

- Given 图片供应商已经生成成功
- When 某个结果下载或规范化失败
- Then 原图片任务仍保持 completed
- And 已成功导入的其他变体仍可使用

### Scenario: 从活动素材直接发起视频

- Given 活动素材列表返回已入库图片的 `image_asset_id`
- When 用户点击“用此图生成视频”
- Then 打开商品图生视频工作台
- And 自动选中该图片作为首帧
- And 不要求用户重新上传

### Scenario: 历史生成图片补入库

- Given 当前用户拥有一条已完成的历史图片生成任务
- When 请求 `POST /api/v1/images/history/{task_id}/materialize`
- Then 返回该任务已入库的图片素材
- And 其他用户请求同一任务返回 404

## 能力六：营销图片批量生成与变体管理

### Requirement

营销活动内应支持一次生成 1、2 或 4 张图片，并把每张输出作为独立变体
展示。变体可以重命名、删除和直接转为视频，所有操作必须限定当前用户
和当前活动。

### Scenario: 活动内批量生成

- Given 用户已选择一个营销活动
- When 提交批量图片生成请求
- Then 请求携带 `campaign_id` 和 `num_outputs`
- And 后端验证活动归属
- And 图片任务保存活动 ID 和生成数量

### Scenario: 展示独立变体

- Given 一个图片任务生成了多张图片
- When 查询活动素材
- Then 返回每个变体的素材 ID、名称、序号和缩略图
- And 图片数量按变体数量统计

### Scenario: 重命名和删除变体

- Given 用户拥有一个生成图片变体
- When 用户重命名或删除该变体
- Then 只影响该变体
- And 其他用户操作返回 404
- And 删除最后一个变体后，活动素材板不再展示空图片任务

### Scenario: 桌面和移动端素材板

- Given 活动内有多个图片变体
- When 在桌面或 390px 移动端打开营销 Agent
- Then 素材板可横向浏览全部变体
- And 重命名、删除、转视频和下载操作保持可用

## 能力七：营销文案资产化

### Requirement

营销 Agent 必须把生成文案保存为活动资产，而不是只返回临时聊天文本。
一次生成应同时产出 TikTok、Amazon、Shopify 三个平台，以及每个平台
A/B 两个版本。每条文案保存平台约束、标题、正文、CTA、标签、关键词、
来源模型和合规状态。

### Scenario: 生成多平台 A/B 文案

- Given 营销活动绑定了商品、目标市场和营销目标
- When 用户选择三个平台并生成文案
- Then 创建同一个 `batch_id` 下的六条文案资产
- And 每个平台包含 A、B 两个独立变体
- And 文案保存活动、用户、平台、语言和合规结果

### Scenario: 失败降级

- Given 文本模型返回空内容或无法解析的 JSON
- When 生成营销文案
- Then 系统使用基于商品事实的确定性降级文案
- And 仍然创建可编辑的 A/B 资产
- And 不伪造价格、折扣或未提供的商品事实

### Scenario: 活动文案素材板

- Given 活动已经生成多平台文案
- When 用户打开营销 Agent
- Then 可以按 TikTok、Amazon、Shopify 切换查看
- And 每个平台显示 A/B 两个版本
- And 可以看到标题、正文、CTA、标签和合规状态
- And 可以复制、编辑或删除单条文案

### Scenario: 权限隔离

- Given 其他用户的活动或文案资产
- When 当前用户生成、查询、编辑或删除文案
- Then 返回 404

### Scenario: Agent 工具

- Given 营销 Agent 已选择活动
- When 用户要求生成广告文案
- Then Agent 调用 `generate_marketing_copy`
- And 工具把结果持久化为活动文案资产
- And 返回活动素材板链接和批次摘要

## 能力八：活动发布与效果回流

### Requirement

营销活动必须记录各平台的发布结果和效果快照。平台真正具备发布能力时，
调用真实发布服务；平台尚未接入时必须记录明确的能力状态，不能生成虚假
外部商品 ID 或成功状态。

### Scenario: Shopify 文案发布

- Given 活动有通过合规检查的 Shopify 文案、绑定商品和启用店铺
- When 用户发起活动发布
- Then 生成活动 Listing 并调用现有 Shopify 发布服务
- And 活动发布记录关联文案、Listing 和统一 Publication

### Scenario: Amazon 能力状态

- Given Amazon Listing 发布尚未接入
- When 用户发起 Amazon 活动发布
- Then 返回并保存 `unavailable` 状态
- And 显示真实的缺失能力原因

### Scenario: 效果数据回流

- Given 活动已有 TikTok、Amazon 或 Shopify 效果数据
- When 用户导入曝光、点击、订单、花费和收入
- Then 数据保存为活动效果快照
- And 活动页面计算 CTR、CVR、ROAS 和累计收入

### Scenario: 用户隔离

- Given 其他用户的活动或效果数据
- When 当前用户查询、发布或导入
- Then 返回 404

## 验收标准

- 通用 Agent 与营销 Agent 的文案和快捷指令不同。
- 两个入口共用同一个 Agent API。
- 历史消息加载前后快捷指令均为可见状态。
- 活动内生成的图片、视频和营销成片可回查并展示缩略图。
- 活动素材不会跨用户或跨活动泄漏。
- AI 生成图可在图片工作台、素材中心和视频首帧选择器中复用。
- 活动支持 1/2/4 张批量图片生成，并逐变体展示和管理。
- 营销文案按平台和 A/B 版本持久化，并可在活动素材板管理。
- 活动发布记录和效果指标归属当前活动，Amazon 不伪造发布成功。
- 桌面和 390px 移动端完成真实截图验证。
