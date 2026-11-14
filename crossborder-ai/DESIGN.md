# VeyaShip Design System

## North Star

VeyaShip 是跨境卖家的石墨决策台：以中性近黑层级、纸白命令和低饱和琥珀信号，把商品证据、AI 判断、利润、合规、SKU 与渠道状态组织成一条可执行链路。

## Product Truth

- Audience: 每天高频处理商品、Listing、图片、库存与多平台发布的跨境卖家和运营人员。
- Primary job: 判断一个来源商品是否可上架，并把可上架商品推进到目标渠道。
- Platform: React Web 应用，同时服务桌面与 390px 移动端。
- Core surfaces: 仪表盘、商品库、Listing 中心、AI 助手、图片工作台、视频工作台、素材中心、运营监控、渠道发布、账单与设置。
- What must survive: 现有路由、鉴权、业务接口、导航入口、琥珀色品牌识别和全部数据能力。

## Principles

1. 每个屏幕只允许一个主角和一个主操作。总览的主角是商品经营链路，不是欢迎语或快捷入口宫格。
2. 用层级、留白和发丝线组织信息。卡片只用于真实对象、浮层和重复项，不用于每个页面区块。
3. 状态色只表达状态。纸白表示执行，琥珀表示 AI/选中/运行，薄荷表示完成，珊瑚表示需要人处理。
4. 中文优先系统字体栈，西文和数字使用 Inter，编号、金额、SKU、耗时使用 JetBrains Mono。
5. 动效只解释状态和空间关系，不装饰高频工作流。

## Visual Direction

- Protagonist: 当前商品的经营链路与待决策事实。
- Primary action: 继续处理当前阻断，或开始一条新的商品到上架链路。
- Character: 安静、精密、可信、长期使用不疲劳。
- Signature: 石墨工作台上的反相纸白命令，以及低饱和琥珀运行信号。
- Material: 真实商品、价格、库存、渠道、合规与 AI 任务状态，不使用装饰性抽象图形。

## Tokens

### Colour roles

#### Theme modes

| Mode | Role |
| --- | --- |
| `graphite` | Default theme. Preserves the existing graphite workspace and amber signal. |
| `paper` | Optional white theme for daytime and general operations. |
| `harbor` | Optional teal theme for logistics, compliance and multi-channel operations. |
| `system` | Optional mode. Dark resolves to graphite, light resolves to paper. |

- Theme changes only replace semantic tokens; layout, type, spacing, radii and component dimensions stay fixed.
- `graphite` remains the fallback when no valid preference exists.
- Theme choice is persisted locally and applied before React starts to prevent flashing.
- Arbitrary user-defined colors are not supported.

| Role | Value | Use |
| --- | --- | --- |
| Canvas | `#0D0E0E` | 页面底色 |
| Sidebar | `#101110` | 完整侧栏 |
| Panel | `#151615` | 工作面、输入区 |
| Raised | `#1B1C1A` | 浮层、下拉、次级面板 |
| Line | `rgba(243,242,237,.09)` | 发丝线、边界 |
| Ink | `#F3F2ED` | 主文字与主按钮 |
| Muted ink | `#B4B0A8` | 次文字 |
| Faint ink | `#8F8C85` | 元信息 |
| Accent | `#D8B56D` | AI、运行、选中和关键状态 |
| Mint | `#9DBBAD` | 完成状态 |
| Coral | `#D98B70` | 风险、失败和需人工处理 |

### Type

- Chinese UI: `"PingFang SC", "Noto Sans SC", "Microsoft YaHei", "HarmonyOS Sans SC", "MiSans", "Hiragino Sans GB", sans-serif`.
- Latin and normal numbers: self-hosted `Inter`.
- IDs, SKU, amounts, credits and durations: self-hosted `JetBrains Mono`.
- Page title: 28-32px / 600 / 1.4.
- Section title: 16-20px / 600.
- Body: 14px / 400 / 1.64.
- Metadata: 12px / 400 / 1.5.
- Nothing readable below 11px; no negative letter spacing; no oblique Chinese.

### Space and shape

- Spacing scale: 4, 8, 12, 16, 24, 32, 48, 64.
- Desktop frame: 232px sidebar, 58px top bar, 24-32px canvas gutters.
- Mobile frame: 16px gutters, 44px minimum touch target.
- Radius: cards 8px, controls 6px, chips 4px.
- Elevation: only menus, dialogs and genuinely floating AI surfaces may use shadow.
- Icon family: Lucide, 14-18px in navigation and 12-16px inline.

