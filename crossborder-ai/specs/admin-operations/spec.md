# 管理员运营后台与真实用户监控

## 目标

在保留现有卖家工作台的前提下，新增独立管理员后台，补齐套餐版本管理、用户反馈、页面性能监控和访问统计。所有管理员能力必须有后端权限校验和审计记录。

## Requirement 1：独立管理员入口

### Scenario：管理员访问后台

- Given 当前用户 `is_admin=true`
- When 用户访问 `/admin/overview`
- Then 页面使用独立管理员布局，不显示卖家工作台侧边栏
- And 管理员可进入总览、访问分析、性能、套餐、订单、反馈和审计页面

### Scenario：普通用户访问后台

- Given 当前用户不是管理员
- When 用户访问 `/admin` 或任一管理员 API
- Then 前端跳转到卖家工作台
- And 后端返回 `403`

## Requirement 2：页面访问与 Web Vitals 采集

### Scenario：页面访问产生 PV 和 UV

- Given 匿名访问者打开公开页面
- When 页面完成一次路由访问
- Then 系统记录一条 `page_view`
- And 同一访问者当天再次访问同一页面产生新的 PV，但不增加 UV

### Scenario：浏览器性能指标上报

- Given 浏览器产生 LCP、FCP、INP、CLS 或 TTFB
- When 指标达到可上报状态
- Then 前端批量发送指标和页面上下文
- And 后端只接受白名单指标、合法评级和有限长度字段

### Scenario：管理员查看真实指标

- Given 管理员选择时间范围
- When 打开访问分析或性能页面
- Then 返回 PV、UV、会话、页面排行、设备和国家分组
- And 返回 LCP、FCP、INP、CLS、TTFB 的 p75 与样本数

## Requirement 3：用户反馈

### Scenario：用户提交反馈

- Given 已登录用户在使用工作台
- When 用户提交问题类型、标题和描述
- Then 系统保存用户、页面、浏览器、视口和请求 ID
- And 用户可在“我的反馈”中查看状态

### Scenario：管理员处理反馈

- Given 管理员打开反馈收件箱
- When 管理员筛选、分配或更新状态
- Then 状态和内部备注持久化
- And 操作写入管理员审计记录

## Requirement 4：套餐版本管理

### Scenario：管理员发布新套餐版本

- Given 管理员打开套餐管理
- When 管理员基于现有套餐创建新版本并填写价格、积分和有效期
- Then 系统先保存草稿
- And 发布后旧版本自动归档，新版本成为唯一公开版本

### Scenario：用户读取最新套餐

- Given 存在已发布套餐版本
- When 用户打开定价或账单页面
- Then `/api/v1/billing/plans` 返回最新已发布版本
- And 升级订单保存价格、积分和周期快照

### Scenario：历史订单不漂移

- Given 管理员修改并发布了新套餐价格
- When 查询历史订单
- Then 历史订单金额和积分保持原值

## Requirement 5：运营总览与审计

### Scenario：管理员查看运营状态

- Given 管理员打开总览
- When 数据加载完成
- Then 显示用户、付费用户、套餐分布、收入、待审核订单、未处理反馈、PV、UV 和性能摘要

### Scenario：管理员修改配置

- Given 管理员执行套餐发布或反馈状态修改
- When 后端完成操作
- Then `admin_audit_logs` 记录操作者、对象、动作、变更前后摘要和时间

## 非目标

- 不在本阶段引入全站 SSR。
- 不在本阶段引入 ClickHouse；以 PostgreSQL 原始事件和查询聚合为主。
- 不在本阶段建设多层级员工权限，只有管理员和非管理员。
- 不保存原始 IP、完整 User-Agent 或客户个人数据到分析表。

## 验收

- 管理员和普通用户权限测试通过。
- PV、UV、Web Vitals 聚合测试通过。
- 反馈状态流转和管理员读取测试通过。
- 套餐版本发布、公开读取和历史快照测试通过。
- 前端类型检查、单测、构建和包预算通过。
- 真实浏览器验证管理员桌面与 390px 移动端页面。
