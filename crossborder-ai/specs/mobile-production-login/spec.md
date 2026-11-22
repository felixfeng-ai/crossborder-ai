# 移动端真实登录内测

> 状态：已实现  
> 日期：2026-11-22  
> 范围：生产移动 API、EAS preview 构建和 PostgreSQL 迁移兼容。

## LOGIN-01 生产移动 API

### Requirement

`https://veyaship.com/api/mobile/v1/bootstrap` 在未登录时返回 `401`，
不再返回 `404`；真实注册和登录后返回用户、工作区和合同版本。

### Scenario

- Given 内测用户安装 `preview` APK
- When 用户注册或登录
- Then App 获取有效会话并进入 Agent 首页
- And bootstrap 返回至少一个个人工作区

## LOGIN-02 EAS preview

### Requirement

Android `preview` profile 使用 `https://veyaship.com` 作为 API，
关闭固定预览数据，并通过 HTTPS 发布真实 APK。

### Scenario

- Given EAS 执行 `preview` profile
- When App 读取构建配置
- Then `extra.apiUrl` 为生产 HTTPS 地址
- And `extra.previewMode` 为 `false`

## LOGIN-03 PostgreSQL 迁移兼容

### Requirement

布尔列默认值必须编译为 PostgreSQL `true/false`，不能使用 SQLite 的 `1/0`。

### Scenario

- Given PostgreSQL 从 `076` 升级到 `077`
- When 创建自动化偏好表
- Then 布尔默认值可正常执行且迁移到达 `081`

## 验收

- 生产注册、登录和 bootstrap 实测通过。
- 数据库迁移到达 head，健康检查通过。
- EAS Android `preview` APK 构建成功并提供安装地址。
