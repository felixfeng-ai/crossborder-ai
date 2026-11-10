# Listing Content Rendering

## 目标

AI 生成的 Listing 内容必须在工作台中以可读、可复核的结构展示，而不是把 Markdown 或 HTML 源码直接铺在页面上。SEO 字段必须保持短摘要语义，不得在生成失败时退化为整篇商品描述。

## 能力点

### CAP-01 商品详情安全预览

#### Requirement

商品详情必须区分预览和源码。Markdown 可以格式化展示，HTML 必须经过清洗后展示，禁止把未经处理的模型输出直接注入 DOM。

#### Scenario

- Given AI 返回包含标题、简短描述和 HTML 详情的历史内容
- When 用户查看生成结果
- Then 页面默认展示内容预览
- And HTML 标签不会以源码形式铺在预览中
- And 用户可以切换到源码视图并复制原文

### CAP-02 长内容折叠

#### Requirement

详情内容超过预览高度时必须折叠，用户可以展开和收起，避免连续长文造成扫读疲劳。

#### Scenario

- Given 商品详情超过默认预览高度
- When 用户打开结果卡片
- Then 页面显示展开入口
- And 展开后保留完整内容

### CAP-03 SEO 摘要约束

#### Requirement

SEO 描述必须是纯文本短摘要，建议长度为 140-160 字符。生成失败时不得复制整篇商品描述。

#### Scenario

- Given AI 没有返回可解析的 SEO JSON
- When 系统生成 SEO 降级结果
- Then SEO 描述由正文纯文本摘要生成
- And 长度不超过 160 字符
- And 不包含 Markdown、HTML 标签或代码围栏

#### Scenario

- Given AI 返回包含 Markdown 或 HTML 的 SEO 描述
- When 系统保存结果
- Then SEO 描述被规范化为纯文本
- And 超长内容被安全截断

### CAP-04 首页阅读层级

#### Requirement

首页首屏保留现有品牌和导航，但减少强居中、强制断行和低对比辅助文字造成的视觉漂移。

#### Scenario

- Given 用户在桌面或移动端打开首页
- When 首屏完成渲染
- Then 标题和说明保持清晰的左对齐扫描路径
- And 辅助文字对比度满足小字号可读要求
- And 首屏仍能看到下一段内容的提示
