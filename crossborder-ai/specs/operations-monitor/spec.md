# Operations Monitor and Replenishment

## 目标

把价格、成本、库存、毛利和补货统一到 SKU 级运营监控中。系统通过快照和规则生成可确认的预警，并允许 Agent 与定时任务复用同一套扫描逻辑。

## 能力点

### CAP-01 SKU 快照

#### Requirement

每次扫描必须记录当前用户每个 SKU 的售价、成本、库存、日均销量和毛利率。

#### Scenario

- Given 用户拥有多个 SKU
- When 执行运营扫描
- Then 每个 SKU 生成一条快照
- And 快照包含当时的价格、库存和毛利数据

#### Scenario

- Given 商品保留 1688 来源链接
- When 用户主动同步供货价
- Then 系统通过 Just One 优先链路刷新商品供货价
- And 未手工填写成本的 SKU 使用新供货价补齐成本
- And 单个商品抓取失败不阻断其他商品同步

### CAP-02 补货模型

#### Requirement

补货模型必须根据日均销量、备货周期、安全库存天数和当前库存计算库存覆盖天数、补货点和建议补货量。

#### Scenario

- Given SKU 日销 2 件、备货 14 天、安全库存 3 天、当前库存 20 件
- When 计算补货计划
- Then 库存覆盖 10 天
- And 补货点为 34 件
- And 状态为需要补货

#### Scenario

- Given SKU 没有日均销量
- When 计算补货计划
- Then 不伪造销量预测
- And 返回数据不足状态

### CAP-03 预警规则

#### Requirement

系统必须支持缺货、低库存、低毛利、缺成本、Listing 合规阻断和缺主图预警。重复扫描不得创建重复未处理预警。

#### Scenario

- Given 同一低库存问题连续扫描两次
- When 两次扫描完成
- Then 只保留一个未处理预警

#### Scenario

- Given SKU 补货后库存恢复
- When 再次扫描
- Then 原有低库存预警自动标记为已解决

### CAP-04 预警确认

#### Requirement

用户可以确认自己的预警。其他用户的预警统一返回 404。

#### Scenario

- Given 用户拥有未处理预警
- When 用户确认预警
- Then 状态变为 acknowledged

### CAP-05 运营设置

#### Requirement

用户可设置目标毛利率、低库存天数、备货周期、安全库存天数、平台费率和单件运费。

#### Scenario

- Given 用户保存新的目标毛利率
- When 再次执行扫描
- Then 低毛利判断使用新阈值

### CAP-06 Agent 与调度

#### Requirement

Agent 和每日调度必须调用同一运营扫描服务。Agent 可回答最近需要处理的商品。

#### Scenario

- Given 用户说“看看最近哪些商品要处理”
- When Agent 调用 monitor_products
- Then 返回 SKU、预警和补货摘要
