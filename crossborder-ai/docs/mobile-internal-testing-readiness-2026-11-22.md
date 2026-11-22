# VeyaShip App 内测打包与远程提交审计报告

> 审计日期：2026-11-22  
> 审计范围：`crossborder-ai/mobile`、移动端依赖与构建配置、后端移动接口、通知与深链、Git 跟踪状态、敏感文件与生成物。  
> 结论口径：保留原始发布前审计，并在顶部补充本轮可验证的修复与剩余阻塞。

## 最新复核（2026-11-22）

本轮已完成 EAS UI 预览构建链路，并保留真实内测包的发布门禁：

| 检查项 | 最新状态 | 证据 |
| --- | --- | --- |
| EAS 项目关联 | 已解决 | `@felix-ai/veyaship-agent`，projectId `85dd918e-3671-4472-be2b-dcdb951c3930` |
| GitHub 仓库连接 | 已解决 | `felixfeng-ai/crossborder-ai`，Base directory 为 `crossborder-ai/mobile` |
| 原生依赖 | 已解决 | `expo-doctor` 为 `20/20` |
| App 法律与隐私中心 | 已解决 | 登录、账号和注册页均提供入口，覆盖 7 份公开文档 |
| AI 内容告知 | App 内已解决 | 登录告知和注册显式勾选均包含《AI 使用说明》 |
| 原生法律正文 | 已解决 | 七份协议离线内置，不再跳转 Web，保留版本和生效日期 |
| 账号页可达性 | 已解决 | 页面可滚动到底部，首屏提供切换账号入口 |
| UI 预览构建 | 已可用 | `ui-preview` 解析成功，Android 输出 APK，预览模式为 `true` |
| 真实 API 门禁 | 已加固 | 缺少 HTTPS API 时 EAS 真实构建直接失败，不再生成无效包 |
| 测试 API | 已解决 | 生产移动 API 已上线，未登录 bootstrap 正确返回 `401` |
| 真实登录 | 已解决 | 生产注册、登录和 bootstrap 已通过，返回 1 个工作区 |
| Android 真实内测包 | 已解决 | EAS `preview` APK 构建成功，versionCode `5` |
| APNs/FCM | 仍阻塞 | 缺少 Apple/Google 推送凭据 |
| iOS/Android 签名 | 部分可用 | Android 托管 Keystore 已创建；iOS 仍需 Apple Developer 凭据 |
| 真机端到端 | 待执行 | APK 已生成，仍需在真实 Android 设备安装并验收 |
| 平台真实写操作 | 未完成 | 需要 Amazon/Temu 等测试店铺与开放平台权限 |
| 同意版本服务端留痕 | 未完成 | 当前客户端完成告知与勾选，尚未写入服务端审计表 |

### Expo 网页版构建方式

