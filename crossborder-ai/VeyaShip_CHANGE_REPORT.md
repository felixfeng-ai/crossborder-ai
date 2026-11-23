# VeyaShip 变更报告

本文件统一记录 App、Web 与后端的生产变更，版本按时间倒序追加。

# Web 发布记录

## v1.2.0 - 2026-11-23

### 交付主题

Web 补齐 App 的 Agent 工作区、任务确认、通知、多模态输入和安全控制。

### 业务变化

- Web 顶部支持工作区切换；商品、任务、通知、店铺和 Agent 数据跟随当前工作区。
- 新增“今日 Agent”，展示待决定、自动执行、关注、结转任务和最近工作流。
- 新增任务详情与动作确认，支持动作预览、工作项版本、幂等提交和执行记录。
- 顶栏新增通知未读数；新增通知中心、全部已读、单条已读和通知偏好。
- “今日 Agent”支持文字、商品链接、订单号、图片、浏览器录音和语音转写。
- 账号安全支持真实头像、上传头像、Agent 急停/恢复和退出全部设备。
- 新增 Shopify、Amazon、Temu 统一店铺与渠道页。
- 素材中心新增工作区图片分类、替换和删除，失败时保留原素材。

### 技术变化

- 所有 Web API 请求自动注入 `X-Workspace-Id`，工作区选择持久化并支持恢复。
- 登录、注册、退出和 401 会清空工作区状态与 React Query 缓存，避免跨账号数据串入。
- Web 复用 App 的 `bootstrap`、`daily-plan`、`timeline`、`work-items`、
  `notifications`、`agent-control`、`agent-turns` 和素材运行面。
- 新增 `specs/web-app-parity/spec.md`，记录跨端同步能力与非目标。
- 查询客户端、会话清理和移动运行面按需加载，营销首页首屏预算保持通过。

### 验证

- TypeScript 类型检查：通过
- 前端单元测试：`63 files / 211 tests passed`
- 新增纯逻辑模块语句覆盖率：`80.39% - 100%`；页面与 API 胶水层由真实浏览器验收覆盖
- 后端相关回归：`41 passed`
- Vite 生产构建：通过
- 首屏包体积门禁：`247 KB gzip`，通过
- 真实页面检查：`1440 × 1000` 和 `390 × 844`
- 工作区、今日 Agent、通知、通知偏好、统一店铺、账号安全和素材分类页面可渲染
- Agent 空状态与输入可提交状态正确，未提交真实计费 Agent 任务

### 当前边界

- 自动化验收未触发真实 Agent 提交、头像上传或店铺 OAuth，避免产生计费或外部授权副作用。
- 浏览器录音权限提示与真实麦克风转写需要在实际设备上由用户授权后验证。
- 本轮为 Web-only 改动，不要求重新生成 Android APK。

## v1.1.4 - 2026-11-23

### 交付主题

Web 首页与教程正式补充 App 随身 Agent 模式。

### 业务变化

- 首页明确区分 Web 工作台与手机 App：复杂配置留在 Web，手机承接今日计划、订单、客服、通知和 Agent 待办。
- 首页新增“App 模式”说明区，提供二维码下载、内测版本和随身 Agent 工作方式说明。
- 教程新增 App 模式说明，并把同一工作区、语音或拍照、任务回传和手机待办加入“问 AI”步骤。
- 登录后的“进入应用”改为“进入 Web 工作台”，避免与手机 App 混淆。

### 技术变化

- 新增 `LANDING_APP_MODE_POINTS` 与 `TUTORIAL_APP_MODE_POINTS`，首页和教程使用同一组 App 能力事实。
- `DownloadAppDialog` 支持自定义触发文案、样式和按钮层级，可复用于首页、教程和工作台顶栏。
- 首页与教程继续复用石墨琥珀设计系统、Lucide 图标和现有响应式结构，没有引入第二套视觉语言。

### 验证

- TypeScript 类型检查：通过
- 前端单元测试：`56 files / 190 tests passed`
- Vite 生产构建：通过
- 首屏包体积门禁：`245 KB gzip`，通过
- `1440 × 1000`、`768 × 1024`、`390 × 844` 首页与教程真实页面检查通过
- 手机端下载弹层完整展示二维码、Build `16` 和直接下载入口，无横向溢出

### 当前边界

- Web 首页与教程展示的是 Android 内测能力，iOS 版本仍在准备中。
- 本轮验证了浏览器下载弹层和响应式页面，未在实体手机上重新安装安装包。

## v1.1.3 - 2026-11-23

### 交付主题

Web 内测二维码与 Android Build 16 同步。

### 业务变化

- Web 顶栏“下载 App”弹层改为下载 Android `1.0.0 (16)`。
- 二维码和“直接下载 APK”入口继续共用同一个安装包地址。
- 新安装包包含生产移动 API、切换账号隔离、用户头像和真实请求错误提示。

### 技术变化

- 下载地址切换为 EAS Build `5cda0584-1b72-4c81-81de-a09a47dc3b46` 的 APK。
- 安装包绑定移动端提交 `ef7774d948589f7ac64da6ade060992a808ab541`。
- `DEFAULT_MOBILE_APP_DOWNLOAD_URL`、`.env.production` 和 `.env.example`
  同步更新，避免默认值与生产覆盖值不一致。

### 验证

- EAS Android Build `16`：`FINISHED`
- APK 地址返回 `200`，大小 `150,749,001` 字节
- TypeScript 类型检查：通过
- 前端单元测试：`56 files / 188 tests passed`
- Vite 生产构建：通过
- 首屏包体积门禁：`225 KB gzip`，通过

### 当前边界

- EAS 构建产物计划于 `2026-12-07` 过期，正式分发前仍需迁移到官网稳定 CDN。
- 本轮验证了安装包下载链路，未在实体 Android 设备上执行安装。

## v1.1.2 - 2026-11-23

### 交付主题

Web App 下载二维码同步最新 Android 内测包。

### 业务变化

- Web 顶栏“下载 App”弹层改为下载 Android `1.0.0 (14)`。
- 二维码和“直接下载 APK”入口使用同一个新安装包地址。

### 技术变化

- 默认下载地址和 `VITE_MOBILE_APP_DOWNLOAD_URL` 更新为 EAS Build `1b4d7cf9-e21b-408c-982e-94077a5031c9` 的 APK。
- 新安装包基于移动端提交 `6a409ba`，包含登录键盘定位、光标颜色和仅返回 Access Token 的会话兼容修复。

### 验证

- EAS Android Build `14`：`FINISHED`
- APK 地址返回 `200`，大小 `150,670,255` 字节
- TypeScript 类型检查：通过
- 前端单元测试：`56 files / 188 tests passed`
- Vite 生产构建：通过
- 首屏包体积门禁：`225 KB gzip`，通过
- `eslint`：未执行；仓库当前未安装该开发依赖，CI 也未配置 lint 步骤

### 当前边界

- EAS 构建产物仍属于内测临时分发地址，到期前需要迁移到官网稳定 CDN。
- 新构建完成后仍需显式更新 Web 下载配置；EAS 不会自动修改 Web 二维码。

## v1.1.1 - 2026-11-23

### 交付主题

Web 品牌标记与 App 统一。

### 业务变化

- 侧栏、登录注册页、公开页面、法务页和管理端统一使用与 App 相同的品牌标记。
- Logo 恢复黑圆、白色 V、白色底线和右上暖金星点。

### 技术变化

- `BrandMark` 改为 `96 x 96` 矢量画布。
- V、底线和星点复用 App `AgentAvatar` 的几何比例与颜色。
- 侧栏、登录、公开页、法务页和下载弹层移除旧方形描边，并让圆标填满各自容器。

### 验证

- Web 桌面与手机视口视觉检查通过
- TypeScript、测试、生产构建和包体积门禁通过

## v1.1.0 - 2026-11-23

### 交付主题

Web 顶栏 App 下载入口与二维码体验。

### 业务变化

- Web 工作台顶栏新增“下载 App”入口。
- 下载弹层提供二维码和直接下载 APK 两种方式。
- 弹层展示 Android 内测版本、安装说明和 iOS 准备状态。

### 技术变化

- 使用 `qrcode.react` 生成与下载地址一致的二维码。
- 下载地址通过 `VITE_MOBILE_APP_DOWNLOAD_URL` 配置，并校验为 HTTPS。
- Vite 本地代理支持切换到生产 HTTPS API，便于真实登录态验收。

### 验证

- APK 地址检查：`200`，约 `150.9 MB`
- 前端全量：`56 files / 190 tests passed`
- TypeScript 类型检查：通过
- Vite 生产构建：通过
- 首屏包体积门禁：`225 KB gzip`，通过
- 桌面与手机视口：二维码、直接下载、关闭和焦点回退正常

### 当前边界

- 当前二维码指向 EAS 内测产物，正式发布前需替换为官网稳定 CDN 地址。
- 当前只提供 Android APK，iOS 版本仍待发布。

# 移动端发布记录

## v3.14.1 - 2026-11-23

### 交付主题

移动后端生产上线与 Android Build 16 真实内测包。

### 业务变化

- 真实登录、工作区、店铺、头像和 Agent 工作流已具备生产移动 API。
- 切换账号会清理旧账号缓存与工作区状态，不再继续展示上一账号内容。
- 用户可以在账号页选择头像，首页问候区同步显示新头像。
- 断网、登录失效、接口版本不一致和服务端异常会显示不同错误原因。

### 技术变化

- 发布提交 `ef7774d948589f7ac64da6ade060992a808ab541` 已包含移动运行面、
  头像迁移 `082_user_avatar`、并发首次工作区修复和部署前迁移。
- EAS Build `5cda0584-1b72-4c81-81de-a09a47dc3b46` 使用提交 `ef7774d`
  构建，版本为 `1.0.0 (16)`。
- APK 下载地址：
  `https://expo.dev/artifacts/eas/bKteV0OXlh1tOtesB0X4C3AEb3qz5P64R0TRCu3FnI8.apk`。

### 验证

- 生产部署 `#127`：成功
- CI `#113`：SQLite、PostgreSQL Production Gate、前端构建门禁全部通过
- 后端全量：`1050 passed, 4 skipped`
- 移动端：`24 files / 89 tests passed`
- 覆盖率：语句 `96.26%`、分支 `91.08%`
- 生产 `/health`：`200`，数据库连接正常
- 生产移动 `bootstrap` 和头像接口：`401`，确认路由存在且鉴权生效
- `npm run check:api`：通过
- EAS Android Build `16`：`FINISHED`
- APK 地址返回 `200`，大小 `150,749,001` 字节

### 当前边界

- 当前仅提供 Android 内测包，iOS 版本仍在准备中。
- EAS 临时安装包计划于 `2026-12-07` 过期，需要及时迁移到稳定 CDN。
- 本轮未在实体设备上执行安装后的完整人工回归，设备侧体验仍需内测用户验证。

## v3.14.0 - 2026-11-23

### 交付主题

切换账号会话隔离、用户头像和移动接口错误文案。

### 业务变化

- 切换账号或退出登录会清空旧账号的查询缓存、工作区、店铺选择和输入草稿。
- 登录成功后先清理旧会话运行时，再保存新账号并进入首页。
- 账号页头像支持点击选择、方形裁切和上传，首页问候头像同步更新。
- 发送文字、图片和语音失败时显示真实原因，不再统一提示“网络恢复后重试”。

### 技术变化

