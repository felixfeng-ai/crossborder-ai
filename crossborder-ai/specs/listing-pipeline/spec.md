# Listing Pipeline

## 目标

把 AI 生成的 Listing 从一次性响应升级为可追踪、可审核、可发布的业务实体。Web、Agent 和后续批量链路统一以该 Listing 作为内容事实源。

## 能力点

### CAP-01 Listing 持久化

#### Requirement

AI 文案生成成功后，系统必须保存一条属于当前用户和当前商品的 ListingDraft，并返回其 ID。

#### Scenario

- Given 当前用户拥有一个商品
- When 用户请求生成 Listing 且 AI 返回有效内容
- Then 系统创建 ListingDraft
- And 响应包含 `listing_id`
- And 商品历史接口可以查询到该记录

### CAP-02 合规报告绑定版本

#### Requirement

每次生成 Listing 时必须保存与 `listing.version` 绑定的合规报告。内容被修改后，旧报告不得继续作为发布依据。

#### Scenario

- Given AI 返回的文案命中违禁词
- When 系统保存 ListingDraft
- Then ListingDraft 状态为 `blocked`
- And 合规报告状态为 `block`
- And 发布接口拒绝发布并返回 409

### CAP-03 从 Listing 发布 Shopify

#### Requirement

用户提交 `listing_id` 发布时，Shopify 必须使用 ListingDraft 中的标题、描述和卖点，而不是原始 Product 字段。

#### Scenario

- Given ListingDraft 属于当前用户且合规状态为 `pass`
- When 用户请求发布到自己的 Shopify 渠道
- Then Shopify 请求体包含 ListingDraft 的文案
- And 发布记录绑定该 ListingDraft

#### Scenario

- Given ListingDraft 属于其他用户
- When 当前用户请求发布
- Then 系统返回 404

### CAP-04 历史接口

#### Requirement

商品详情页必须通过受鉴权和归属校验的接口获取该商品的 Listing 历史。

#### Scenario

- Given 当前用户生成了两个 ListingDraft
- When 请求 `GET /api/v1/products/{product_id}/listings`
- Then 返回两条当前用户记录
- And 不返回其他用户记录

### CAP-05 批量任务归属

#### Requirement

批量任务转换成商品时必须写入当前用户 `user_id`，商品可通过正常商品列表查询。

#### Scenario

- Given 当前用户上传了一条 CSV
- When 用户处理该批量任务
- Then 创建的商品属于当前用户
- And 商品列表可以查询到该商品

### CAP-06 批量 AI 持久化

#### Requirement

批量 AI 处理必须保存 ListingDraft、合规报告和任务关联，不得只返回生成文本后丢弃。

#### Scenario

- Given Standard 用户有 pending 批量任务和足够积分
- When 用户触发 `/batch/process-ai`
- Then 每个成功任务生成 ListingDraft
- And BatchJob 记录 `product_id` 和 `listing_id`
- And 商品 Listing 历史可查询生成结果
- And 每个成功任务扣 1 积分

### CAP-07 批量 AI 前端入口

#### Requirement

批量页面必须提供触发 AI 批量生成的入口，而不是只暴露普通商品导入。

#### Scenario

- Given 当前存在 pending 批量任务
- When 用户点击“AI 批量生成”
- Then 页面调用 `/batch/process-ai`
- And 成功后刷新任务列表

### CAP-08 商品 URL 用户级唯一

#### Requirement

同一 1688 URL 可以被不同用户分别录入，但同一用户不能重复录入。

#### Scenario

- Given 用户 A 已录入 URL X
- When 用户 B 录入相同 URL X
- Then 用户 B 创建成功
- And 用户 A 和用户 B 各自只能看到自己的商品

### CAP-09 Listing 编辑与重新合规

#### Requirement

用户可以查看和编辑自己的 ListingDraft。每次编辑必须递增版本并使旧合规报告失效；重新执行合规检查后才能再次发布。

#### Scenario

- Given 用户拥有一个合规通过的 ListingDraft
- When 用户修改标题或描述
- Then `version` 递增
- And `compliance_status` 变为 `unknown`
- And 旧版本合规报告不能用于发布

#### Scenario

- Given ListingDraft 已编辑但尚未重新合规
- When 用户调用重新合规接口且正文无违规词
- Then 生成绑定最新版本的新合规报告
- And ListingDraft 状态变为 `ready`

#### Scenario

- Given 编辑后的正文命中违禁词
- When 用户重新合规
- Then ListingDraft 状态变为 `blocked`
- And 发布接口返回 409

#### Scenario

- Given ListingDraft 属于其他用户
- When 当前用户读取、编辑或重新合规
- Then 系统返回 404

### CAP-10 图片任务持久化队列

#### Requirement

图片生成任务提交后不得依赖当前进程内的 `asyncio.create_task`。任务必须由数据库队列消费，支持多 worker 抢占和进程重启恢复。

