# 移动端店铺添加与渠道连接

> 状态：已确认实施
> 日期：2026-11-23
> 范围：店铺列表、添加店铺入口、Shopify/Amazon/Temu 授权和 Android 安全区。

## STORE-01 添加店铺入口

### Requirement

首页店铺选择器和账号页都必须提供“添加店铺”入口。
店铺页展示当前工作区已连接店铺，并提供 Shopify、Amazon、Temu 三种连接方式。

### Scenario

- Given 用户首次登录且没有店铺
- When 用户打开店铺选择器或账号页
- Then 可以进入“店铺与渠道”
- And 可以选择平台发起授权

## STORE-02 平台授权

### Requirement

- Shopify 接受裸子域或完整 `.myshopify.com` 域名，并获取真实 OAuth URL。
- Amazon 获取 Seller Central 授权 URL。
- Temu 获取默认区域授权 URL。
- 授权在系统浏览器完成，返回 App 后刷新店铺列表。
- 平台未配置或授权 URL 无效时必须显示真实错误，不伪造连接成功。

## SAFE-01 Android 顶部安全区

### Requirement

带 `ModalScreenHeader` 的页面根 `SafeAreaView` 不得包含顶部安全区。
标题栏是唯一消费状态栏高度的组件，避免华为等长状态栏设备出现双倍空白。

## 验收

- 店铺 provider 和域名解析有单元测试。
- 375px 与 390px 检查店铺页、添加入口、授权错误状态。
- 执行结果页在 Android 预览中顶部无重复留白。
- 移动端测试、TypeScript、ESLint 和 Expo Web 构建通过。