- 新增 `clearUserRuntimeState`，按取消查询、清缓存、清输入草稿、清工作区顺序执行。
- 退出登录改为本地凭据先失效，再异步撤销服务端会话。
- 用户模型新增头像存储键和更新时间，新增迁移 `082_user_avatar`。
- 新增鉴权头像读取、上传和移除接口；上传图片统一裁成 512px WebP。
- 首页和账号页通过带 Bearer Token 的图片请求读取私有头像。
- 头像 URL 包含用户 ID 和版本号，避免切换账号时命中旧头像缓存。

### 验证

- 移动端类型检查：通过
- 移动端 ESLint：通过
- 移动端全量：`24 files / 89 tests passed`
- 覆盖率：语句 `96.26%`、分支 `91.08%`、函数 `96.55%`、行 `97.92%`
- 后端头像与认证回归：`12 passed`
- Alembic head：`082_user_avatar`
- Expo Web 生产导出：通过
- `390px` 账号页实测：头像入口、相机角标和预览模式错误提示正常

### 当前边界

- 生产移动 API 仍未部署，头像上传需要先合并并部署移动后端。
- 当前改动尚未提交，也未重新构建 APK。

## v3.13.9 - 2026-11-23

### 交付主题

移动 API 部署缺口诊断与请求错误分类。

### 问题根因

- 设备网络正常，生产公开 API 也可达。
- 生产 `/api/mobile/v1/bootstrap` 和
  `/api/mobile/v1/workspaces/{id}/commerce-stores` 均返回 `404`。
- 当前生产 `main` 未包含移动端后端路由，店铺页却把所有查询异常显示成
  “请检查网络”，导致服务端版本不一致被误报为断网。

### 业务变化

- 请求错误按断网、登录失效、接口版本不一致、服务端异常和普通请求失败分类展示。
- 店铺、通知、通知偏好、素材库、Agent 结果和任务详情统一使用真实错误原因。
- 不再把移动接口未部署描述成用户网络问题。

### 技术变化

- 新增结构化查询错误说明 `describeQueryError` 和对应单元测试。
- `QueryErrorState` 支持接收真实查询错误并切换图标、标题和说明。
- 新增 `npm run check:api`，在发布前检查生产移动 API 是否真实部署。

### 验证

- `npm run typecheck`：通过
- `npm run lint`：通过
- 移动端全量：`22 files / 84 tests passed`
- 覆盖率：语句 `96.15%`、分支 `90.84%`、函数 `96.49%`、行 `97.86%`
- `npm run check:api`：正确失败，确认生产两个移动 API 均为 `404`
- `GET /api/v1/auth/login`：`405`，证明服务和网络链路正常

### 当前边界

- 本次只修复错误诊断和发布检查，没有部署缺失的移动端后端。
- 生产移动 API 必须随后端分支合并并部署后，店铺同步及其他移动业务才能恢复。

## v3.13.8 - 2026-11-23

### 交付主题

品牌冷启动页和连续加载态。

### 业务变化

- 冷启动改为留白画布上的 V 标记与暖金星点，与 App 工作台背景连续。
- 原生 Splash 会保持到字体、登录态和工作区本地状态准备完成，不再先露出空白页。
- 原生启动页退出后，页面加载统一使用同一品牌标记和细进度线，不再显示通用转圈。
- 系统开启“减少动态效果”时关闭呼吸动画，只保留静态加载指示。

### 技术变化

- `expo-splash-screen` 配置为 `#F2F3F5` 画布、`164pt` 品牌标记和透明 `contain` 缩放。
- 根布局在原生环境阻止 Splash 自动隐藏，核心本地状态完成后显式关闭。
- 新增 `BrandBootScreen`，复用 `splash-icon.png`，并作为 `PageLoader` 的统一加载界面。
- 字体资源加载失败时允许继续进入应用，避免单个资源异常永久卡住启动页。
- 新增启动就绪逻辑和 Expo Splash 配置契约测试。

### 验证

- 移动端类型检查：通过
- 移动端 ESLint：通过
- 移动端全量：`21 files / 78 tests passed`
- 覆盖率：语句 `96.27%`、分支 `89.60%`、函数 `96.29%`、行 `97.63%`
- Expo Doctor：`20/20` 检查通过
- Expo 配置内省：Splash 插件、底色、图片、宽度和缩放模式均正确
- Expo Web 生产导出：通过

### 当前边界

- 本轮尚未重新构建 APK，也未在真机录制完整冷启动序列；原生 Splash 的最终显示需下一版安装包确认。
- 当前只实现默认浅色品牌启动，不增加需要用户点击或停留的营销欢迎页。

## v3.13.7 - 2026-11-23

### 交付主题

登录键盘滚动、输入光标和旧版登录响应兼容。

### 业务变化

- Android 键盘弹起时只上移必要距离，不再把 Logo 和品牌区滚出屏幕。
- 邮箱、密码和用户名字段的输入光标统一使用品牌近黑色，不再出现系统绿色竖线。
- 当前生产登录接口只返回 `access_token` 时也能正常进入工作台。
- “网络失败”和“登录成功但会话保存失败”改为不同错误提示。

### 技术变化

- 删除键盘弹起后的 `scrollToEnd`，改为固定最小滚动距离。
- `TextInput` 显式设置 `selectionColor` 与 Android `cursorColor`。
- 移动端 `AuthTokens` 将 refresh session 字段改为可选，兼容旧版接口。
- `setSession` 在缺少 refresh token 时清理旧凭据，不阻塞本次登录。
- 新增旧版 access-only 登录响应单元测试。

### 验证

- 移动端类型检查：通过
- 移动端全量：`20 files / 75 tests passed`
- 覆盖率：语句 `96.25%`、分支 `89.34%`、函数 `96.22%`、行 `97.61%`
- ESLint：通过
- 生产登录接口实测：`200`
- 生产 Nginx 日志确认手机请求已到达服务端

### 当前边界

- 当前生产后端未返回 refresh token，因此本轮先兼容 access-only 登录；
  完整会话自动续期需要后端新版认证接口部署后才能启用。

## v3.13.6 - 2026-11-23

### 交付主题

安装图标比例修正与登录页字体微调。

### 业务变化

- Android 安装页图标中的 V 缩小并校正到视觉中心，星点继续保留在右上角。
- 同步更新旧版图标、自适应图标、单色图标、启动图和 favicon。
- 登录页保持原布局，只微调字标宽度、标语字号与字重、辅助文字颜色和输入框边界。

### 技术变化

- 新增 `assets/brand/app-mark.png` 作为统一图标主标。
- 新增 `scripts/generate-app-icons.ps1`，从一个主标生成全部平台图标资产。
- 登录页辅助文字对比度提升到可用范围，品牌星点继续保持暖金色。

### 验证

- 移动端类型检查：通过
- 移动端全量：`20 files / 74 tests passed`
- 覆盖率：语句 `96.25%`、分支 `89.34%`、函数 `96.22%`、行 `97.61%`
- ESLint：通过
- Expo Web 预览导出：通过
- `390 x 844` 登录页实拍：布局未改，文字层级和对比度提升
- 图标尺寸与透明通道检查：通过

### 当前边界

- 已安装的旧 APK 不会自动更新系统安装页图标，需要重新打包并安装后确认。
- 本轮只输出登录页效果图，没有按新的复杂页面方向重做登录流程。

## v3.13.5 - 2026-11-23

### 交付主题

Web 顶栏 App 下载入口与二维码体验。

### 业务变化

- Web 工作台顶栏新增“下载 App”入口，桌面显示图标与文字，窄屏保留图标热区。
- 下载弹层同时提供二维码与“直接下载 APK”，手机用户无需扫描自己的屏幕。
- 弹层明确展示 Android 内测版本、安装方式和当前工作宗旨，并说明 iOS 仍在准备。

### 技术变化

- 新增 `qrcode.react`，二维码与直接下载共用 `VITE_MOBILE_APP_DOWNLOAD_URL`。
- 下载配置只接受 HTTPS 地址；无效配置回退到当前已验证构建，避免生成坏二维码。
- Vite 开发代理支持 `VITE_DEV_API_PROXY_TARGET`，可在本地后端未启动时通过同源代理
  连接生产 HTTPS API 完成登录态验收。

### 验证

- APK 地址检查：`200`，约 `150.9 MB`
- 前端全量：`56 files / 190 tests passed`
- TypeScript 类型检查：通过
- Vite 生产构建：通过
- 首屏包体积门禁：`225 KB gzip`，通过
- 内置浏览器桌面 `1280x720`、手机 `390x844`、`375x812` 实测：
  顶栏入口、二维码、直接下载按钮、Esc 关闭和焦点回退正常

### 当前边界

- 当前二维码指向 EAS 内测产物，预计 `2026-12-06` 过期；正式发布前必须通过
  `VITE_MOBILE_APP_DOWNLOAD_URL` 替换为官网稳定 CDN 地址。
- 当前只有 Android APK，iOS 安装包仍待 Apple Developer 凭据。
- 前端 `npm run lint` 仍不可执行：项目未安装 ESLint 依赖且没有对应配置；
  本轮以 TypeScript、全量测试和生产构建作为代码门禁。

## v3.13.4 - 2026-11-23

### 交付主题

品牌头像标记比例与星点修复。

### 业务变化

- 首页问候与账号页的 V 标记缩小到参考图比例，不再顶满黑色圆形。
- 补回标记右上角的品牌星点，账号页 `44pt` 和首页 `38pt` 均可辨认。

### 技术变化

- `AgentAvatar` 从位图改为 `react-native-svg` 矢量绘制，避免小尺寸缩放失真。
- 以 `96 x 96` 画布固定 V、底线和星点的内边距与相对位置。
- 新增 `colors.brandStar` 品牌暖金色，和状态色、时间轴琥珀色分离。

### 验证

- 内置浏览器 `390x844`、`375x812` 实测：首页与账号页头像比例正常
- 移动端全量：`20 files / 74 tests passed`
- 覆盖率：语句 `96.25%`、分支 `89.34%`、函数 `96.22%`、行 `97.61%`
- TypeScript 类型检查：通过
- ESLint：通过
- Expo Web 预览导出：通过

### 当前边界

- 本轮没有重新构建 APK，原生安装包仍需下一版打包后确认实机显示。

## v3.13.3 - 2026-11-23

### 交付主题

移动端店铺添加入口与 Android 顶部安全区修复。

### 业务变化

- 首页店铺选择器新增“添加店铺”，账号页和全部功能新增“店铺与渠道”。
- 新增店铺页展示工作区已连接店铺，并提供 Shopify、Amazon、Temu 授权入口。
- Shopify 支持输入裸子域或完整 `.myshopify.com` 域名后发起真实 OAuth。
- 授权返回 App 后自动刷新店铺列表。
- 修复执行结果页在华为等长状态栏设备上的双倍顶部留白。

### 技术变化

- 新增店铺 provider 定义、域名规范化、状态文案和单元测试。
- 新增移动端 Shopify、Amazon、Temu connect URL 客户端。
- 带 `ModalScreenHeader` 的执行结果和通知异常页统一使用
  `edges={["left","right","bottom"]}`，顶部安全区只由标题栏消费。
- 全部功能的“店铺与渠道”使用独立店铺图标，不再落到默认履约图标。
- 预览模式明确提示不会发起真实授权，不伪造连接成功。

### 验证

- 移动端全量：`20 files / 74 tests passed`
- 覆盖率：语句 `96.25%`，分支 `89.34%`，函数 `96.22%`，行 `97.61%`
- TypeScript 类型检查：通过
- ESLint：通过
- 生产 Shopify connect URL：可生成，目标主机为测试店铺域名
- 内置浏览器 `390x844`、`375x812` 实测：首页添加店铺、店铺页、
  全部功能店铺入口、账号店铺入口和 Shopify 授权弹层正常
