# Agent Image Text Safety

## 目标

防止 Agent 在商品图和广告图中自由生成标题、中文卖点、数字、水印或乱码文字。
模型只负责商品与场景画面，确定性文案由前端或图像模板后处理。

## 能力点

### CAP-01 无新增文字

#### Requirement

Agent 图片任务必须在入库前统一改写提示词，禁止模型新增文字、汉字、字母、数字、
水印、字幕、标签、UI 或叠加文案。

#### Scenario

- Given 工具参数包含“留左上角文案空间”
- When 创建图片任务
- Then 提示词改为“干净留白”
- And 追加“不得新增任何文字”
- And 负向提示词包含乱码、水印和叠加文案

### CAP-02 商品文字保持

#### Requirement

商品场景必须保留参考图已有的 Logo、包装文字、型号和容量，不允许模型自行创造、
改写或补全。

#### Scenario

- Given 商品场景包含真实商品参考图
- When 生成任务入库
- Then 提示词明确商品文字严格以参考图为准

### CAP-03 工具优先级

#### Requirement

Agent 生成商品主图或场景图时必须优先使用 `generate_image_asset` 并携带参考图。
`generate_product_image` 仅用于旧客户端兼容，不允许新任务主动选择。

#### Scenario

- Given 营销 Agent 收到商品主图需求
- Then 系统提示词要求使用带参考图的 `generate_image_asset`