1. 打开 [VeyaShip Agent](https://expo.dev/accounts/felix-ai/projects/veyaship-agent)。
2. Git 分支选择 `codex/veyaship-mobile-internal-build`。
3. Base directory 填 `crossborder-ai/mobile`。
4. 在 Build 中选择 Android。
5. Build profile 选择 `ui-preview`。
6. 构建完成后安装 internal distribution APK，直接查看 App 界面与核心页面。
7. 如需真实登录，先给 `preview` 环境配置
   `EXPO_PUBLIC_API_URL=<当前移动 API 的 HTTPS 根地址>`，再切换到 `preview` 档位。

`ui-preview` 只用于界面验收，不代表真实账号、真实店铺、推送或后台 Agent 已通过
端到端验收。

### 分支与发布规则

- `main` 是唯一发布主线，只接收通过验证的 PR，不从功能分支直接发布。
- 功能开发使用 `codex/<scope>` 分支；当前移动端验收分支为
  `codex/veyaship-mobile-internal-build`。
- UI 验收阶段允许从功能分支构建 `ui-preview` APK，但不得把该包标记为正式内测
  或生产版本。
- 合并 `main` 前必须确认移动端源码、后端移动 API、数据库迁移和部署配置属于同
  一个可运行版本。
- 合并 `main` 后创建版本标签，例如 `mobile-v1.0.0`，正式 `preview` 和
  `production` 构建只允许从 `main` 或对应发布标签发起。
- 每次发布必须保留构建编号、EAS Build 链接、变更报告和真机验收记录。

## 一、结论

当前版本不适合直接发送给外部内测用户。

主要不是因为页面功能不够，而是发布链路还没有闭合：

1. 生产环境变量文件已被 Git 跟踪，包含已经填充的密钥字段，必须按已泄露风险处理。
2. 整个 `mobile` 目录当前有 `0` 个文件被 Git 跟踪，无法从远程分支复现。
3. `expo-doctor` 检查为 `19/20`，缺少两个原生必需 peer dependency，离开 Expo Go 后可能崩溃。
4. 内测构建没有配置可访问的 HTTPS API、EAS projectId、推送凭据和版本号策略。
5. 当前没有 `.ipa`、`.apk` 或 `.aab`，也没有真机安装、签名、推送和深链验收证据。

当前可以定义为“开发候选版本”，不能定义为“可分发的内测候选版本”。

## 二、P0 阻断项

### P0-1 生产密钥文件已被跟踪

`crossborder-ai/.env.production` 已被当前 Git HEAD 跟踪。文件中存在非空的应用、JWT、数据库和模型服务密钥字段，同时保留了支付与平台授权字段：

- 应用与 JWT 密钥
- 数据库密码
- 模型服务 API Key
- 支付、图片服务和平台授权配置字段

本次审计没有读取或输出具体值。风险判断为：

- 只要该文件曾经推送到远程，就需要假定凭据已经暴露。
- 仅新增 `.gitignore` 不能解决问题，因为 Git 仍会跟踪已有文件，历史提交中也仍然保留。
- 必须先轮换密钥，再清理当前树和历史记录，最后才能继续使用相关环境。

需要的处理方向：

1. 轮换 `.env.production` 中全部非空密钥，优先处理 JWT、数据库、模型和平台授权。
2. 从 Git 跟踪中移除真实环境文件。
3. 使用 `git filter-repo` 或 BFG 清理历史，并协调所有协作者重新克隆。
4. 把真实值迁移到部署平台 Secret、EAS Environment Variables 或服务器环境。
5. 保留 `.env.example`，确保其中只有占位值。

### P0-2 移动端尚未进入 Git

当前仓库根目录是：

```text
D:\Project
```

不是项目目录本身。`crossborder-ai/mobile` 当前被 Git 跟踪的文件数量为 `0`。

影响：

- 其他人从远程分支无法获得 App 源码。
- EAS 云构建无法从远程仓库构建当前 App。
- 本地工作区一旦丢失，移动端全部变更都没有版本历史。
- 根仓库还包含多个无关同级项目，直接执行 `git add .` 可能把其他项目一起提交。

正确方式必须是显式白名单暂存，例如只处理 `crossborder-ai/mobile` 下的必要源码和配置；不要从 `D:\Project` 执行 `git add .`。

### P0-3 原生依赖检查未通过

实际执行：

```text
npx expo-doctor
```

结果为 `19/20` 通过，失败项：

- 缺少 `expo-asset`
- 缺少 `react-native-worklets`

`expo-asset` 是 `expo-audio` 的必需 peer dependency；  
`react-native-worklets` 是 `react-native-reanimated` 的必需 peer dependency。

风险：在 Expo Go 内不一定暴露，但独立原生包可能启动失败或运行时崩溃。

### P0-4 内测 API 和 EAS 项目未配置

当前 `mobile/app.config.ts` 的默认 API 地址是：

```text
http://127.0.0.1:8000
```

`mobile/eas.json` 的 `preview` profile 没有注入环境变量。

影响：

- 真机安装后会访问手机自己的回环地址，无法连接开发电脑。
- Android 只对模拟器做了 `10.0.2.2` 替换，物理 Android 手机也不会命中。
- 登录、时间线、任务和通知都会失败。

同时，仓库中没有稳定的 EAS projectId 配置。推送注册逻辑在缺少 projectId 时会直接返回：

```text
if (!projectId) return;
```

结果是 App 可以运行站内通知，但不会注册 Expo Push Token，外部推送实际不可用。

### P0-5 原生构建、签名和安装尚未验证

当前没有发现任何 `.ipa`、`.apk` 或 `.aab`。

还未验证：

- Apple Developer / App Store Connect 记录
- Android 包名 ownership
- iOS Bundle ID ownership
- EAS 账号和项目归属
- iOS Distribution Certificate 与 Provisioning Profile
- APNs Key
- Android Keystore 与 FCM 凭据
- TestFlight 或 Ad Hoc 设备注册
- Android 内测安装包分发

当前 `mobile/eas.json` 已有 `development`、`preview`、`production` 三个 profile，这是正确基础，但还没有形成真实构建证据。

## 三、P1 内测前应修项

### 1. 网络错误可能被显示成业务结果

- 任务详情在无数据时直接显示“这件事已经处理或已失效”。
- Agent 执行详情在无数据或请求失败时会把 `!item` 当作“正在处理”。

这会把网络失败误判为业务状态，内测用户无法区分“网络断了”和“任务真的失效/仍在运行”。

建议为查询错误增加独立状态：说明网络失败、保留重试，不伪造成功、处理中或已失效。

### 2. 请求没有统一超时和离线策略

移动端 API 使用原生 `fetch`，没有统一的超时、取消或离线分类。

内测风险：

- 弱网下按钮可能长时间无反馈。
- 后台切换网络后请求可能悬挂。
- 用户重复点击可能增加重复提交概率，虽然后端有幂等键兜底。

### 3. 没有移动端崩溃和性能监控

后端已有 Sentry 和请求链路基础，但 App 内没有发现 Sentry、Crashlytics、全局错误边界或 ANR/卡顿监控。

内测用户遇到白屏、原生崩溃或启动失败时，团队无法获得足够诊断信息。

### 4. 推送只完成了代码链路，没有真实送达证据

后端已经有设备注册、通知 Outbox、安静时段和 Expo Push Sender。  
但当前还缺：

- EAS projectId
- APNs/FCM 生产凭据
- 真机 token 注册验证
- 前台、后台、冷启动通知点击验证
- 无效 Device Token 清理验证

另外，用户登录后会立即请求通知权限，没有解释页或延后触发。内测用户更容易直接拒绝权限。

### 5. 真机 E2E 尚未执行

当前移动端验证以单元测试、类型检查、lint 和 Expo Web 截图为主。

还没有 iOS/Android 真机证据：

- 相机拍照
- 相册权限
- 麦克风录音
- 语音上传
- 图片上传
- 图片替换和删除
- 深链冷启动
- 通知点击
- 后台回到前台后的 SSE 恢复
- 键盘和底部安全区
- 动态字体和屏幕阅读器

### 6. 字体加载失败时可能是空白页

根布局在字体未加载时只返回空 `View`，没有超时、错误状态或系统字体降级。

另外，两个中文 TTF 文件分别约 `10.5 MB`，合计约 `21 MB`。内测可以接受，但会明显增加安装包大小和首次启动成本。

### 7. 存在未使用的原生依赖

当前依赖中未发现业务代码直接使用：

- `expo-camera`
- `expo-sqlite`
- `expo-haptics`
- `expo-updates`
- `@shopify/flash-list`

其中部分可能用于后续规划，但当前会增加原生构建面、升级成本和包体风险。内测版应区分“立即必需”和“后续能力”。

### 8. EAS Update 和预览版本号未闭环

- 已安装 `expo-updates`，但 app config 没有 runtimeVersion 和 updates 配置。
- `preview` profile 没有 `autoIncrement`。
- iOS 没有显式 buildNumber，Android 没有显式 versionCode。

连续向 TestFlight 分发时，版本号重复会导致上传失败或测试者无法确认安装的是哪一版。

### 9. 内测运营资料缺失

移动端没有正式的测试说明文档，至少还缺：

- 构建编号和变更摘要
- 测试账号或测试工作区
- 支持哪些 iOS/Android 版本
- 已知问题
- 反馈渠道
- 隐私与测试数据说明
- 紧急联系人和停止测试方式

建议内测必须使用独立测试数据库和测试店铺，不能直接让外部测试者操作真实卖家生产数据。

## 四、当前已经具备的基础

以下部分已经具备较好的内测基础：

- `app.config.ts` 已配置正式 App 名称、scheme、iOS Bundle ID 和 Android package。
- 1024 图标、Android adaptive icon 和 monochrome icon 已存在。
- 登录、注册、用户名校验、刷新令牌、当前设备退出和全部设备退出已实现。
- 原生端令牌使用 SecureStore，没有直接写入普通存储。
- 服务条款和隐私政策 URL 当前均可访问并返回 `200`。
- `eas.json` 已建立 development、preview、production 三个构建 profile。
- 后端已有 Expo Push Outbox、通知偏好、安静时段和设备注册。
- 移动端单元测试当前为 `8 files / 30 tests passed`。
- TypeScript 和 ESLint 当前通过。
- Expo Web 预览构建 `dist-preview-v39` 成功。
- `npm audit --omit=dev` 没有报告 high/critical；当前有 3 个 moderate 的 `minimatch` 间接依赖问题。

## 五、建议的内测放行顺序

### 阶段 A：先解决安全与仓库问题

1. 轮换 `.env.production` 中所有真实密钥。
2. 清理 Git 当前树和历史中的真实环境文件。
3. 只把移动端必要源码、配置、图标和锁文件纳入 Git。
4. 确认远程分支能独立 clone 并安装。

### 阶段 B：解决原生构建问题

1. 补齐 `expo-asset` 和 `react-native-worklets`。
2. 重新执行 `expo-doctor`，必须 `20/20`。
3. 创建并绑定 EAS 项目，写入稳定 projectId。
4. 为 preview 配置 HTTPS 测试 API。
5. 为 preview 配置独立版本号递增策略。
6. 配置 APNs Key、FCM/Google Services 和 EAS 签名。

### 阶段 C：生成首个候选包

1. Android：生成 internal distribution APK。
2. iOS：按团队条件选择 TestFlight 或 Ad Hoc。
3. 安装到至少一台真实 iPhone 和一台真实 Android 手机。
4. 验证冷启动、登录、时间线、任务确认、素材上传、通知和深链。
5. 确认 App 内版本号与实际构建编号一致。

### 阶段 D：开放给少量测试用户前

1. 使用独立测试工作区和测试店铺。
2. 准备 5-10 名受控测试者，不要直接公开发布。
3. 提供测试说明、已知问题、反馈入口和退出方式。
4. 接入移动端崩溃监控。
5. 建立每天查看错误、失败任务和测试者反馈的值班流程。

## 六、禁止提交到远程分支的文件

### 1. 必须立即从远程移除

| 文件或模式 | 原因 |
| --- | --- |
| `crossborder-ai/.env.production` | 当前已被 Git 跟踪，包含真实密钥字段，必须轮换并清理历史 |
| `.env` | 本地运行密钥 |
| `backend/.env` | 数据库与模型 API Key |
| `.env*.local` | 本地覆盖配置 |

### 2. 签名和凭据文件

禁止提交：

- `*.jks`
- `*.keystore`
- `*.p8`
- `*.p12`
- `*.mobileprovision`
- `*.key`
- `*.pem`
- `credentials.json`
- App Store Connect 私钥
- APNs 私钥
- FCM Service Account JSON

本次未在 `mobile` 中发现上述签名文件，当前是好状态，必须保持。

### 3. 构建目录、缓存和浏览器资料

禁止提交：

- `mobile/dist-preview*`
- `mobile/dist/`
- `mobile/web-build/`
- `mobile/node_modules/`
- `mobile/.expo/`
- `mobile/.chrome-preview/`
- `*.tsbuildinfo`
- Metro、npm、yarn 日志

当前 `mobile` 下有 36 个预览构建目录，约 `923.7 MB`；`.chrome-preview` 约 `265.5 MB`。这些都不能进入 App 源码提交。

### 4. 评审截图、ZIP 和测试产物

建议不提交，改为共享盘、对象存储或 GitHub Release 附件：

- `mobile/artifacts/`
- `frontend/.artifacts/`
- `*.zip`
- 临时截图
- 临时预览日志
- 临时 HTML 预览服务日志

当前 `mobile/artifacts` 约 `18.4 MB`，`frontend/.artifacts` 约 `123.9 MB`。

### 5. 测试数据库、日志和运行时目录

禁止提交：

- `.tmp/`
- `backend/.tmp/`
- `*.pytest_runtime_*`
- `.pytest_cache/`
- `*.db`
- `*.sqlite`
- `*.sqlite3`
- `*.db-wal`
- `*.db-shm`
- `*.log`
- `backend/storage/`
- 上传的用户图片、语音和导出文件

### 6. 本地工具与无关项目

禁止从根仓库提交：

- `D:\Project` 下与 `crossborder-ai` 无关的同级项目
- `.claude/`
- `.taste-skill/`
- `.tmp/`
- `$null`
- `bash.exe.stackdump`
- 本地 IDE 配置和机器专属文件

`design-previews/` 当前约 `31.1 MB`。是否提交应由团队明确决定；如果只是历史设计稿，建议放独立设计资产库。

### 7. 可以并且应该提交的移动端内容

| 内容 | 说明 |
| --- | --- |
| `mobile/src/` | App 业务源码 |
| `mobile/assets/` | App 运行必需资源 |
| `mobile/app.config.ts` | Expo 配置 |
| `mobile/eas.json` | EAS build profile |
| `mobile/package.json` | 依赖与脚本 |
| `mobile/package-lock.json` | 可复现安装 |
| `mobile/tsconfig.json` | TypeScript 配置 |
| `mobile/eslint.config.js` | lint 配置 |
| `mobile/vitest.config.mts` | 测试配置 |
| `mobile/src/**/*.test.ts` | 测试 |
| `mobile/.gitignore` | 生成物忽略规则 |

`mobile/assets/fonts/` 中约 `21 MB` 的中文字体是运行依赖，可以提交；如果仓库不接受大文件，应使用 Git LFS 或子集化方案，而不是直接删除。

## 七、本次审计实际执行结果

| 检查 | 结果 |
| --- | --- |
| `git rev-parse --show-toplevel` | `D:/Project` |
| 当前分支 | `main`，与 `origin/main` 同步 |
| `mobile` 已跟踪文件数 | `0` |
| `.env.production` | 已被 Git 跟踪 |
| `.ipa/.apk/.aab` | 未发现 |
| `npx expo-doctor` | `19/20`，缺少 `expo-asset`、`react-native-worklets` |
| `npm test` | `8 files / 30 tests passed` |
| `npm run typecheck` | 通过 |
| `npm run lint` | 通过 |
| Expo Web 预览构建 | `dist-preview-v39` 通过 |
| `npm audit --omit=dev` | 3 个 moderate，无 high/critical |
| 服务协议 | `https://veyaship.com/terms` 返回 `200` |
| 隐私政策 | `https://veyaship.com/privacy` 返回 `200` |

## 八、最终放行标准

达到以下条件后，可以开始小范围外部内测：

- 所有暴露密钥已轮换，真实环境文件不再出现在当前树和历史中。
- `mobile` 必要源码和配置已进入远程分支。
- `expo-doctor` 为 `20/20`。
- preview 构建固定连接 HTTPS 测试 API，`EXPO_PUBLIC_PREVIEW_MODE` 未误开。
- EAS projectId、签名、APNs/FCM 和内测分发通道已验证。
- 至少一台真实 iPhone 和一台真实 Android 完成核心流程。
- 推送、冷启动深链、相机、麦克风、相册和上传在真机通过。
- 测试数据与生产数据隔离。
- 有崩溃监控、反馈渠道、值班人和明确停止测试方式。

在这些条件完成之前，建议状态保持为：

```text
NO-GO for external internal testing
GO for continued internal development and device validation
```
