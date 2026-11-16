# Selection Report Normalization

## 目标

消除 LLM 输出字段漂移导致候选商品空白的问题，并区分品类分析与选品推荐。

## 能力点

### CAP-01 字段归一化

#### Requirement

后端必须把 `name/title/product_name/商品名`、`price_usd/suggested_price_usd/价格美元`
等常见别名统一成前端 `ProductCandidate` 契约。

#### Scenario

- Given LLM 返回 `title` 和 `price_usd`
- When 生成选品报告
- Then 前端收到 `name` 和 `suggested_price_usd`

### CAP-02 品类模式边界

#### Requirement

`analyze_category` 是市场分析，不允许展示竞品候选商品列表；服务端必须强制
`products=[]`。

#### Scenario

- Given 品类分析模型擅自返回 products
- Then 服务端清空 candidates
- And 前端不显示候选商品卡片

### CAP-03 历史兼容

#### Requirement

前端必须兼容已经落库的异形字段，过滤没有商品名的空对象。

#### Scenario

- Given 历史报告使用中文键或 `title/price_usd`
- Then 卡片能显示标准商品名称和价格