## Layout and Navigation

- Mobile model: 58px top bar, drawer navigation, single-column content, no horizontal page scroll.
- Desktop model: 232px labelled sidebar, 58px top bar, continuous graphite work surface.
- Primary navigation groups: 经营（仪表盘、商品库、Listing 中心）、AI 创作（AI 助手、图片工作台、视频工作台、素材中心）、运营（运营监控、渠道发布）、账户（账单、设置）。
- Batch import is an action inside 商品库; AI Listing generation is an action inside Listing 中心; upgrade approval is an admin action in the account menu.
- What is intentionally not navigation: onboarding hints, recent products, billing upgrades and provider configuration stay inside their owning surface.
- Safe areas and keyboard behaviour: `min-h-[100dvh]`, safe-area insets, visible focus rings and keyboard reachable controls.

## Admin Operations

- 管理员使用独立 `/admin` 壳层，沿用 232px 石墨侧栏和 58px 顶栏，但不复用卖家工作台导航。
- 管理员页面是高密度运营工具：KPI 使用一组分隔条，不堆叠图标卡片；表格用行规则和对齐，图表只保留一个数据色。
- 页面主角是待处理运营事实，主操作是审核、发布或处理反馈；管理页面不使用营销页式 Hero、装饰性渐变或动效入场。
- 移动端侧栏折叠为顶部菜单抽屉，数据表在自身容器内处理溢出，页面不允许横向滚动。

## Components

- Button: paper-white default for primary commands, outlined or ghost for secondary; 34px desktop height and 44px mobile touch area.
- Card: opaque panel with 1px hairline; no blur, glow or hover lift at rest.
- Input: opaque field on panel, 6px radius, visible label and brand focus ring.
- Sidebar: neutral active fill and text weight change; no coloured pill and no left accent bar.
- Header: shows current workspace group and page title; carries credits, language and account; does not repeat the brand slogan.
- Brand mark: geometric V-route with three route nodes and one amber destination node; sidebar subtitle is `AI 跨境运营台`.
- Pipeline: ordered operational steps with completed, running, blocked and waiting states.
- AI status: model/tool activity is shown only where it helps the current decision.
- Login and registration: split-page authentication with an AI Agent execution chain on the left and one focused form on the right; mobile collapses to the brand claim plus the complete form.

## Content and States

- Empty state: preserves the frame, states the current fact and gives one next action.
- Loading: final layout with flat value placeholders; refresh keeps existing content.
- Error: local to the failed block, says what failed, preserves prior values and offers retry.
- Offline: existing content remains readable; write actions explain that connection is required.
- Long content: one-line truncation with accessible full value, or explicit wrapping for descriptions.

## Motion

- Duration/easing: 120-220ms, `cubic-bezier(0.23, 1, 0.32, 1)`.
- Allowed motion: pressed feedback, menu/dialog origin, state transitions and status pulse.
- Reduced motion: remove travel, pulse and stagger while preserving state feedback.

## Prohibited Patterns

- Aurora, glow orbs, decorative gradients, gradient buttons and gradient text.
- Default glassmorphism, backdrop blur on resting surfaces and card-inside-card nesting.
- Rows of identical rounded cards as page structure.
- Emoji greetings or emoji navigation.
- Purple or electric-blue AI palettes and high-saturation fluorescent accents on near-black.
- Coloured left bars or inset left lines for selected navigation, cards or list rows.
- Inter-first Chinese rendering or full Chinese webfont downloads.

## Verification

- Target viewports: 1440×1000, 768×1024 and 390×844.
- Required screenshots: 总览桌面、总览移动端、商品列表、商品详情、设置页、视频工作台、素材中心桌面与移动端。
- Automated checks: `npx tsc -p tsconfig.tscheck.json --noEmit`, `npm test`, `npm run build`.
- Manual checks: keyboard focus, reduced motion, text overflow, long Chinese copy and contrast.
- Last verified: 2026-11-11, production build verified at 1440, 768 and 390 widths.

## Change Policy

Ordinary feature work preserves this system. A redesign requires explicit user intent and a before/after review. Do not reintroduce multi-theme palettes, decorative AI gradients or glass surfaces without changing this document first.
