# AI Marketing Video Agent

## 目标

把现有单镜头商品视频升级为面向跨境卖家的营销视频 Agent。用户输入一句营销想法，系统结合商品首帧、目标平台、市场和时长，先生成可审阅的营销 Brief 与分镜，再在用户批准后逐镜头生成并合成为 MP4。

本期不建设完整 AI 演员市场，也不把 AI 演员包装成真实消费者证言。

## 能力点

### CAP-01 营销方案生成

#### Requirement

Agent 必须把用户想法转换为结构化营销方案，包含标题、受众、营销角度、钩子、口播脚本、CTA 和 3-5 个分镜。模型不可用时必须返回可执行的确定性降级方案。

#### Scenario

- Given 用户选择自己的商品首帧并输入营销想法
- When 创建营销视频项目
- Then 返回 `brief_ready` 项目和结构化 storyboard
- And 不调用 MiniMax 视频生成

### CAP-02 审阅后渲染

#### Requirement

营销方案生成和付费渲染必须分离。只有 `brief_ready` 项目可以进入渲染，渲染前必须展示镜头数量、预计积分和工作量。

#### Scenario

- Given 项目已有方案但用户未批准
- When 查询项目
- Then 不创建视频任务且不扣积分

#### Scenario

- Given 用户批准方案
- When 调用渲染
- Then 每个分镜创建一个视频任务
- And 项目进入 `rendering`

### CAP-03 人物与商品镜头

#### Requirement

分镜 Prompt 必须区分钩子、人物演示、细节证明和 CTA。人物演示镜头只能描述品牌演示者或 AI 演示者，不得声称是真实消费者体验。

#### Scenario

- Given 用户选择“人物演示”模板
- When Agent 生成分镜
- Then 至少包含一个展示人物手持或使用商品的镜头
- And Prompt 包含商品形状、颜色、材质、Logo 和包装锁定

### CAP-04 多镜头合成

#### Requirement

所有分镜任务成功后，系统必须按分镜顺序合成一个 MP4；任一任务失败时项目失败，不得发布不完整成片。

#### Scenario

- Given 三个分镜全部成功
- When 调度器对账项目
- Then 按顺序合成 MP4
- And 保存 final_storage_key、文件大小和 SHA256

### CAP-05 积分、隔离与取消

#### Requirement

提交全部供应商任务成功后才扣项目积分。其他用户读取、取消或下载项目必须返回 404。取消项目必须取消仍在运行的镜头任务。

#### Scenario

- Given 用户积分不足
- When 批准渲染
- Then 返回 402
- And 不调用 MiniMax

#### Scenario

- Given 其他用户访问项目
- When 读取或下载
- Then 返回 404

## MVP 边界

- 支持 15、20、30 秒；3-5 个镜头。
- 支持 `presenter_demo`、`problem_solution`、`unboxing`、`feature_focus` 四类模板。
- 默认 MiniMax H3-Lite、480P、9:16。
- 支持 TikTok/Reels/Shorts、Shopify Ads、通用电商。
- 不包含人脸克隆、多人剧情、复杂物理交互、自动广告投放。
- 不自动生成未经用户确认的价格、折扣或不实宣称。