- 执行结果页在 `390x844`、`375x812` 下无重复顶部安全区留白

### 当前边界

- Amazon SP-API 和 Temu 开放平台应用凭据尚未配置，生产接口当前返回明确
  “尚未配置”错误。
- 本轮没有重新构建 APK，华为真机安全区修复需下一版安装包确认。
- 首页文件仍有其他会话的并行改动，本版本只保证当前工作区和预览行为。

## v3.13.2 - 2026-11-23

### 交付主题

Composer 可见发送按钮、语音转写恢复和输入框焦点修正。

### 业务变化

- 文字输入非空后，Composer 明确显示黑色发送按钮，不再只依赖键盘发送键。
- 发送中显示加载态，发送失败时保留输入内容以便重试。
- 语音识别失败按登录过期、录音格式、服务未配置、服务不可用和网络问题分别提示。
- 输入聚焦时移除不必要的浏览器焦点框。

### 技术与数据

- 新增 Composer 发送状态纯函数和语音错误映射。
- 修复运行时服务商空值覆盖环境变量的问题。
- 修复语音转写调用层传空默认值导致环境 DashScope Key 被遮蔽的问题。
- 生产真实 WAV 与 M4A 语音均成功返回中文转写。

### 验证

- 移动端全量：`19 files / 71 tests passed`
- 覆盖率：语句 `96.62%`，分支 `89.65%`，函数 `96.07%`，行 `98.13%`
- TypeScript 类型检查：通过
- ESLint：通过
- 后端语音与配置定向：`6 passed`
- 生产 WAV 转写：`201`，返回“帮我看看今天的订单，有超时的先处理。”
- 生产 M4A 转写：`201`，返回同一段中文文本
- 375px 预览：输入“帮我上架一个新产品”后发送按钮可见，输入框无焦点线

### 当前边界

- 本轮没有重新构建 APK，真机麦克风录制仍需在下一版安装包验证。
- 生产语音存储仍使用本地私有目录，短期保留策略为服务端配置。

## v3.13.1 - 2026-11-23

### 交付主题

账号页底部可达性与快速切换账号入口。

### 业务变化

- 账号页改为原生可滚动长页，375px 和 390px 均可滚动到安全设置与退出登录。
- 个人资料卡右上角新增常驻“切换账号”入口，不再必须滚到底部才能退出。
- 切换账号使用 App 内底部确认层，不会直接退出；工作区数据不受影响。

### 技术变化

- 账号页内容容器由固定 `View` 改为 `ScrollView`，内容高度使用 `flexGrow`。
- 新增切换账号确认状态和底部操作层，兼容 Web 与原生，不依赖系统 Alert。

### 验证

- 移动端全量：`17 files / 67 tests passed`
- TypeScript 类型检查：通过
- ESLint：通过
- 375px 实测：可滚动到底部，退出登录可见
- 390px 实测：切换账号入口首屏可见
- 切换账号底部确认层在 375px 正常展示

### 当前边界

- 本轮未重新构建 APK；待用户确认后统一打包。
- “切换账号”当前语义为退出当前账号后重新登录，不维护多账号会话栈。

## v3.13.0 - 2026-11-23

### 交付主题

App 内原生法律正文与离线阅读。

### 业务变化

- 法律中心所有协议改为 App 内原生页面，点击不再打开 Web。
- 七份文档全部可离线阅读，包含标题、版本、生效日期、章节和项目列表。
- 登录页、注册页和账号页的协议入口统一导航到 App 内正文。
- 每份正文底部提供系统邮件操作，用于账号、隐私、数据、安全和举报请求。

### 技术变化

- 新增 `/legal/[slug]` 原生动态路由和原生长文阅读页面。
- 新增法务内容同步脚本，从 `frontend/src/lib/legal.ts` 机械生成
  `mobile/src/features/legal/legal-documents.json`。
- 新增 `npm run legal:sync`，避免 App 与 Web 手工复制正文。
- 移除移动端协议入口对 Web URL 和浏览器跳转的依赖。

### 验证

- 移动端全量：`17 files / 67 tests passed`
- 逻辑覆盖率：语句 `96.98%`，分支 `90.81%`，函数 `95.91%`，行 `98.65%`
- TypeScript 类型检查：通过
- ESLint：通过
- Expo Web 构建：`dist-preview-legal-v42` 成功
- 375px 和 390px 实测：隐私政策、举报列表、正文底部邮件操作无横向溢出
- 离线正文来源与 Web 法务版本一致

### 当前边界

- 本轮未重新构建 APK；待用户确认后统一打包。
- 法律正文仍需正式法律终审，技术实现不替代法律意见。

## v3.12.0 - 2026-11-23

### 交付主题

生产移动 API 上线与 Android 真实登录内测包。

### 业务变化

- `https://veyaship.com` 已提供新版移动 API，登录不再是只打不开的 UI 预览。
- 内测用户可以使用真实邮箱、密码和 Agent 工作区登录。
- 注册成功后自动创建个人工作区，bootstrap 返回合同版本和工作区信息。
- EAS `preview` 使用生产 HTTPS API，`previewMode=false`，不再使用固定预览数据。
- Android internal distribution APK 已生成，可直接安装体验。

### 技术与数据

- 生产后端已升级并执行迁移 `050` 至 `081`，当前数据库版本为
  `081_work_item_channel_scope (head)`。
- 修复 `077_workspace_automation` 中 PostgreSQL 布尔默认值错误：
  `server_default=sa.text("1")` 改为 `sa.true()`。
- 新增 PostgreSQL 布尔默认值回归测试。
- EAS `preview` profile 固定 `EXPO_PUBLIC_API_URL=https://veyaship.com`，
  并明确绑定 `preview` 环境。
- 生产部署前已备份数据库与后端代码：
  `crossborder_ai-pre-mobile-20261122.dump` 和
  `backend-pre-mobile-20261122.tar.gz`。

### 验证

- 生产健康检查：`200`
- 未登录移动 bootstrap：`401`，不再为 `404`
- 真实注册：成功
- 真实登录：成功
- 真实 bootstrap：返回 1 个个人工作区
- 生产数据库迁移：`081_work_item_channel_scope (head)`
- PostgreSQL 迁移与启动门禁：`16 passed`
- 移动 API、认证、工作区和迁移组合门禁：`63 passed`
- EAS Android `preview`：`FINISHED`
- APK 下载检查：`200`，约 `150.9 MB`
- Android versionCode：`5`
- EAS Build：`4386fa83-5e8d-4912-b15b-ab7a42388f18`

### 当前边界

- 当前完成 Android 内测 APK；iOS TestFlight 仍需 Apple Developer 凭据。
- APNs/FCM 真机推送、相机、麦克风、相册和深链仍需真实设备验收。
- 真机尚未安装本轮 APK，设备端到端验收仍待执行。

## v3.11.0 - 2026-11-22

### 交付主题

App 法律与隐私中心及 AI 内容确认闭环。

### 业务变化

- App 新增“法律与隐私”模态页面，覆盖服务条款、隐私政策、数据处理与删除、
  AI 使用说明、安全与事件响应、侵权举报和联系我们。
- 登录告知明确包含《服务条款》《隐私政策》与《AI 使用说明》。
- 注册必须显式勾选三项核心文档；未勾选时阻止创建账号并给出可执行错误。
- 账号页新增常驻“法律与隐私”入口。
- 页面展示服务条款 `1.1`、隐私政策 `1.3` 和 AI 使用说明 `1.0` 的当前版本。

### 技术变化

- 新增统一的移动端法务文档元数据和注册同意校验，避免页面复制文档正文和版本。
- 新增 Expo Router `/legal` 路由，使用公网 HTTPS 法务地址作为唯一正文来源。
- 登录页只在登录模式展示登录同意；注册模式使用独立复选框和两行可读文案。
- 主要业务代码包含中文注释，说明法务入口与同意行为。

### 验证

- 移动端全量：`17 files / 66 tests passed`
- 逻辑覆盖率：语句 `96.91%`，分支 `91.66%`，函数 `95.55%`，行 `98.63%`
- TypeScript 类型检查：通过
- ESLint：通过
- Expo Web 构建：`dist-preview-legal-v42` 成功
- 真实页面检查：390px 法律中心、375px 登录、注册和账号页无横向溢出
- 注册未勾选确认：正确显示错误并阻止提交
- 七份公网法务地址当前均返回 `200`

### 当前边界

- 本轮复用网站已发布法律正文，不在 App 内复制长文档。
- 用户同意的文档版本尚未写入服务端审计表；客户端告知与显式勾选已完成。
- 正式对外发布前仍需法律文本终审，并确认运营主体、联系方式和适用法域。

## v3.10.1 - 2026-11-22

### 交付主题

移动端发布分支规范与 EAS 构建职责边界。

### 业务变化

- 明确 `main` 为唯一发布主线，不允许直接使用功能分支发布正式内测或生产包。
- 明确 UI 验收包从功能分支构建，正式包只从合并后的 `main` 或发布标签构建。
- 合并前要求 App、移动 API、数据库迁移和部署配置处于同一可运行版本。

### 技术变化

- 增加 `codex/<scope>` 功能分支、PR、版本标签和构建证据的发布流程。
- 增加 `mobile-vX.Y.Z` 版本标签命名约定。
- 保留 `ui-preview` 作为纯界面验收档位，不与真实账号和真实店铺验收混淆。

### 验证

- 当前功能分支与 `origin/main` 的差异为 `3` 个提交、`130` 个文件。
- 功能分支、远程跟踪分支和 EAS GitHub 仓库连接均已确认。
- 无新增代码依赖与数据库迁移。

### 当前边界

- 功能分支尚未合并到 `main`，不能作为正式发布来源。
- `main` 当前尚未包含本轮移动端源码和移动 API 的完整发布组合。

## v3.10.0 - 2026-11-22

### 交付主题

Temu LOCAL/SEMI 供货价审核预检、价格变更提交和价格审核单回读。

### 业务变化

- Agent 可以为指定 Temu SKU 准备基础供货价变更计划。
- 预览展示外部 SKU、本地参考价、新供货价、币种和变更原因。
- 价格审核中或等待卖家确认时，预检停止提交。
- 新价格必须由卖家显式输入，不自动复制本地售价。
- 提交成功只显示“已提交审核”，不表示买家售价已经生效。
- 价格未白名单、已有待确认价格、涨跌幅超限、促销冷却或越界时展示可执行错误。

### 技术与安全

- 新增 `TemuPriceService` 和 `TemuPriceUpdateActionAdapter`。
- 新增受控动作 `temu.pricing.submit` 和 Agent 工具
  `submit_temu_price_change`。
- 使用 `bg.local.goods.list.query` 按 `skuSn` 精确映射 Temu `skuId`。
- 使用 `bg.local.goods.priceorder.query` 检查价格审核状态。
- 使用 `bg.local.goods.priceorder.change.sku.price` 提交
  `newSupplierPrice{amount,currency}`。
- 提交后按新价格审核单 ID 回读，不把接口受理当成售价生效。

### 验证

- 后端全量：`1013 passed, 4 skipped`
- Temu 价格变更专项：`10 passed`
- 价格服务与适配器覆盖率：`82%`
- 价格、库存、状态、V3 发布、履约、动作运行时和 Agent 组合：`75 passed`
- 无新增数据库迁移

### 当前边界

- 真实 Temu 价格接口白名单、scope、审核状态、价格审核单和买家售价生效
  仍需 LOCAL/SEMI 测试商品验收。
- 当前只提交单个 SKU 的基础供货价，不处理活动价、促销价或批量改价。
- 没有真实价格审核样本前，不能把审核单创建解释为买家售价已改变。

## v3.9.0 - 2026-11-22

