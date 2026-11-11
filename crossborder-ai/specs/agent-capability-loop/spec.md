# AI 助手能力闭环

## 目标

让 AI 助手从“只会分析和生成文案”升级为能驱动平台现有商品、Listing、图片、视频和素材能力的业务入口。Agent 的每次高成本操作都必须可预期、可追踪，并能从执行结果进入对应业务页面继续处理。

## 能力点

### CAP-01 Listing 生成统一

#### Requirement

网页 Listing 生成和 Agent Listing 生成必须复用同一套业务服务，商品描述、店铺、销量、主图等事实必须进入 Prompt，SEO 标题和 SEO 描述必须完整生成并落库。

#### Scenario

- Given 用户拥有一个包含描述、价格、店铺和销量的商品
- When 用户通过网页或 AI 助手生成 Listing
- Then 两种入口得到相同的字段结构和合规状态
- And SEO 标题、SEO 描述不为空
- And 返回可跳转到商品详情页 Listing 编辑区的链接

### CAP-02 Listing 回查与编辑

#### Requirement

Agent 必须能读取当前用户拥有的 Listing，并按指定字段修改 Listing 内容。修改后必须递增版本、重置合规状态，旧合规报告不得继续用于发布。

#### Scenario

- Given 用户拥有一个已生成的 Listing
- When 用户要求 Agent 修改标题、描述、卖点或 SEO
- Then Agent 保存修改并返回新版本号
- And compliance_status 变为 unknown
- And 返回 Listing 编辑入口

### CAP-03 商品图片与图生视频

#### Requirement

Agent 可以根据商品事实提交商品图片生成任务；也可以基于用户已上传的商品首帧提交商品图生视频任务。提交视频前必须获得用户明确确认，并返回预计积分和任务链接。

#### Scenario

- Given 用户具备对应套餐权限
- When 用户明确要求生成商品图片
- Then 系统创建持久图片任务并返回任务 ID
- When 用户明确确认生成商品图生视频且提供首帧素材
- Then 系统检查积分并提交 MiniMax 任务
- And 返回任务 ID、预计积分和视频工作台链接

### CAP-04 营销成片方案

#### Requirement

Agent 可以把营销想法生成结构化营销视频项目与分镜，但不得自动渲染视频。渲染必须由用户在视频工作台再次确认。

#### Scenario

- Given 用户提供商品首帧、商品名、营销想法、平台和时长
- When 用户要求 Agent 策划营销视频
- Then 系统创建状态为 brief_ready 的项目
- And 返回分镜摘要、预计积分和项目链接
- And 不调用视频供应商、不扣视频积分

### CAP-05 素材查询与结果闭环

#### Requirement

Agent 必须能查询当前用户的图片、商品视频和营销成片素材，并在生成类步骤中返回可点击业务入口。所有查询和操作必须按用户隔离。

#### Scenario

- Given 用户拥有已完成的图片和视频
- When 用户询问“有哪些素材”
- Then Agent 返回图片、视频和营销项目计数及最近素材摘要
- And 返回素材中心链接
- Then 用户可以从 Agent 消息直接进入素材或业务页面继续处理

## 非目标

- 本轮不新增 Amazon、Temu、SHEIN 的实际上架 API。
- 本轮不允许 Agent 未经确认直接渲染营销成片。
- 本轮不把 LLM 生成的市场指标伪装成实时平台数据。
