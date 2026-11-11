# Shopify 发布完整性与价格语义

## 目标

修复 Shopify 发布把 1688 供货价当销售价、丢失 SKU 变体与媒体素材的问题。网页发布和 AI 助手发布必须共用同一个发布服务，避免两套 Payload 继续分叉。

## 价格语义

- `Product.price` 表示商品来源供货参考价，不直接作为 Shopify 售价。
- `ProductVariant.price` 表示可发布的销售价格。
- 没有启用 SKU，或任一启用 SKU 缺少大于 0 的售价时，禁止发布。
- 运营毛利模型继续使用 SKU 售价与 SKU 成本；只有缺少 SKU 成本时才回退到供货参考价。

## 能力点

### CAP-01 完整 Shopify 草稿商品

#### Requirement

发布 Payload 必须包含 Listing 标题、描述、五点卖点、SEO Metafields、商品主图、变体图片、SKU、变体选项、售价、库存数量和条形码。

#### Scenario

- Given 用户拥有已通过合规审查的 Listing
- And 商品拥有一个或多个启用 SKU
- When 用户发布到 Shopify
- Then Shopify Payload 包含 Listing 内容和全部启用 SKU
- And 商品图片使用可通过公网访问的绝对 URL
- And 发布结果返回变体数与图片数

### CAP-02 发布前完整性校验

#### Requirement

发布前必须验证 SKU 售价、属性数量与媒体地址。不能猜测售价，也不能静默丢弃关键字段。

#### Scenario

- Given 商品没有启用 SKU
- When 用户尝试发布
- Then 返回 409 并提示先创建启用 SKU

- Given 某个启用 SKU 没有售价
- When 用户尝试发布
- Then 返回 409 并指出对应 SKU

- Given SKU 属性超过 Shopify 支持的三个选项
- When 用户尝试发布
- Then 返回 409 并提示精简属性

### CAP-03 单一发布服务

#### Requirement

`POST /api/v1/shopify/push` 和 Agent `push_to_shopify` 必须调用同一个服务完成 Payload 构建、供应商请求、发布记录和 Listing 状态更新。

#### Scenario

- Given 同一条 Listing
- When 分别通过网页和 Agent 发布到不同幂等键
- Then 两次请求使用相同字段结构与价格来源
- And Agent 不再维护另一套简化 Payload

### CAP-04 前端价格与发布提示

#### Requirement

商品录入和详情页必须把 `Product.price` 标为供货/采购参考价，发布失败时必须明确提示补齐启用 SKU。

#### Scenario

- Given 用户手动录入商品
- Then 字段显示为“采购/供货价”
- When 发布缺少 SKU 的 Listing
- Then 页面展示后端返回的补齐 SKU 提示

## 非目标

- 本轮不实现 Shopify 商品更新和双向库存同步。
- 本轮不实现 Amazon、Temu、SHEIN 发布。
- 本轮不实现商品图片上传到 Shopify CDN 后的变体图片 ID 绑定；先将全部商品与变体图片加入商品媒体库。