#### Scenario

- Given 专业版用户提交图片生成请求
- When 接口创建 pending 任务
- Then 不创建进程内后台协程
- And 任务记录包含 `num_outputs`、`attempts`

#### Scenario

- Given 数据库中存在 pending 图片任务
- When 调度器执行抢占
- Then 最多抢占 4 条任务
- And 状态变为 `processing`
- And `attempts` 递增

#### Scenario

- Given 图片任务停留在 processing 超过 10 分钟
- When 调度器执行恢复
- Then 未达到 3 次尝试的任务回到 pending
- And 达到上限的任务标记 failed

#### Scenario

- Given 任务已被 Worker 抢占为 processing
- When 图片服务成功返回 URL
- Then 任务写回 completed、image_urls 和 model_used

### CAP-11 Provider 配置中心

#### Requirement

平台管理员必须能在设置页更新 DeepSeek、Onebound、通义万相、Replicate 和 Shopify 应用配置。敏感字段加密存储，业务服务通过运行时缓存读取，无需修改 `.env` 或重启当前进程。

#### Scenario

- Given 管理员提交 DeepSeek API Key 和模型名
- When 保存 Provider 配置
- Then 数据库只保存加密后的 API Key
- And 当前进程缓存立即刷新
- And 后续 DeepSeek 请求使用新 Key 和模型

#### Scenario

- Given 普通用户访问 Provider 配置接口
- When 请求查看或修改配置
- Then 系统返回 403

#### Scenario

- Given 管理员查看 Provider 状态
- When 返回配置结果
- Then 敏感字段只返回掩码
- And 返回是否已配置

#### Scenario

- Given 其他 Worker 使用旧缓存
- When 调度器执行 Provider 刷新
- Then 缓存从 SystemConfig 重新加载

### CAP-12 PostgreSQL 生产门禁

#### Requirement

生产关键路径必须在真实 PostgreSQL 上验证，不得只依赖 SQLite 测试。CI 必须执行迁移、UUID 外键、并发积分扣减、任务抢占和租户隔离。

#### Scenario

- Given 空 PostgreSQL 数据库
- When CI 执行 `alembic upgrade head`
- Then 所有迁移成功
- And `listings`、`listing_drafts`、`image_generation_tasks` 的 UUID 外键合法

#### Scenario

- Given 用户只剩 1 积分
- When 两个独立事务并发送 `deduct_credits(1)`
- Then 只有一个成功
- And 最终积分不小于 0

#### Scenario

- Given 一个 pending Agent 任务和一个 pending 图片任务
- When 调度器连续执行两次抢占
- Then 第一次各返回一条
- And 第二次不再返回同一任务

#### Scenario

- Given 两个用户录入相同商品 URL
- When PostgreSQL 持久化商品和 Listing
- Then 两个用户可以各自创建成功
- And 查询结果不会跨用户泄露

### CAP-13 Creem Webhook 签名校验

#### Requirement

Creem webhook 必须使用原始请求体和 `CREEM_WEBHOOK_SECRET` 计算 HMAC-SHA256，并与 `creem-signature` 进行固定时间比较。未配置密钥或签名非法时必须拒绝。

#### Scenario

- Given 已配置 webhook secret
- When 使用正确原始请求体和签名调用校验
- Then 校验通过

#### Scenario

- Given 请求体被修改或签名错误
- When 调用校验
- Then 校验失败

#### Scenario

- Given 未配置 webhook secret
- When 调用校验
- Then 必须 fail closed，不得返回通过

### CAP-14 Just One API 优先抓取

#### Requirement

1688 商品详情抓取优先使用 Just One API V2。只有 Just One API 未配置或调用失败时，才允许降级到 Onebound 和直抓。

#### Scenario

- Given Just One API Token 和 Onebound Key 都已配置
- When 用户提交 1688 商品链接
- Then 系统优先调用 Just One API
- And Onebound 不应被调用
- And 返回 `data_source=justone`

#### Scenario

- Given Just One API 暂时不可用但 Onebound 可用
- When 用户提交商品链接
- Then 系统自动降级到 Onebound
- And 返回 `data_source=onebound`

#### Scenario

- Given Just One API 返回 `code=0` 且 data 为空
- When 系统处理响应
- Then 返回商品不存在，不继续直抓无效链接

#### Scenario

- Given 只配置 Just One API Token
- When 用户访问商品抓取就绪探针
- Then 系统应显示已配置

### CAP-15 前端 API 契约门禁

#### Requirement

前端源码中的每个后端 API 调用都必须能在 OpenAPI 路径中找到对应方法和路径形状，防止页面调用不存在的接口。

#### Scenario

- Given 前端调用 `apiClient.post('/agent/run')`
- When 契约测试扫描前端源码
- Then OpenAPI 必须包含 `POST /api/v1/agent/run`

#### Scenario

