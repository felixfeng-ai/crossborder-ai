# 移动端原生法律正文

> 状态：已确认实施
> 日期：2026-11-23
> 范围：法律中心列表、七份协议正文、登录协议入口和离线阅读。

## LEGAL-NATIVE-01 原生正文页

### Requirement

点击任一协议后进入 App 内 `/legal/[slug]` 页面，不打开浏览器。
页面展示文档标题、版本、生效日期、章节、段落和必要的项目列表。

### Scenario

- Given 用户位于法律与隐私中心
- When 用户点击《隐私政策》
- Then App 原生页面展示完整隐私政策
- And 返回操作回到法律中心

## LEGAL-NATIVE-02 内容同源

### Requirement

移动端正文由 Web 法务源机械生成，不手工改写。版本和生效日期必须与
`frontend/src/lib/legal.ts` 一致。

### Scenario

- Given Web 法务文档更新版本
- When 执行移动端法务内容生成脚本
- Then App 内正文和版本同步更新

## LEGAL-NATIVE-03 登录入口

### Requirement

登录页和注册页的协议入口必须导航到 App 内正文页，不调用 Web URL。

### Scenario

- Given 用户尚未登录
- When 用户点击《AI 使用说明》
- Then App 内直接展示 AI 使用说明

## LEGAL-NATIVE-04 联系与举报

### Requirement

正文底部提供单一邮件操作，用于账号、隐私、数据、安全和举报请求。
邮件操作使用系统邮件客户端，不离开当前 App 去展示网页。

## 验收

- 七份文档均可在离线状态阅读。
- 正文长页在 375px 和 390px 无横向溢出。
- 移动端测试、TypeScript、ESLint 和 Expo Web 构建通过。