### 交付主题

Expo/EAS UI 预览构建闭环与真实内测环境门禁。

### 业务变化

- Expo 网页版可直接选择 `ui-preview` 档位构建 Android APK 查看完整 App 界面。
- UI 预览包跳过登录和真实网络依赖，使用自洽的固定业务数据进入工作台。
- 真实 `preview` 和 `production` 档位缺少 HTTPS API 时立即停止构建，避免生成
  安装后无法登录的无效内测包。
- Android `development`、`preview` 和 `ui-preview` 明确输出 APK，便于真机安装。

### 技术变化

- EAS 项目固定为 `@felix-ai/veyaship-agent`，projectId 为
  `85dd918e-3671-4472-be2b-dcdb951c3930`。
- EAS 项目已连接 GitHub 仓库 `felixfeng-ai/crossborder-ai`，Base directory 为
  `crossborder-ai/mobile`。
- 已创建 Android 托管 Keystore，应用标识为 `com.veyaship.agent`。
- `app.config.ts` 增加真实构建 API 必填、HTTPS 协议和尾部斜杠规范化校验。
- `eas.json` 增加 `EXPO_PUBLIC_REQUIRE_REMOTE_API`，本地开发仍可使用回环 API。
- `ui-preview` 继续使用 `EXPO_PUBLIC_PREVIEW_MODE=1`，不会与真实构建混淆。

### 验证

- `expo-doctor`：`20/20` 通过。
- EAS `project:info`：成功识别 `@felix-ai/veyaship-agent`。
- Expo GitHub 设置：仓库连接成功，Base directory 保存成功。
- Android 凭据页：已显示应用标识 `com.veyaship.agent`，托管 Keystore 创建成功。
- EAS `ui-preview` 配置解析：成功，`previewMode: true`，Android 输出 APK。
- EAS 真实 `preview` 配置在缺少 API 时：按预期失败。
- 移动端全量：`16 files / 62 tests passed`。
- TypeScript 类型检查：通过。
- ESLint：通过。
- Android 预览 JS Bundle：`dist-preview-native-v41` 导出成功。
- 无新增数据库迁移。

### 当前边界

- `https://veyaship.com/health` 可访问，但当前部署仍是旧后端；
  `/api/mobile/v1/bootstrap` 返回 `404`，不能供真实内测包登录。
- APNs、FCM、iOS 签名和真机端到端验收仍需外部凭据与设备；Android
  `ui-preview` 已具备云端签名和 APK 构建入口。
- Amazon/Temu 等平台的真实店铺写操作仍需测试店铺和开放平台权限验收。

## v3.8.0 - 2026-11-22

### 交付主题

Temu LOCAL/SEMI 普通库存查询、外部 SKU 唯一映射、全量覆写和平台回读。

### 业务变化

- Agent 可以按当前工作区 Temu Listing 和 SKU 准备库存覆写计划。
- 库存预览展示外部 SKU、Temu goodsId、Temu skuId、当前库存和目标库存。
- 卖家确认后使用 `skuStockTargetList` 覆写普通库存，不使用增量库存。
- 外部 SKU 找不到、重复出现或无法精确对应时明确拒绝，不按数组位置猜测。
- 平台编辑返回失败时展示 Temu 错误；回读库存与目标值一致后才更新本地 SKU。

### 技术与安全

- 新增 `TemuInventoryService`、`TemuInventoryUpdateActionAdapter`。
- 新增受控动作 `temu.inventory.update` 和 Agent 工具 `update_temu_inventory`。
- 使用 `temu.goods.stock.query` 精确读取 `outSkuSn`、`skuId` 和普通库存。
- 使用 `bg.local.goods.stock.edit` 全量目标库存，并提交稳定
  `requestUniqueKey`。
- 普通库存范围限制为 0 至 1,000,000。
- 只允许 LOCAL/SEMI，同时要求库存查询和编辑 scope。

### 验证

- 后端全量：`1003 passed, 4 skipped`
- Temu 库存覆写专项：`8 passed`
- 库存服务与适配器覆盖率：`81%`
- 库存、状态追踪、V3 提交、scope、动作运行时和 Agent 组合：`66 passed`
- 无新增数据库迁移

### 当前边界

- 真实 `temu.goods.stock.query`、`bg.local.goods.stock.edit` scope、外部 SKU
  映射和平台回读仍需 LOCAL/SEMI 测试商品验收。
- 不修改预售价库存、增量库存、多商品批量或自动补货策略。
- 本轮不包含价格写回。

## v3.7.0 - 2026-11-22

### 交付主题

Temu 商品提交后的原始状态追踪、工作项更新和确认映射门禁。

### 业务变化

- Temu V3 商品回读确认后会登记“Temu 正在处理”工作项。
- 调度器每 15 分钟批量读取处理中商品的 Temu 原始状态。
- 同一商品重复查询只更新原工作项，不产生重复任务。
- 工作项保留 `status`、`subStatus`、观察时间和次数。
- 默认状态映射为空，任何整数状态都显示为处理中，不猜审核结果。
- 经真实样本确认后，通过映射会完成工作项并更新 Listing 发布时间；
  驳回映射会让工作项进入人工处理。

### 技术与安全

- 新增 `temu_listing_status_sync` 服务和 `temu_listing_status_sync` 调度任务。
- 主接口使用 `bg.local.goods.publish.status.get` 批量 `goodsIdList`。
- 状态 scope 不可用或接口暂时不可用时，按商品列表回读原始状态。
- 复用 `AgentSignal`、`WorkItem` 和 `ListingDraft`，无新增数据库迁移。
- 信号按连接和 `goodsId` 幂等，店铺失败不影响其他店铺。
- 平台能力接口增加 `temu.listings.status` 读能力。

### 验证

- 后端全量：`995 passed, 4 skipped`
- Temu 商品状态追踪专项：`8 passed`，服务覆盖率：`81%`
- 状态追踪、V3 提交、信号、调度、动作运行时和自发货组合：`68 passed`
- 真实验收仍需状态样本和确认映射

### 当前边界

- Temu 商品状态枚举仍为空映射，提交成功或状态变化都不等于可售。
- 真实 `bg.local.goods.publish.status.get` scope 和响应字段仍需测试店铺验收。
- 状态映射必须有真实 `goodsId` 样本、连接和确认时间后才能启用。

## v3.6.0 - 2026-11-22

### 交付主题

移动端核心功能链路修复、真实店铺筛选、通知偏好与素材重生成。

### 业务变化

- 生成图片“保存到素材库”改为真实幂等入库，不再只跳转页面。
- 时间线、今日计划和日结统一使用工作区设备时区，修复 UTC 日界错位。
- 任务、Agent、通知和素材库查询失败时显示真实错误与重试，不再伪装成失效、处理中或空状态。
- 账号页支持真实工作区切换，通知深链会先恢复目标工作区。
- 首页“全部店铺”接入真实店铺清单，时间线、计划、通知和功能计数同步过滤。
- 通知支持单条已读；执行失败通知改用警告图标。
- 新增通知偏好页面，支持提醒类型、免打扰时段和 IANA 时区。
- 素材支持修改描述、重选最多 4 张参考图并创建新的图片动作，保留旧结果。
- 视频“保存视频”改为真实下载并写入系统相册。
- 离线文案改为“网络已断开，Agent 仍会继续处理”。
- 客户回复快捷入口按投诉风险、评价回复、待回复消息互斥分类。
- 素材库筛选状态下排序只调整可见素材，不打乱隐藏素材顺序。

### 技术与数据

- `work_items` 新增可空 `channel_type`、`channel_id` 和店铺范围索引。
- 新增迁移 `081_work_item_channel_scope`；历史未归因任务只在全部店铺显示。
- 新增移动端店铺清单接口和按渠道过滤的时间线、计划、通知参数。
- Shopify、Amazon、Temu、Shopify 库存和邮件客服在创建新任务时写入店铺归属。
- 新增生成图入库、单条通知已读和素材重生成移动接口。
- 新增 `expo-asset`、`react-native-worklets`、`expo-file-system` 和 `expo-media-library`。
- 相册权限、保存说明和原生插件已写入 Expo 配置。

### 验证

- 移动端全量：`16 files / 62 tests passed`
- 逻辑覆盖率：语句 `96.62%`，分支 `91.3%`，函数 `95.23%`，行 `98.49%`
- TypeScript 类型检查：通过
- ESLint：通过
- `expo-doctor`：`20/20 passed`
- 后端全量：`995 passed, 4 skipped`
- 核心链路定向回归：`72 passed`
- Expo Web 预览构建：`dist-preview-v40` 成功
- 实际运行检查店铺选择、工作区切换、通知偏好和素材重生成弹层

### 当前边界

- 历史工作项没有可靠店铺信息，不进行猜测回填，只在全部店铺显示。
- 旧 Amazon/Temu 连接仍按用户存储，没有 workspace_id；当前只在个人所有者工作区展示，避免团队工作区串店。
- 视频保存已实现原生权限与相册写入，仍需 iOS/Android 真机验收。
- 真实平台店铺动作、推送和后台恢复仍需真实账号与设备验收。

## v3.5.0 - 2026-11-22

### 交付主题

Temu LOCAL/SEMI 商品发布 V3 请求构建、图片公网化、受控提交和商品回读。

### 业务变化

- Agent 可以从当前工作区 Temu Listing、商品和有效 SKU 准备 V3 发布计划。
- 卖家选择 1 至 9 张图片，确认后先发布为公网 HTTPS 地址，再提交 Temu。
- 发布请求包含真实标题、描述、类目、价格、库存、SKU 规格和可选包装信息。
- 包装信息缺失时不编造默认重量和尺寸。
- 跨境店铺、缺少 V3 或商品回读 scope、缺少类目/价格/图片时明确拒绝。
- 提交成功后显示“已提交，等待 Temu 处理”，不把未公开状态码解释成可售。

### 技术与安全

- 新增 `TemuListingPublishService`、`TemuListingPublishActionAdapter`。
- 新增受控动作 `temu.listings.submit` 和 Agent 工具 `submit_temu_listing`。
- 首发只支持 LOCAL/SEMI 和 `temu.local.goods.v3.add`。
- 发布前要求 `bg.local.goods.list.query` 用于按 `goodsId` 回读。
- 图片必须来自当前工作区，且只能是可发布的图片格式。
- V3 请求使用稳定 `externalGoodsId` 与 `externalSkuId`，价格为字符串。
- 回读只保存 Temu 原始状态和子状态，状态映射明确标记为未猜测。

### 验证

- 后端全量：`986 passed, 4 skipped`
- Temu V3 商品发布专项：`14 passed`
- V3 请求构建与适配器综合覆盖率：`81%`
- Temu 发布、商品读取、scope、动作运行时、Agent 和自发货组合：`62 passed`
- 无新增数据库迁移

### 当前边界

- 真实 Temu 应用是否授予 `temu.local.goods.v3.add` 仍需店铺验收。
- 尚未确认真实类目推荐、图片下载、商品状态和子状态枚举。
- 当前不接定制、MTO、二手、多包裹拆单、商品更新、退款、库存、价格和售后。
- 提交成功只代表 Temu 已受理创建请求，不代表商品已经通过审核或可售。

## v3.4.0 - 2026-11-22

### 交付主题

Temu 自发货只读验收诊断服务与 CLI 安全门禁。

### 业务变化

- 真实 LOCAL/SEMI 测试店铺可用前，可以先运行只读诊断确认订单是否能安全发货。
- 诊断报告展示订单行数、商品数量、承运商、掩码物流单号、仓库和阻断项。
- 报告明确标记 `submitted=false`，不会误触发真实发货。
- CLI 仅在诊断为 `ready=true` 时返回成功退出码，便于验收和 CI 复用。

