# Shopify 强制隐私 Webhook 配置

生产后端已经提供以下 HTTPS 地址：

```text
https://veyaship.com/api/v1/shopify/webhooks/customers/data_request
https://veyaship.com/api/v1/shopify/webhooks/customers/redact
https://veyaship.com/api/v1/shopify/webhooks/shop/redact
```

## 配置方式

优先使用 Shopify App 配置中的 `compliance_topics`。参考项目根目录的
`shopify.app.toml.example`，复制为 `shopify.app.toml` 后填写真实 `client_id`，
再通过 Shopify CLI 部署配置。

如果当前应用仍由 Partner Dashboard 管理，则在 App 的 Webhook 配置中分别登记
上述三个地址，Topic 必须与路径一致。

## 验证要求

- 使用 `X-Shopify-Hmac-Sha256` 原始请求体验签
- 缺少 secret 时 fail closed
- 相同 `X-Shopify-Webhook-Id` 幂等处理
- 不持久化客户姓名、邮箱、电话、地址或完整 payload
- `shop/redact` 删除对应店铺 Token 和该渠道发布记录

Shopify 会发送测试通知。首次配置后应在 `shopify_compliance_events` 表中看到
`processed` 记录。