- Given 前端保留未实现接口 `/auth/refresh`
- When 契约测试执行
- Then 测试必须失败并指出该接口缺失

### CAP-16 前端 Vitest 基础门禁

#### Requirement

前端核心纯逻辑必须纳入 Vitest，并在 CI 中执行，不能只依赖 TypeScript 和构建。

#### Scenario

- Given 后端返回字符串、对象、422 数组或无 detail 的错误
- When 调用 `toErrorMessage`
- Then 始终输出适合卖家阅读的中文文案

#### Scenario

- Given 前端安装依赖
- When 执行 `npm test`
- Then Vitest 用例必须通过

### CAP-17 多平台发布基础

#### Requirement

平台发布必须统一记录 `listing_id`、平台、渠道、幂等键、外部商品 ID 和发布状态。相同用户使用相同幂等键重复请求时，不得重复创建外部商品。

#### Scenario

- Given Shopify 首次发布成功
- When 用户使用相同 `Idempotency-Key` 再次发布
- Then 系统返回第一次发布结果
- And 不再调用 Shopify 创建商品

#### Scenario

- Given 发布请求没有幂等键
- When 用户重复点击发布
- Then 系统仍必须在响应中返回可追踪的 publication_id

#### Scenario

- Given 平台能力查询
- When 用户查看发布平台
- Then 只有已接入的平台标记为可发布
- And Amazon/Temu/SHEIN 在未接入前必须明确标记为不可用

### CAP-18 Listing 附图轮询闭环

#### Requirement

Listing 生成响应包含 `image_task_id` 时，前端必须轮询图片任务，直到完成、失败或超时，并向用户展示真实状态。

#### Scenario

- Given 图片任务先返回 processing
- When 后续状态变为 completed
- Then 前端拿到 image_urls
- And 在 Listing 结果区展示生成图片

#### Scenario

- Given 图片任务返回 failed
- When 前端轮询到失败
- Then 展示中文失败原因

#### Scenario

- Given 图片任务长时间未结束
- When 超过轮询截止时间
- Then 展示图片生成超时
- And 不阻塞 Listing 文案结果

### CAP-19 Amazon SP-API 授权连接

#### Requirement

Amazon 应用授权必须使用平台级 App ID、Client ID、Client Secret 和回调地址，并保存卖家级 Refresh Token。Refresh Token 必须加密存储，不能返回前端。

#### Scenario

- Given 平台已配置 Amazon SP-API 应用参数
- When 登录用户请求 Amazon 连接地址
- Then 返回 Seller Central 授权 URL
- And URL 包含 application_id 和短时 state

#### Scenario

- Given Amazon 回调携带有效授权码和 state
- When 后端用授权码换取 Refresh Token
- Then 调用 Marketplace Participations 验证授权
- And 加密保存卖家连接
- And 跳回设置页

#### Scenario

- Given 用户已绑定 Amazon
- When 查询平台连接列表
- Then 不返回 Refresh Token 明文

#### Scenario

- Given Amazon 应用参数或 Token 缺失
- When 请求连接或测试
- Then 返回明确中文错误

### CAP-20 SKU / 变体主数据

#### Requirement

每个商品必须支持多个 SKU 变体。变体包含用户级唯一 SKU、属性、价格、成本、库存、条码和图片，且只能由商品所属用户管理。

#### Scenario

- Given 用户拥有一个商品
- When 创建颜色和尺寸不同的两个变体
- Then 商品变体列表返回两条
- And 每个变体 SKU 在用户范围内唯一

#### Scenario

- Given 用户修改变体价格和库存
- When 保存变体
- Then 修改结果持久化

#### Scenario

- Given 商品属于其他用户
- When 当前用户查询、创建或删除变体
- Then 返回 404

#### Scenario

- Given 用户重复提交相同 SKU
- When 创建变体
- Then 返回 409

### CAP-21 SKU 批量库存调整

#### Requirement

商品详情页必须支持一次提交多个 SKU 的库存数量。批量更新必须具备原子性：任一变体不存在、不属于当前用户或不属于当前商品时，整批拒绝且不得修改其他变体库存。

#### Scenario

- Given 当前用户拥有一个包含多个 SKU 的商品
- When 用户一次提交多个变体的新库存数量
- Then 系统在一个事务中更新全部变体
- And 返回更新后的变体列表

#### Scenario

- Given 批量请求中存在不属于当前商品的变体 ID
- When 用户提交批量库存调整
- Then 系统返回 404
- And 同批次中合法变体的库存保持不变

#### Scenario

- Given 批量请求包含重复的变体 ID
- When 用户提交批量库存调整
- Then 系统返回 422
- And 不执行任何库存修改

#### Scenario

- Given 商品属于其他用户
- When 当前用户请求批量调整库存
- Then 系统返回 404

## 非目标

- 本次不实现可视化工作流编辑器。
- 本次不接入新的外部 AI 或图片供应商。
- 本次不改变现有套餐规则。
