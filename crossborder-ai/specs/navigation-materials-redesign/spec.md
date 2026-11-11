# Navigation and Material Center Redesign

## 目标

把当前按功能平铺的侧栏重组为跨境运营工作流，合并重复的视频入口，增加统一素材中心，并让顶部栏和品牌标识表达当前工作区而不是重复品牌口号。

## 能力点

### CAP-01 分组导航

#### Requirement

侧栏必须按“经营、AI 创作、运营、账户”分组；同一业务只保留一个一级入口。

#### Scenario

- Given 用户打开应用侧栏
- When 浏览导航
- Then 看到四个明确分组
- And 视频只有一个“视频工作台”入口
- And 批量导入不再占用一级导航

### CAP-02 视频工作台合并

#### Requirement

营销成片和商品图生视频必须在同一个页面的顶部 Tab 中切换。

#### Scenario

- Given 用户打开视频工作台
- When 切换“营销成片”和“商品图生视频”
- Then URL 查询参数和行为同步变化
- And 旧营销视频地址重定向到营销 Tab

### CAP-03 素材中心

#### Requirement

素材中心必须聚合当前用户已完成的图片和视频素材，并支持按来源筛选。

#### Scenario

- Given 用户拥有上传图、白底图、AI 图、商品图生视频和营销成片
- When 打开素材中心
- Then 图片和视频分别展示
- And 来源筛选可区分上传、白底、AI、商品图生视频和营销成片
- And 只展示已完成的图片/视频

### CAP-04 页面上下文与品牌

#### Requirement

顶部栏必须显示当前页面名称和工作分组，侧栏品牌标识使用自定义 V 路线标记，副标题为“AI 跨境运营台”。

#### Scenario

- Given 用户进入素材中心
- When 查看顶部栏
- Then 显示“AI 创作 / 素材中心”
- And 不再固定显示重复的“跨境决策台”

### CAP-05 Listing 入口收敛

#### Requirement

Listing 生成不再作为一级导航；Listing 中心必须提供进入 AI Listing 生成的操作。

#### Scenario

- Given 用户进入 Listing 中心
- When 查看页面主操作
- Then 可以进入 AI 生成 Listing