### 技术与安全

- 新增 Temu 自发货只读诊断服务模块和诊断入口。
- 新增 `scripts/verify_temu_fulfillment_readiness.py`。
- 诊断只调用自发货适配器 `preflight`，从不调用 `execute` 或
  `bg.logistics.shipment.v2.confirm`。
- 物流单号只显示前四位和后四位，报告不包含 Token、App Secret 或买家信息。
- 数据库不可用或店铺连接不存在时输出阻断 JSON，不抛出未处理堆栈。

### 验证

- 后端全量：`966 passed, 4 skipped`
- Temu 自发货只读诊断专项：`4 passed`，服务覆盖率：`89%`
- 诊断、自发货、订单巡检、scope 和动作运行时组合：`41 passed`
- CLI `--help` 和阻断路径烟测通过
- 无新增数据库迁移

### 当前边界

- 当前执行环境没有可用的 Temu 真实店铺连接，只读诊断尚未对真实订单运行。
- 真实承运商、仓库要求和物流回读仍需 LOCAL/SEMI 测试订单验收。
- 诊断工具不会提交发货；真实写操作仍必须走 App 确认和动作运行时。

## v3.3.0 - 2026-11-22

### 交付主题

Agent 执行结果页升级为生产级工作回执。

### 业务变化

- 页面从“白底组件堆叠”改为一张连续工作回执，形成完整阅读路径。
- 回执顶部展示 Agent 身份、角色和真实执行状态。
- 用户指令、具体结果和执行轨迹进入同一信息结构，结果摘要成为主角。
- 执行步骤展示真实完成数量，并逐项标记完成、进行中或待执行。
- 接入本轮实际生成的待确认工作项，显示任务标题和当前处理状态。
- 主操作改为“查看处理方案”，直接进入真正需要用户决策的任务。

### 设计与工程

- 页面画布改为安静的浅雾灰，回执使用单层纸白表面和轻微染色阴影。
- 删除了独立状态大图标、巨型泛化标题和悬浮卡片式步骤分组。
- `390 x 844` 和 `375 x 812` 均验证首屏完整展示待确认事项。
- 固定底部按钮保留安全间距，不再覆盖回执或任务对象。
- 新增项目级 `Agent Work Receipt` 可复用模式约束。

### 验证

- 移动端全量：`8 files / 30 tests passed`
- TypeScript 类型检查：通过
- ESLint：通过
- Expo Web 预览构建：`dist-preview-v39` 成功
- 完成两轮真实截图审查，并修复 375 宽度下固定按钮贴近内容的问题

### 当前边界

- 执行结果数据没有时间戳字段，因此页面不展示伪造的完成时间或耗时。
- 回执中的待确认任务来自当前 workspace 的真实任务查询，查询失败时保留回执并给出可恢复说明。
- 真机动态字体、辅助功能和语音播报仍需真机验收。

## v3.2.0 - 2026-11-22

### 交付主题

Agent 执行结果页的导航与信息层级统一。

### 业务变化

- 顶部标题由“小 Veya”改为“执行结果”，与“Agent 任务”等详情页保持一致。
- 完成、处理中和失败状态改为横向状态摘要，不再使用孤立的超大圆形图标。
- 执行步骤从独立大卡片改为无框清单，和各页面现有列表节奏保持一致。
- 主操作固定到底部安全区域，避免内容较短时按钮悬在页面中部。
- 标题字号与行高收敛，减少无意义的大面积留白和过度强调。

### 验证

- 移动端全量：`8 files / 30 tests passed`
- TypeScript 类型检查：通过
- ESLint：通过
- Expo Web 预览构建：`dist-preview-v36` 成功
- `390 x 844` 与 `375 x 812` 均完成实际截图检查
- 已确认状态摘要、步骤清单和底部主按钮无重叠或横向溢出

### 当前边界

- 本次为现有页面层级与排版修正，没有改变 Agent 执行接口或业务状态。
- 真机动态字体、系统辅助功能和语音播报仍需真机验收。

## v3.1.0 - 2026-11-21

### 交付主题

移动端完整 UI 评审截图包与业务状态补齐。

### 业务变化

- 补充商品上架、库存调整和退款售后三类业务任务预览。
- 截图覆盖首页、今日计划、全部功能、通知、素材库、账号和执行结果。
- 截图覆盖订单确认、客户订单选择、附件预览、素材成功/失败和 Agent 结果。
- 截图覆盖登录、注册、用户名字符错误、用户名重复与受限视口滚动状态。
- 三张拼版总览图和逐页 README 清单可直接交给外部 UI/设计评审。

### 技术与数据

- `PREVIEW_MODE` 新增上架、库存和退款固定夹具，生产接口不受影响。
- 素材库预览改为三张公开商品图，并兼容绝对图片地址。
- 主截图统一为逻辑视口 `390 x 844 pt`，DPR 2，输出 `780 x 1688`。
- 受限视口键盘模拟单独放入 `supplemental`，避免破坏主截图尺寸一致性。
- 新增预览夹具测试，约束业务入口与高风险确认面板内容。

### 交付物

- `mobile/artifacts/ui-review-2026-11-21/README.md`
- 25 张主截图与 1 张补充键盘视口截图
- `contact-sheet-1.png`、`contact-sheet-2.png`、`contact-sheet-3.png`
- `mobile/artifacts/VeyaShip-mobile-ui-review-2026-11-21.zip`

### 验证

- 移动端全量：`8 files / 30 tests passed`
- TypeScript 类型检查：通过
- ESLint：通过
- Expo Web 预览构建：`dist-preview-v35` 成功
- 已在 `390 x 844` 视口实际访问并检查全部截图页面
- 已检查确认面板、图片加载、附件预览、滚动底部和注册错误态

### 当前边界

- 截图来自 Expo Web 运行时，不替代 iOS/Android 真机包截图。
- 真实系统键盘、权限弹窗、触觉反馈和系统分享面板未进入主截图矩阵。
- 外部平台任务只展示确认前 UI，截图过程中未执行真实发布、退款或库存写入。

## v3.0.0 - 2026-11-21

### 交付主题

Temu LOCAL/SEMI 自发货受控动作、承运商校验、物流单号提交和逐子单回读。

### 业务变化

- Agent 可以读取 Temu 父订单和当前区域承运商，准备待确认的自发货计划。
- 发货预览展示父订单、承运商、物流单号、仓库和商品数量，不展示买家隐私。
- 卖家确认后提交 Temu 自发货信息，成功后关闭原订单异常任务。
- 同一订单重复处理时，只有已回读到相同物流单号才跳过二次提交。
- 承运商不匹配、合作仓履约、买家改地址、买家取消、仓库缺失和店铺受限时
  明确失败，不伪造发货成功。

### 技术与安全

- 新增 `TemuFulfillmentService` 和 `TemuOrderFulfillmentActionAdapter`。
- 新增受控动作 `temu.orders.fulfill` 和 Agent 工具 `fulfill_temu_order`。
- 自发货同时要求订单详情、承运商、发货确认和物流回读 scope。
- 使用 `bg.logistics.companies.get` 校验当前区域承运商。
- 使用 `bg.logistics.shipment.v2.confirm` 提交父订单全部可履约订单行和 Temu
  原始数量，固定 `sendType=0`。
- 使用 `bg.logistics.shipment.v2.get` 按每个子订单回读物流单号。
- Temu 返回 `120012004`“已发货”时仍要求回读相同物流单号。
- 物流单号去除空格、横线和其他符号，响应不包含 Access Token 或 App Secret。

### 验证

- 后端全量：`956 passed, 4 skipped`
- Temu 自发货专项：`9 passed`，综合覆盖率：`82%`
- Temu 自发货、订单巡检、订单读取、scope、动作运行时和 Amazon 履约组合：
  `63 passed`
- 无新增数据库迁移

### 当前边界

- 只支持卖家自发货，不实现 Temu Buy-Shipping 面单购买和异步面单下载。
- 真实承运商 ID、仓库要求、`sendType=0` 和物流回读仍需真实 LOCAL/SEMI
  测试订单验收。
- Temu 商品发布、退款、库存、价格和售后写操作仍未接入。

## v2.12.0 - 2026-11-21

### 交付主题

登录页接入真实 signup 模式、用户名校验和首页称呼截断。

### 业务变化

- 创建账号字段顺序调整为「用户名 → 邮箱 → 密码」，三框同宽、同圆角、高 58。
- 用户名字符规则为 4–12 位中文、字母、数字或下划线，不允许空格。
- 用户名在失焦后等待 400ms 检查唯一性，冲突时在输入框下方显示 12pt 红字。
- 注册提交前再次校验用户名，避免用户绕过失焦检查。
- 首页问候使用注册用户名；超过 8 个字符时显示前 6 个字符加省略号。
- 输入聚焦不再改变边框，也不显示 Web 默认焦点框。
- signup 模式允许键盘弹起时弹性滚动，登录模式保持原有紧凑布局。

### 技术与接口

- 新增 `GET /api/v1/auth/username-availability`，只返回目标用户名是否可用。
- 注册接口在邮箱冲突后继续检查用户名唯一性，返回 `409`。
- 新增移动端 `checkUsernameAvailability` API。
- 新增共享设计常量 `mobile/src/design/auth-layout.ts`。
- 新增 `mobile/src/features/account/display-name.ts`。
- 更新 `mobile/src/app/sign-in.tsx` 和首页问候调用。

### 验证

- 移动端全量：`7 files / 26 tests passed`
- TypeScript 类型检查：通过
- ESLint：通过
- 后端认证专项：`10 passed`
- Expo Web 生产导出：`dist-preview-v33` 构建成功
- 最后常驻预览服务重启被本机应用更新中断，需在环境恢复后补一次最终截图验收。

### 当前边界

- 用户名唯一性目前由注册事务内的应用层查询保障；并发注册的数据库唯一约束仍需单独迁移评估。
- 真实 iOS/Android 键盘行为已实现，但最终真机键盘截图尚未完成。

## v2.11.0 - 2026-11-21

### 交付主题

按用户确认的参考图精确重建 VeyaShip 登录页。

### 业务变化

- 登录页改为参考图中的轻量 iOS 构图：品牌主视觉、单句定位、两个输入框、一个主按钮和一个注册入口。
- 移除深色环境、运行时状态环、工作轨迹和所有额外叙事。
- 文案、按钮、协议说明和注册入口均按参考图复原。
- 主操作统一为“进入工作台”，邮箱、密码、服务协议和隐私政策保持完整语义。

### 设计与技术

- 新增参考图提取的透明品牌素材：`reference-logo.png`、`reference-wordmark.png`。
- 页面严格按参考图 `1044×2259` 比例换算，目标视口 `390×844`。
- 背景使用参考图对应的冷色柔和径向渐变，主按钮使用青绿到浅蓝渐变。
- 输入框、图标、圆角、阴影、间距和字号按参考图比例重建。
- 密码显隐、输入聚焦、按钮按压、错误提示和 reduced motion 已实现。
- 新增文件：`design-previews/2026-11-21-signin-agent-final/index.html`。

### 验证

- `375×812`：无横向或纵向溢出。
- `390×844`：与参考图逐项对照，品牌区、表单区、按钮、协议说明和注册入口位置一致。
- 密码显隐与焦点态通过内置浏览器实际操作验证。
- 样式 lint：`0 FAIL / 0 WARN`。
- 常驻预览：`http://127.0.0.1:4216/`

### 当前边界

- 当前为设计还原稿，未修改生产登录页面 `mobile/src/app/sign-in.tsx`。
- 创建账号流程、真实接口提交、错误回调和真机键盘避让尚未接入。

