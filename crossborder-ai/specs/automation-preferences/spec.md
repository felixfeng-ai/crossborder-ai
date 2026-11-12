# 用户自动化开关

## 目标

允许用户控制会影响其店铺数据和版本状态的业务自动化，同时保留系统任务队列、
计费、数据保留和外部 Webhook 的持续运行。

## 能力一：用户级自动化配置

### Requirement

系统必须为每个用户保存四项业务自动化开关，并在没有配置时保持现有自动化默认行为。

### Scenario: 读取默认配置

- Given 付费用户尚未保存自动化设置
- When 打开自动化设置
- Then 四项开关默认开启
- And 返回最近执行状态和计划说明

### Scenario: 保存开关

- Given 用户是 Standard 或 Professional
- When 修改一个或多个业务自动化开关
- Then 配置只影响当前用户
- And 后续调度任务读取最新配置

### Scenario: Free 用户

- Given Free 用户打开自动化设置
- When 尝试开启付费自动化
- Then 开关显示不可用和升级说明
- And 后端拒绝开启请求

## 能力二：按用户跳过调度任务

### Requirement

每日巡检、每日运营监控、Shopify 自动同步和 A/B 自动暂停必须遵守用户开关。

### Scenario: 关闭自动巡检

- Given 用户关闭每日整店巡检
- When 02:30 调度任务运行
- Then 跳过该用户
- And 其他开启用户仍正常执行
- And 手动巡检入口仍可使用

### Scenario: 关闭运营监控

- Given 用户关闭每日运营监控
- When 02:45 调度任务运行
- Then 不为该用户生成新快照和预警

### Scenario: 关闭 Shopify 自动同步

- Given 用户关闭 Shopify 自动同步
- When 六小时同步任务运行
- Then 跳过该用户所有 Shopify 店铺
- And 手动同步按钮仍可使用

### Scenario: 关闭 A/B 自动暂停

- Given 用户关闭 A/B 自动暂停
- When 导入效果数据
- Then 保存真实指标
- And 不修改文案 performance_status
- And 优化页面仍可展示建议

## 能力三：执行状态

### Requirement

每个业务自动化应显示最近一次执行时间、结果和错误，不得显示伪造状态。

### Scenario: 成功与失败

- Given 自动任务执行完成
- When 用户打开自动化设置
- Then 显示 success 或 failed
- And 失败时显示真实错误摘要

## 验收标准

- 四项配置有数据库迁移和 API 隔离测试。
- Free 用户不能开启付费自动化。
- 调度器按用户跳过关闭项，系统级任务不受影响。
- 手动操作入口不依赖自动化开关。
- 设置页在 1440px 和 390px 下完成真实截图验收。
