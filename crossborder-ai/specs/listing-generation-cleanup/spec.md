# Listing Generation Cleanup

## 目标

让 Listing 生成页面只负责标题、描述、卖点、SEO 与合规，不再同步承载专家 Agent 和商品主图生成。商品图片统一进入图片工作台处理。

## 能力点

### CAP-01 文案生成页面收敛

#### Requirement

Listing 页面不得展示“专家模式”和“AI 生成商品主图”开关。页面主操作只生成 Listing 文案。

#### Scenario

- Given 用户进入 Listing 生成页面
- When 查看生成参数
- Then 只看到商品、平台、语气和输出语言
- And 看不到专家模式与商品主图开关

### CAP-02 旧客户端参数兼容

#### Requirement

旧客户端仍可能提交 `expert_mode`、`generate_image` 和 `image_prompt`。后端必须接收请求但不能触发专家 Agent 或图片任务。

#### Scenario

- Given 请求携带专家模式和图片生成参数
- When 调用 Listing 生成
- Then 按普通文案链路生成
- And 不创建图片任务、不返回 image_task_id

### CAP-03 商品事实注入

#### Requirement

普通 Listing 生成必须使用商品描述、价格、店铺、销量和已有主图信息，不能只依赖标题。

#### Scenario

- Given 商品已有描述和销量
- When 生成描述与卖点
- Then Prompt 包含描述、价格、店铺和销量

### CAP-04 图片入口迁移

#### Requirement

Listing 页面展示当前真实商品主图，并引导用户进入图片工作台处理平台尺寸、白底图或营销图。

#### Scenario

- Given 商品已有主图
- When 用户查看商品上下文
- Then 页面显示主图预览
- And 提供进入图片工作台的入口

#### Scenario

- Given 商品没有主图
- When 用户查看商品上下文
- Then 提示先补充真实商品图片
- And 不提供“根据标题生成主图”的快捷操作