## v2.10.0 - 2026-11-21

### 交付主题

随身 Agent 登录页设计方向收敛，重建“一个手机、一个 Agent、一天工作”的首屏表达。

### 业务变化

- 对标 Manus、Devin 等 AI Agent 产品的真实登录页，确认登录任务应先于产品叙事。
- 推翻此前把时间轴、订单、客户、日结多段流程塞进登录首屏的方案。
- 新增单一登录候选：哑光石墨环境、真实 Logo、运行状态环、两行主张和底部登录面。
- 首屏文案压缩为“随时随地，工作不停”和一句能力说明，不再堆叠工作项列表。
- 保持登录/创建账号、邮箱、密码显隐、忘记密码和明确主操作完整可用。

### 设计与技术

- 新增 `design-previews/2026-11-21-signin-agent-final/index.html`。
- 使用真实 Logo `star-ark.png`，不重画品牌标识。
- 使用系统字体栈，仅保留标题、正文、按钮和元信息四级字号。
- 所有可见触控区域不小于 `44px`；`375×812` 和 `390×844` 均无横向或纵向滚动。
- 动效仅用于进入、Logo 状态环、分段切换、输入聚焦和按压反馈，并支持 reduced motion。

### 验证

- `375×812`：无横向溢出，首屏高度完整。
- `390×844`：无横向溢出，登录面完整落在安全区内。
- 登录/创建账号切换、密码显隐和焦点状态已通过内置浏览器实际操作验证。
- 预览服务：`http://127.0.0.1:4216/`

### 当前边界

- 当前仍是设计方向样机，未修改 `mobile/src/app/sign-in.tsx`。
- 尚未接入生产登录接口、错误态、加载态和真机键盘避让验收。

## v2.9.0 - 2026-11-21

### 交付主题

Temu LOCAL/SEMI 订单自动巡检、履约风险工作项和失败隔离。

### 业务变化

- 调度器每 15 分钟巡检 Temu LOCAL/SEMI 订单，不再依赖卖家主动查询。
- 履约警告或最迟发货时间进入 24 小时窗口时，订单自动进入 Agent 工作项。
- 工作项显示父订单号、商品数量、履约警告和最迟发货时间。
- 重复巡检更新原工作项，不产生重复任务。
- 所有订单行都返回发货时间后，旧工作项自动关闭。
- 跨境或未知店铺类型跳过自动巡检，不创建无依据任务。

### 技术与安全

- 新增 `temu_order_signal_sync` 服务和 `temu_order_signal_sync` 调度任务。
- 使用 `bg.order.list.v2.get`，要求 LOCAL/SEMI 类型和订单读取 scope。
- 每页读取 100 条，单次最多 20 页；全部页面成功后才保存巡检水位。
- 每个店铺使用独立租约，单店失败不阻塞其他店铺。
- 信号指纹按店铺和父订单号幂等，工作项不保存买家隐私或平台 Token。

### 验证

- 后端全量：`947 passed, 4 skipped`
- Temu 订单巡检定向：`7 passed`，服务覆盖率：`82%`
- Temu 巡检、只读、商品、scope、授权、Agent、信号和计划组合：`60 passed`
- 无新增数据库迁移

### 当前边界

- 自动巡检只生成工作项，尚未接 Temu 发货、物流、取消、退款或售后写回。
- 真实 LOCAL/SEMI 店铺、订单读取 scope 和响应字段仍需外部验收。
- 跨境订单接口边界继续保持明确拒绝，不宣称已支持。

## v2.8.0 - 2026-11-21

### 交付主题

Temu LOCAL/SEMI 订单只读、业务字段白名单和 Agent 订单查询。

### 业务变化

- Agent 可以查询授权 LOCAL/SEMI Temu 店铺的订单列表。
- 订单结果包含父订单号、状态、商品、SKU、数量、时间、履约警告和仓库摘要。
- 卖家可以按父订单状态筛选，并指定店铺与分页查询。
- 多店铺场景必须明确选择 Temu 店铺，不会混合店铺数据。
- 跨境或未知店铺类型会明确拒绝订单读取，不能用空列表伪装成功。
- 结果不返回买家姓名、地址、电话、邮箱或平台访问令牌。

### 技术与安全

- 新增 `TemuOrderReadService`。
- 新增 `GET /api/v1/platforms/temu/{connectionId}/orders`。
- 新增 Agent 工具 `search_temu_orders`。
- 首发只使用 `bg.order.list.v2.get`，要求订单读取 scope 且店铺类型为
  LOCAL/SEMI。
- 使用现有 Temu MD5 签名 POST 和分页参数，响应按业务字段白名单归一化。
- 空订单列表是正常成功结果；无权限、跨境限制和错误响应保持明确失败。

### 验证

- 后端全量：`940 passed, 4 skipped`
- Temu 订单、商品、scope、授权和 Agent 组合专项：`35 passed`
- 无新增数据库迁移

### 当前边界

- 尚未接 Temu 发货、取消、退款、售后、库存或价格写回。
- `bg.order.list.v2.get` 不支持部分跨境卖家，当前不宣称跨境订单已支持。
- 真实 LOCAL/SEMI 店铺、订单读取 scope 和响应字段仍需外部验收。

## v2.7.0 - 2026-11-21

### 交付主题

可撤销设备会话、短期访问令牌与自动续期。

### 业务变化

- 登录会话不再依赖 7 天不可撤销令牌。
- App 自动续期，正常使用无需重复登录。
- 退出当前设备后，旧访问令牌和旧刷新令牌立即失效。
- 新增退出全部设备。
- 改密或注销账号后，其他设备立即失效。
- 被撤销或过期的会话无法继续访问任何工作区。

### 技术与安全

- 访问令牌有效期 15 分钟，并绑定设备会话 `sid`。
- 刷新令牌为一次性不透明令牌，数据库只保存 SHA-256。
- 刷新令牌重放会撤销整个会话。
- 刷新使用条件更新，两个并发请求只有一个能成功。
- App 真机把访问令牌和刷新令牌放入 SecureStore。
- Web Axios 与 App Fetch 客户端均实现单飞自动刷新。
- 新增迁移 `079_user_sessions`。

### 验证

- 后端全量：`935 passed, 4 skipped`
- 认证会话核心服务覆盖率：`95%`
- Web：`55 files / 188 tests passed`，TypeScript 与生产构建通过
- 移动端：`5 files / 16 tests passed`，TypeScript 与 ESLint 通过

### 当前边界

- 真实 iOS Keychain、Android Keystore 重装恢复尚未验收。
- 生产多设备撤销、密钥轮换和事故演练尚未执行。

## v2.6.0 - 2026-11-21

### 交付主题

Temu 商品只读同步、业务字段归一化和 Agent 商品查询。

### 业务变化

- Agent 可以查询授权 Temu 店铺的商品列表。
- 商品结果包含名称、状态、价格、币种、缩略图、SKU、库存和规格。
- 没有商品读取 scope 时明确拒绝。
- 跨境或未知店铺类型使用 LOCAL/SEMI 商品接口时停止执行。
- 多店铺场景要求卖家指定 Temu 店铺，不会混合店铺数据。

### 技术与安全

- 新增 `TemuProductReadService`。
- 新增 `GET /api/v1/platforms/temu/{connectionId}/products`。
- 新增 Agent 工具 `search_temu_products`。
- 使用已有 Temu MD5 签名 POST `/openapi/router`。
- 首发只支持 `bg.local.goods.list.query`。
- 响应不包含 App Secret、Access Token、签名或网关内部参数。

### 验证

- 后端全量：`931 passed, 4 skipped`
- Temu 商品、scope、授权和 Agent 组合专项：`30 passed`
- 无新增数据库迁移

### 当前边界

- 尚未接 Temu 商品发布、编辑、上下架、价格或库存写回。
- 商品详情全量属性、图片转存和跨境兼容接口仍未接入。
- 真实 LOCAL/SEMI 店铺、商品读取 scope 和测试商品仍需外部验收。

## v2.5.0 - 2026-11-21

### 交付主题

Temu 授权 scope 能力矩阵与安全能力查询接口。

### 业务变化

- Temu 店铺不再只显示“已授权”，而是按真实 scope 展示可执行能力。
- 商品读取、发布、更新、库存、价格、订单、物流和售后分别计算。
- 跨境店铺使用 LOCAL/SEMI 接口时标记为需要确认，不直接开放。
- 未知店铺类型的 Temu 订单接口标记为受限。
- 没有对应 scope 的动作不会进入 Agent 可用能力。

### 技术与安全

- 新增 `derive_temu_capabilities` 权限映射服务。
- 新增 `GET /api/v1/platforms/temu/scopes`。
- 接口按当前用户和每个 Temu 连接独立返回能力摘要。
- 响应不包含 Access Token、加密凭据或 API Secret。
- 权限矩阵只表示授权范围，不替代真实接口预检和测试店铺验收。

### 验证

- 后端全量：`921 passed, 4 skipped`
- Temu 授权、scope 和平台能力专项：`17 passed`
- 无新增数据库迁移

### 当前边界

- 尚未执行 Temu 商品、订单、库存、价格或物流写操作。
- 真实 Temu 应用 scope、店铺类型和测试店铺仍需外部验收。

## v2.4.0 - 2026-11-21

### 交付主题

全量工作区隔离收口、私有媒体签名 URL 与工作区级自动化/监控设置。

### 业务变化

- 团队和个人工作区的图片、视频、营销、Agent、批量和运营数据不再互相串读。
- 图片与视频封面改为短时签名访问，复制裸 UUID 地址不能直接读取。
- Agent 在团队工作区创建的商品、媒体任务和营销项目写入团队工作区。
- 团队修改自动化开关或毛利/库存阈值不会影响个人工作区。
- Shopify 渠道列表、解绑和 Webhook 事件只能进入明确工作区。
- 客服自动值班任务和后台执行结果不会写入其他工作区对话。

### 技术与数据

- 新增 `media_tokens` 服务，媒体令牌绑定资源类型、资源 ID、用户和工作区，有效期 15 分钟。
- 图片 API 新增稳定 `file_path`，前端只把它写入商品主图和 SKU 图片字段；`image_url` 仅用于展示。
- 图片、视频和营销视频幂等约束改为 workspace + user + key。
- 自动化偏好和执行状态迁移到工作区级新表，旧用户级表保留回滚周期。
- 运营监控阈值迁移到 `workspace_monitor_settings`。
- 历史对话、AgentTask、Persona、批量、媒体和营销记录通过 `075` 幂等回填个人工作区。
- Alembic head：`078_workspace_monitor_settings`。

### 验证

- 后端全量：`921 passed, 4 skipped`
- 全仓库覆盖率：`72%`
- 共享工作区/媒体令牌/自动化/运营摘要核心逻辑覆盖率：`86%`
- 媒体、图片、视频、营销与签名 URL 组合：`120 passed`
- 自动化偏好、监控设置与迁移组合：`22 passed`
- Web：`55 files / 186 tests passed`，TypeScript 与生产构建通过
- 移动端：`4 files / 13 tests passed`，TypeScript 与 ESLint 通过

### 当前边界

- 全仓库覆盖率未达到 80%，仍需补旧 API、路由和爬虫测试。
- 真实对象存储/CDN、Shopify、Amazon、Temu、邮件和 APNs/FCM 尚未验收。
- 生产 PostgreSQL `074 → 078` 变更窗口与回滚演练仍待执行。
- 前端 ESLint 仍因本地缺少 `eslint` 可执行文件而未运行。

## v2.3.0 - 2026-11-20

### 交付主题

