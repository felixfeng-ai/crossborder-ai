# 套餐钱包、有效期与超额积分

## 目标

把当前单一 `credits` 余额升级为“套餐月额度 + 购买积分”双钱包，增加 30 天套餐有效期、超额积分包、分析类额度和自动巡检次数，同时保证老用户余额不丢失。

## 套餐目录

| 套餐 | 价格 | 月额度 | 有效期 |
|---|---:|---:|---:|
| Free | ¥0 | 30 | 自然月 |
| Standard | ¥99 | 800 | 30 天 |
| Professional | ¥249 | 2,000 | 30 天 |

价格和额度集中配置，不在各路由散落硬编码。

## CAP-01 双钱包与扣费顺序

### Requirement

用户钱包拆分为：

- `plan_credits`：套餐期额度，按月发放、不可跨期保留。
- `purchased_credits`：购买或补偿积分，不因套餐月度重置清零。

扣费时先扣 `plan_credits`，不足部分再扣 `purchased_credits`。`User.credits` 保留为总额兼容字段。

### Scenario

- Given 用户有 3 套餐积分和 10 购买积分
- When 扣 5 积分
- Then 套餐积分变为 0，购买积分变为 8，总额为 8

- Given 购买积分余额为 8
- When 新自然月开始
- Then 套餐额度重置，但购买积分仍为 8

## CAP-02 套餐有效期

### Requirement

管理员开通 Standard/Professional 时创建 30 天有效订阅。到期任务将用户降级为 Free、套餐钱包重置为 Free 30，但保留购买积分。

### Scenario

- Given 用户 Standard 订阅已过期
- When 每日订阅检查执行
- Then 用户变为 Free，订阅状态为 expired
- And 购买积分保持不变

## CAP-03 超额积分包

### Requirement

用户可提交积分包购买申请，管理员确认收款后增加 `purchased_credits`。订单号作为幂等依据，重复审核不得重复到账。

### Scenario

- Given 管理员批准一笔 200 积分购买订单
- Then 用户购买积分增加 200
- And 生成正向积分流水
- And 重复批准同一订单失败

## CAP-04 分析类额度

### Requirement

AI 品类分析和 AI Insights 每自然月各包含 10 次。超出后每次扣 1 积分。

## CAP-05 自动巡检与手动巡检

### Requirement

- 每日自动巡检仅对 Standard/Professional 有效用户执行，套餐内包含，不额外扣积分。
- 手动巡检 Free 每次 1 积分；Standard 每月包含 10 次；Professional 每月包含 20 次；超出后每次 1 积分。

## 验收

- 老数据迁移后总额不变
- 月度重置不清空购买积分
- 套餐到期保留购买积分
- 积分包批准幂等
- 分析额度和手动巡检计数按自然月重置
- 后端全量测试、前端测试、TypeScript、生产构建通过
