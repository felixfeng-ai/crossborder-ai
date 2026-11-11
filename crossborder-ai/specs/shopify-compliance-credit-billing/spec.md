# Shopify 合规 Webhook 与积分计费

## 目标

补齐 Shopify 公开应用必需的三个隐私 Webhook，并把当前“只有余额、没有流水和月度规则”的积分体系升级为可审计、可重置、可解释的计费底座。

## CAP-01 Shopify 强制隐私 Webhook

### Requirement

系统必须接收并验证以下 Webhook：

- `customers/data_request`
- `customers/redact`
- `shop/redact`

每个请求使用原始请求体和 `X-Shopify-Hmac-Sha256` 做 HMAC-SHA256 验证；缺少密钥、签名错误、Topic 不匹配时不得处理。

### Scenario

- Given Shopify 使用正确 secret 签名请求
- When 调用对应 Webhook
- Then 返回 200，并记录不含客户 PII 的处理事件

- Given 请求签名错误
- When 调用 Webhook
- Then 返回 401，且不产生业务副作用

- Given 相同 `X-Shopify-Webhook-Id` 重复投递
- When 再次接收
- Then 不重复执行删除，返回幂等成功

### 数据删除边界

- `customers/data_request`：平台不持久化客户姓名、邮箱、电话、地址，只记录已处理。
- `customers/redact`：同样不存储客户 PII，只记录已处理。
- `shop/redact`：删除对应 Shopify 渠道 Token 与该渠道发布记录。

## CAP-02 积分流水

### Requirement

所有积分增加、扣减和月度重置都必须写 `credit_transactions`，记录功能、变动值、变动后余额、资源标识和说明。

### Scenario

- Given 用户成功执行扣费功能
- When 扣减积分
- Then 余额原子更新
- And 生成一条负向积分流水

- Given 管理员开通套餐
- When 设置套餐额度
- Then 生成一条正向额度流水

## CAP-03 月度额度

### Requirement

Free、Standard、Professional 均按自然月获得对应额度。登录用户在当前自然月首次访问额度接口时自动补充；后台每日任务也会执行，避免仅登录不触发。

本轮保留现有额度数值：

- Free：30
- Standard：99,999
- Professional：99,999

价格是否调整不纳入本轮代码决策。

## CAP-04 AI 图片计费

### Requirement

Professional 图片生成按输出张数扣积分，每张 1 积分。成功生成后才扣费；失败不扣费。必须防止同一任务重复扣费。

### Scenario

- Given 用户有 5 积分并生成 2 张图片
- When 任务完成
- Then 余额变为 3，并写入图片任务流水

- Given 生成任务失败
- Then 不扣除积分

## CAP-05 浏览器与 Agent 一致性

高成本功能的计费原因和资源 ID 必须统一写入流水，不允许只扣余额不记录用途。

## 验收

- 新测试先失败后通过
- 后端全量测试通过
- Alembic 迁移可在空 SQLite 和 PostgreSQL CI 升级
- 生产部署后三个 Webhook 地址可访问