App 工作区素材到 Amazon Listing 图片的 Agent 发布与绑定闭环。

### 业务变化

- Agent 可以直接选择当前工作区图片素材，生成 Amazon 主副图发布计划。
- 第一张素材作为 Amazon 主图，其余按顺序作为副图，最多 9 张。
- 动作确认前不会公开私有图片。
- App 预览明确提示所选素材会变成 Amazon 可访问的公网图片。

### 技术与安全

- 新增 `amazon.listing.media.attach_assets` 待确认动作。
- 新增 `AmazonListingAssetMediaAdapter`，负责素材校验、公网发布和 Amazon 绑定。
- 素材发布后立即执行 Amazon 图片 `VALIDATION_PREVIEW`，再正式 PATCH。
- 只接受当前工作区未删除图片素材。
- 公共对象键按工作区和素材 ID 确定性生成，重复执行保持同一 URL。
- Amazon 图片定位器回读一致后才标记完成。

### 验证

- 后端全量：`915 passed, 4 skipped`
- 素材图片、公共托管、Amazon 图片绑定、动作预览和 Agent 组合专项：`40 passed`
- 无新增数据库迁移

### 当前边界

- 真实公共 CDN/S3 和 Amazon 图片抓取仍需外部环境验收。
- 不支持视频、A+ 内容、客户隐私附件或自动裁剪。

## v2.2.0 - 2026-11-20

### 交付主题

公共图片素材托管、移动端显式发布接口和历史迁移兼容修复。

### 业务变化

- 工作区 owner、admin 或 operator 可以把私有图片素材显式发布为持久 HTTPS URL。
- 公共 URL 可直接用于 Amazon Listing 图片绑定。
- 公共发布不改变原图片的私有读取权限。
- 重复发布同一素材返回相同 URL。

### 技术与安全

- 新增 `S3PublicImageStorage` 和 `publish_public_image_asset`。
- 新增 `PUBLIC_MEDIA_BASE_URL`、`PUBLIC_MEDIA_S3_BUCKET` 和
  `PUBLIC_MEDIA_PREFIX` 配置。
- 新增移动接口
  `POST /api/mobile/v1/workspaces/{workspaceId}/assets/images/{assetId}/public-url`。
- 对象键绑定工作区和素材 ID，不暴露用户私有目录路径。
- 公共对象使用图片 Content-Type 和一年不可变缓存策略。
- `074_agent_workspace_idem` 兼容历史 drift 库中缺少 `agent_tasks` 或
  `workspace_id` 的情况。

### 验证

- 后端全量：`894 passed, 4 skipped`
- 公共图片、移动素材库、对象存储和迁移专项：`7 passed`
- 无新增数据库迁移

### 当前边界

- 尚未配置真实公共 CDN/S3 Bucket，也未验收 Amazon 实际抓图。
- 不支持视频、附件或客户隐私文件公共发布。
- 公共对象生命周期、缓存刷新和删除策略仍需生产配置。

## v2.1.0 - 2026-11-20

### 交付主题

今日计划顶部改为 iOS 紧凑摘要，移除彩色分段进度条。

### 业务与视觉变化

- 保留 `今天` 标题、3 项安排总数和待决定/处理中/观察中三个数量。
- 删除横向彩色 workload bar，避免顶部像 KPI 仪表盘。
- 三项状态收进一个轻量摘要胶囊，使用低饱和状态点和细分隔线。
- 决策卡继续作为页面唯一主角，“查看并确认”为唯一主动作。
- 下方 Agent 进度分组、日结行和跳转行为不变。

### 技术与设计

- `PlanAgenda` 移除 distribution track 和独立 legend 样式。
- 新增 compact summary、metric 和 divider 样式。
- 更新 `DESIGN.md`，明确禁止今日计划重新引入 segmented workload bar 或独立状态图例。

### 验证

- 移动端 TypeScript：通过
- 移动端 ESLint：通过
- 移动端测试：`4 files / 13 tests passed`
- Expo Web 生产导出：通过
- 实拍检查：375×812、390×844
- 截图：`mobile/artifacts/today-plan-compact-summary-2026-11-20/`
- 内部浏览器预览：`http://127.0.0.1:4211/plan?workspaceId=99999999-9999-4999-8999-999999999999`

### 已知边界

- 本轮使用 Expo Web 实拍验证，没有重新生成 iOS/Android 原生安装包。
- 空状态、错误状态和加载状态未单独重新截图，布局代码未改动。

## v2.0.0 - 2026-11-20

### 交付主题

Amazon Listing 持久图片 URL 绑定、图片定位器回读和 Agent 媒体动作。

### 业务变化

- 卖家可以通过 Agent 把主图和副图 URL 绑定到已有 Amazon Listing。
- 支持 1 张主图和最多 8 张副图。
- 临时签名 URL、localhost、内网 IP、本地路径和含账号凭据的地址会被拒绝。
- App 预览展示 SKU、Marketplace、图片数量和持久 URL 风险提示。

### 技术与安全

- 新增 `amazon.listing.media.attach` 待确认动作。
- 新增 `AmazonListingMediaAttachAdapter`，负责 URL 校验、PATCH 和回读。
- 仅 PATCH `main_product_image_locator` 和
  `other_product_image_locator_1` 至 `_8`。
- 图片 URL 只接受持久 HTTPS 或 `s3://` 地址。
- 提交前使用 Listings Items `VALIDATION_PREVIEW`。
- 回读不到一致图片定位器时保持可恢复，不把 ACCEPTED 当成成功。

### 验证

- 后端全量：`849 passed, 4 skipped`
- Amazon 图片、内容、动作预览和 Agent 组合专项：`37 passed`
- 无新增数据库迁移

### 当前边界

- 不从 App 私有素材目录直接上传二进制文件。
- 没有公共 CDN/S3 图片托管链路。
- 不支持视频、A+ 内容和变体图库。
- 真实公共 URL、Amazon 图片抓取和测试 Listing 仍需平台侧验收。

## v1.9.0 - 2026-11-20

### 交付主题

Amazon Listing 标题、描述和卖点的局部更新、回读与 Agent 编辑。

### 业务变化

- 卖家可通过 Agent 修改 Amazon Listing 标题、描述和卖点。
- 更新只提交发生变化的正文属性，不覆盖价格、库存、图片和合规字段。
- App 预览显示 SKU、Marketplace 和发生变化的字段。
- Amazon 回读一致后才更新本地 Listing；本地版本递增，旧合规结果失效。

### 技术与安全

- 新增 `amazon.listings.update` 待确认动作。
- 新增 `AmazonListingContentUpdateAdapter`，负责字段校验、PATCH 和回读。
- 仅允许 PATCH `item_name`、`product_description` 和 `bullet_point`。
- 提交前调用 Listings Items `VALIDATION_PREVIEW`。
- 标题最多 200 字符，描述最多 2000 字符；至少提供一个变更字段。
- 回读成功后使用本地 Listing 更新逻辑递增版本并恢复待合规状态。

### 验证

- 后端全量：`844 passed, 4 skipped`
- Amazon 内容、库存、售价、动作预览和 Agent 组合专项：`38 passed`
- 无新增数据库迁移

### 当前边界

- 不支持图片、视频、A+ 内容和变体关系更新。
- 不支持跨 Marketplace 批量同步。
- 真实 Product Type 属性约束和测试 Listing 仍需平台侧验收。

## v1.8.0 - 2026-11-20

### 交付主题

Amazon Listing 库存与售价受控 PATCH、属性回读和 Agent 运营动作。

### 业务变化

- 卖家可通过 Agent 准备 Amazon Listing 库存更新。
- 卖家可通过 Agent 准备 Amazon Listing 售价更新。
- 库存和售价使用两个独立动作，调价不会顺带覆盖库存，反之亦然。
- App 预览显示 SKU、Marketplace、变更前后值和属性级风险提示。
- 回读值不一致时动作保持可恢复，不把 ACCEPTED 当成最终成功。

### 技术与安全

- 新增 `amazon.inventory.update` 与 `amazon.pricing.update` 动作定义。
- 新增 `AmazonOfferUpdateAdapter`，实现预检、PATCH、执行和属性回读。
- 使用 Listings Items `2021-08-01` 的 `patchListingsItem`。
- 库存仅更新 `/attributes/fulfillment_availability`。
- 售价仅更新 `/attributes/purchasable_offer`。
- 提交前使用 `mode=VALIDATION_PREVIEW`，提交后读取
  `summaries,attributes,issues`。
- 不重新提交标题、描述、图片、合规字段或其他未变更商品属性。
- 库存必须是非负整数；售价必须大于 0 且包含币种。

### 验证

- 后端全量：`835 passed, 4 skipped`
- Amazon 库存、售价、动作预览和 Agent 组合专项：`41 passed`
- 无新增数据库迁移

### 当前边界

- 不支持促销价、企业价、多地点库存或批量改价。
- 真实 Listings Items 角色、不同 Product Type 属性约束和测试 Listing 仍需验收。

## v1.7.0 - 2026-11-20

### 交付主题

Amazon FBM 受控确认发货、物流单号回读与 Agent 发货计划。

### 业务变化

- Agent 可以读取 Amazon 订单剩余可发商品，并准备发货待确认动作。
- 卖家确认后向 Amazon 提交承运商、物流单号、发货时间和订单商品数量。
- 提交成功后读取订单 `FULFILLMENT` 和 `PACKAGES`，只有相同物流单号出现才
  标记动作完成。
- 找不到物流单号时保持可恢复状态，不把 HTTP 204 或订单状态变化当成该包裹
  发货成功。
- FBA、已取消、已全部发货和不可履约订单不能进入确认发货动作。
- 其他承运商缺少承运商名称时停止执行。
- App 预览只展示订单号、Marketplace、承运商、物流单号、发货日期和商品数量。

### 技术与安全

- 新增 `amazon.orders.fulfill` 高风险动作定义，默认需要用户确认。
- 新增 `AmazonOrderFulfillmentActionAdapter`，负责预检、执行和外部回读。
- 发货提交使用 Orders v0
  `POST /orders/v0/orders/{orderId}/shipmentConfirmation`。
- 订单回读使用 Orders `2026-01-01`
  `GET /orders/2026-01-01/orders/{orderId}?includedData=FULFILLMENT,PACKAGES`。
- `packageReferenceId` 强制为正整数字符串，商品数量按 Amazon 剩余未发数量计算。
- 不请求或返回买家姓名、邮箱、电话、地址、付款和税务数据。
- 动作运行时保留幂等键、确认人、前后快照、失败状态和重试入口。

### 验证

- 后端全量：`823 passed, 4 skipped`
- Amazon 发货、订单、发布、动作预览、Agent 和调度组合专项：`59 passed`
- Amazon 发货动作专项：`7 passed`
- 无新增数据库迁移

### 当前边界

- 未接 Easy Ship、Amazon Buy Shipping 或自动购买面单。
- 真实承运商代码、NA/EU/FE 测试订单和 Amazon Orders 角色仍需外部验收。
- Amazon 退款、价格、库存和客服动作仍未进入移动 Agent 动作运行时。

## v1.6.0 - 2026-11-20

### 交付主题

Amazon FBM 订单监控、Agent 订单查询和 Amazon 多区域发布修复。

### 业务变化

- Agent 可以查询 Amazon 商户自履约订单，并回答待发货、部分发货、已发货和取消状态。
- 未发货 Amazon 订单会自动进入移动 Agent 时间线，生成订单异常工作项。
- 订单等待超过 24 小时提升为注意，超过 48 小时提升为紧急。
- 已发货、已取消或不可履约订单会自动关闭对应旧任务。
- FBA 订单不会误生成“卖家待发货”任务。
- Amazon Listing 发布现在按 Marketplace 自动选择 NA、EU 或 FE 域名。

