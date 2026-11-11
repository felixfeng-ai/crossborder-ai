# Shopify 运营数据同步

## 目标

让 SKU 运营模型可以主动从已绑定的 Shopify 店铺同步最近订单销量和已发布商品库存，减少人工维护日均销量与库存。

## 能力点

### CAP-01 订单销量聚合

#### Requirement

系统按当前用户和 Shopify 渠道读取最近 N 天订单，按 SKU 汇总有效行项目数量，并计算日均销量。

#### Scenario

- Given 用户绑定 Shopify 店铺并拥有 SKU
- When 用户执行运营数据同步
- Then 每个匹配 SKU 的 `daily_sales_rate` 更新为最近订单数量除以天数
- And 未匹配订单 SKU 不影响任何商品

### CAP-02 已发布商品库存同步

#### Requirement

系统只读取当前渠道通过本平台发布且有 `external_product_id` 的 Shopify 商品，不扫描无关店铺商品。

#### Scenario

- Given 渠道存在已完成发布记录
- When 执行同步
- Then 系统读取这些 Shopify 商品的 Variants
- And 按 SKU 匹配本地启用变体并更新库存数量
- And 不覆盖本地售价和成本

### CAP-03 用户隔离与可观测结果

#### Requirement

同步必须校验渠道归属，返回订单数、更新 SKU 数、库存更新数、未匹配 SKU 和失败信息。

#### Scenario

- Given 用户 A 的渠道
- When 用户 B 发起同步
- Then 返回 404

- Given 同步成功
- Then 返回 scopes、days、orders_scanned、sales_rate_updates、stock_updates、unmatched_skus

### CAP-04 运营页入口

#### Requirement

运营监控页提供 Shopify 渠道选择和“同步 Shopify 数据”操作，成功后刷新运营概览与预警。
