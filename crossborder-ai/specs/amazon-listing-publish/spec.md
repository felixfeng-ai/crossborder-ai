# Amazon SP-API Listing 发布

## 目标

在现有 Amazon SP-API 授权连接基础上，支持 Listing 预览校验和正式发布。
发布能力必须依赖真实卖家授权、Listing 权限和商品数据，不生成虚假成功状态。

## Requirement

用户可以把活动绑定的商品、Listing 和一个 Amazon 卖家连接发布到指定站点。

### Scenario: 发布前校验

- Given 用户有启用的 Amazon 卖家连接和 Marketplace ID
- And 商品至少有一个启用且带价格和 SKU 的变体
- And Listing 已通过合规检查
- When 用户执行预览校验
- Then 系统调用 Listings Items API 的 VALIDATION_PREVIEW
- And 返回 Amazon 校验问题和 SKU

### Scenario: 正式发布

- Given 预览校验没有阻断错误
- When 用户确认发布
- Then 系统向 Listings Items API PUT 商品数据
- And 保存 Publication、活动发布记录、外部 SKU 和 ACK 状态
- And 重复幂等请求返回已有记录

### Scenario: 权限或数据错误

- Given Amazon 应用缺少 Listing 权限或商品属性不完整
- When 调用发布接口
- Then 返回真实错误原因
- And 不把状态标为 completed

### Scenario: 能力状态

- Given Amazon SP-API 已配置
- Then 平台能力接口显示 auth_supported=true
- And publish_supported=true
- And reason 明确要求 Listings Items 权限

## 验收标准

- 授权、预览和发布均不在日志中暴露 Refresh Token。
- Amazon 发布记录与 Shopify 一样使用统一 Publication 和幂等键。
- 单元测试覆盖预览请求、成功响应、权限错误和跨用户隔离。
- 营销页面展示 Amazon 发布可选连接、Marketplace 和真实状态。