### 技术与数据

- 接入 Amazon Orders API `2026-01-01`，使用 `searchOrders` 增量查询。
- 只请求 `includedData=FULFILLMENT`，不请求买家、收件地址、付款或税务数据。
- 每个 Amazon 连接使用独立 `IntegrationCursor` 和跨进程同步租约。
- 首次同步回看最近 7 天，后续从成功游标回退 10 分钟继续同步。
- 单次同步最多处理 5 页、每页 100 单，防止耗尽 Amazon 低速率额度。
- Amazon 限流时不推进游标；401/403 会将连接标记为 `invalid` 并生成重连任务。
- Agent 工具 `search_amazon_orders` 只返回订单号、Marketplace、履约状态、
  商品数量、SKU 和时间。
- Amazon Listing Items 发布与回读复用统一区域解析，不再固定美国域名。

### 验证

- 后端全量：`809 passed, 4 skipped`
- Amazon 订单、发布、授权、Agent 和调度组合专项：`60 passed`
- Amazon 订单监控专项：`9 passed`
- 无新增数据库迁移

### 当前边界

- Amazon 订单发货确认、承运商选择和物流单写入尚未接入。
- 真实 Orders 角色、NA/EU/FE 测试店铺和限流额度仍需外部验收。
- Amazon 退款、价格、库存和客服动作仍未进入移动 Agent 动作运行时。

## v1.5.0 - 2026-11-20

### 交付主题

Amazon 移动 Agent Listing 发布、Temu 授权基础层与平台连接设置。

### 业务变化

- Agent 可以为 Amazon Listing 生成待确认发布动作，不再直接提交平台。
- Amazon 发布前执行 Listings Items 预检，卖家确认后提交。
- 发布后按卖家 ID、SKU 和 Marketplace 回读；没有达到可售状态时保持验证中。
- Temu 支持 US、EU、GLOBAL 三个区域的店铺授权和连接测试。
- 跨境卖家可以从 Temu 卖家中心复制 Access Token，在设置页验证并绑定店铺。
- 平台连接页同时展示 Amazon 与 Temu 的真实连接状态。
- 平台能力矩阵明确区分“已授权”“可发布”和“完整日常闭环”。

### 技术与安全

- 新增 `amazon.listings.publish` 动作运行时适配器、动作预览和 Agent 工具。
- Amazon 动作复用卖家 Refresh Token，但只使用工作区 owner 或当前确认人的连接。
- 新增 Temu MD5 签名器、区域网关、回调授权、Token 交换和店铺验权。
- Temu App Secret 与卖家 Access Token 不进入 URL、日志、App 响应或明文数据库字段。
- Temu Access Token 使用现有加密能力保存，连接列表只返回脱敏业务字段。
- 新增 Temu 服务商配置与管理员设置入口。
- 修复付费套餐开通后额度周期被清空、导致下一次余额读取重复补发的问题。
- 批量 Listing、视频和营销分镜测试夹具迁移到工作区钱包唯一事实源。

### 验证

- 后端全量：`799 passed, 4 skipped`
- Amazon 与 Temu 平台专项：`31 passed`
- 套餐、批量扣费和账本专项：`21 passed`
- MiniMax、即梦、营销视频与专业分镜专项：`81 passed`
- Web：`186 tests passed`，TypeScript 与生产构建通过
- 移动端：`4 files / 13 tests passed`
- 移动端 TypeScript 与 ESLint：通过
- 前端 ESLint 未运行：当前 `frontend/node_modules` 缺少本地 `eslint` 可执行文件

### 当前平台边界

- Shopify：唯一具备移动 Agent 商品、订单、履约、退款、库存、价格和客服完整闭环的平台。
- Amazon：已具备授权和受控 Listing 发布；订单、履约、退款、价格、库存和客服尚未接入。
- Temu：已完成授权与验权基础层；商品、订单、履约和售后仍受开放平台权限包及店铺类型限制。
- 真实 Amazon/Temu 卖家授权、测试店铺和外网验收尚未执行，不能宣称真实平台闭环完成。

## v1.4.0 - 2026-11-20

### 交付主题

多订单候选选择、订单关联纠错和平台能力澄清。

### 业务变化

- 客户邮箱匹配到多个订单时，Agent 暂停生成物流回复。
- App 展示订单号、支付状态、履约状态和物流摘要供卖家选择。
- 卖家选择订单后，Agent 重新校验订单并自动继续生成回复。
- 已关联订单允许切换到其他候选订单。
- 换单会取消旧草稿、待确认回复和尚未执行的发送动作。
- 订单选择来源和切换前后订单号写入工作项事件。
- 新增平台能力矩阵，明确 Shopify、Amazon、TikTok、Temu 和 SHEIN 的真实边界。

### 技术变化

- 订单候选只保留脱敏业务字段，不包含客户邮箱、地址或电话。
- 候选选择接口重新查询当前工作区 Shopify 店铺，避免使用过期候选。
- 订单候选写入工作项结构化结果，App 不依赖临时内存。
- AgentTask 幂等逻辑支持任务完成后因订单重选而安全复用入队记录。
- 多订单工作项使用 `choose` 动作，不再显示普通确认按钮。

### 验证

- 后端全量：`774 passed, 4 skipped`
- 订单关联与自动值班专项：`18 passed`
- 移动端：`4 files / 13 tests passed`
- TypeScript、ESLint、Expo Web 构建：通过
- 已视觉检查双订单候选、支付/履约状态和物流摘要

### 当前平台边界

- Shopify：唯一具备移动 Agent 完整商品、订单、履约、退款、库存和客服闭环的平台。
- Amazon：已有 Seller Central OAuth 和部分 SP-API Listing 发布，尚未进入移动 Agent 的订单、履约、退款等写操作闭环。
- TikTok Shop：当前主要是内容和营销能力，尚无真实店铺铺货闭环。
- Temu、SHEIN：尚未接入开放平台授权与发布。
- IMAP/SMTP 与 Judge.me：作为独立客户沟通和评价渠道，不是铺货平台。

## v1.3.0 - 2026-11-20

### 交付主题

客户会话与 Shopify 订单事实自动关联。

### 业务变化

- 物流、订单状态和售后问题会先查询当前工作区中的真实 Shopify 订单。
- 只有唯一匹配订单时才自动关联，并把支付、履约和物流事实传给 Agent。
- 多店铺、多订单或查询失败时不会编造物流状态，自动降级为人工确认。
- 没有订单事实的物流问题会询问订单号或等待卖家处理。
- App 任务详情显示订单号、支付状态、履约状态和物流单号。
- 物流单号存在链接时可直接从任务详情打开承运商追踪页。

### 技术与数据

- 新增 `customer_order_links` 订单事实快照表。
- 新增迁移 `071_customer_order_links`。
- Shopify 查询只限当前工作区已启用店铺，并使用完整规范化邮箱精确匹配。
- 客户邮箱只在服务端解密，不进入模型事实、动作预览或 App 响应。
- 订单查询失败只影响自动回复级别，不阻断客户消息和人工确认。
- AgentTask 自动值班会在生成物流草稿前调用订单解析器。
- 修复并行新增的 `072_user_workspace_lifecycle` 在历史漂移 SQLite 库上的兼容性。

### 验证

- 后端全量：`769 passed, 4 skipped`
- 订单关联、Worker、AgentTask、调度和迁移组合专项：`55 passed`
- 移动端：`4 files / 13 tests passed`
- TypeScript 类型检查：通过
- ESLint：通过
- Expo Web 预览构建：通过
- 已视觉检查订单号、支付/履约状态和物流单号展示

### 已知边界

- 多订单场景目前不会自动猜测，后续需要 App 内订单选择。
- 真实 Shopify 订单读取需要生产店铺授权和受保护客户数据权限验收。
- 订单关联纠错、手动换单和历史订单选择尚未实现。

## v1.2.0 - 2026-11-20

### 交付主题

Agent 自动值班 Worker 与客户回复自动入队。

### 业务变化

- 客户邮件同步后，Agent 会自动领取客服工作项，不再要求卖家先发指令。
- Agent 会读取最新客户消息、语言、意图、会话主题和关联订单/商品标识。
- 普通客服问题自动生成可编辑回复草稿，并进入等待确认或自动发送队列。
- 低风险售前问题可直接按工作区策略进入发送队列。
- 物流和订单问题只有在存在关联订单事实时才允许自动发送。
- 退款、质量、延迟、投诉、法律和隐私问题保留人工确认或接管。
- 人工接管后 Worker 不再生成或发送回复。

### 技术与调度

- 复用现有 `agent_tasks` 持久队列，没有新增第二套任务系统。
- 新增 `customer_reply` AgentTask 类型，任务成本为 0。
- 调度器每 5 秒扫描待处理客服工作项，并使用独立跨进程锁入队。
- 同一工作项和同一客户消息使用稳定幂等键，不重复建任务、草稿或动作。
- AgentTask 继续复用现有抢占、僵尸任务恢复和并发限制。
- 新增 `AgentOrchestrator` 之外的专用客服草稿生成器，事实与表达分离。
- 草稿生成失败会把工作项置为可重试，不伪造 Agent 成功。

### 验证

- 后端全量：`750 passed, 4 skipped`
- 自动值班、调度、风险、邮件和动作组合专项：`37 passed`
- 移动端：`4 files / 13 tests passed`
- TypeScript 类型检查：通过
- ESLint：通过

### 已知边界

- 自动发送效果依赖真实工作区自主策略和真实邮件渠道。
- 订单事实关联仍取决于上游订单与客户会话绑定质量。
- 真实模型回复质量、邮件送达和真机通知仍需外部环境验收。

## v1.1.0 - 2026-11-20

### 交付主题

邮件客服附件、退信对账与移动端附件预览。

### 业务变化

- 卖家收到的客户邮件附件会自动进入私有素材存储，不需要回 Web 下载。
- 系统过滤可执行文件和未知高风险附件，单封邮件最多接收 5 个安全附件。
- 卖家可在 App 客服任务中看到附件名称，并预览图片附件。
- Agent 发送客服回复时，可携带当前工作区的图片附件。
- 邮件退信会回写原外发消息为 `bounced`，记录投递错误码和诊断信息。
- 退信会生成一个高优先级卖家处理项，提示检查客户邮箱或改用其他渠道。
- 系统不会把 SMTP“已受理”或普通发送成功误报为真实送达。

### 技术与数据

- 新增 `customer_attachments` 表，附件同时绑定工作区、会话和消息。
- `customer_messages` 增加投递错误码和诊断信息字段。
- 新增迁移 `070_customer_attachments`，接在
  `069_billing_reconciliation_control` 之后。
- IMAP MIME 解析支持安全附件提取、附件总大小限制和危险扩展名过滤。
- SMTP MIME 发送支持多张图片附件，不在动作预览中暴露对象路径。
- 客户附件通过工作区鉴权接口读取，使用私有对象存储键，不包含客户邮箱。
- App 客服上下文新增附件摘要和图片全屏预览。

### 验证

- 后端全量：`742 passed, 4 skipped`
- 邮件附件、退信、动作预览和迁移专项：`24 passed`
- 移动端：`4 files / 13 tests passed`
- TypeScript 类型检查：通过
- ESLint：通过
- Expo Web 预览构建：通过
- 已视觉检查附件标签、图片全屏预览和关闭交互

### 已知边界

- 真实邮件服务送达回执仍需供应商回执或真实邮箱环境验收。
- 当前外发附件支持工作区图片；PDF 和批量多附件管理留待后续版本。
