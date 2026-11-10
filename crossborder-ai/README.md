# VeyaShip AI 🌐

> 面向中国跨境卖家的 AI 决策引擎：给一个品类或一条 1688 链接，AI 跑完「**能不能做 → 多少钱能赚 → 文案过不过合规 → 图长什么样 → 上不上得了架**」整条链。

在线体验：<https://veyaship.com> —— 注册即送免费额度，**不装环境、不填任何 Key、不碰配置文件**。

---

## 这是什么

跨境卖家手上从来不缺工具，缺的是**把这些工具串起来的那根线**：采集在一个网站、翻译在另一个、合规靠人肉查词、发布再回 Shopify 后台。一个品从「看到」到「上架」，人要在四五个界面之间来回搬运。

**VeyaShip 把这条链收进同一个对话里。** 你说一句「把这个品抓下来、写好文案、合规过一遍、发到 Shopify」，Agent 自己按顺序跑完并回报结果 —— 不是给你一个建议，是把活干完。

三个立足点：

|                            | 说明                                                                                                     |
| -------------------------- | -------------------------------------------------------------------------------------------------------- |
| **对话即操作**             | ReAct + Function Calling，12 个工具可被自动编排；说人话就是操作，不用学菜单在哪                             |
| **合规是闭环，不是提示**   | 违禁词 / 极限词 / 品牌禁词「正则 + AI」双层拦截，**生成后再校验一次**，命中即拦下并告诉你改了什么           |
| **卖家零配置**             | 数据能力（1688 抓取等）由平台侧开通，注册即用；卖家不需要装环境、不需要申请或填写任何服务商密钥              |

### 能力地图

- **1688 抓取** —— 粘贴链接抓商品，Just One API 优先，失败降级 Onebound 与直抓，返回标注数据来源
- **品类分析** —— 锚定 Amazon US，看市场容量与竞争格局，回答「这个品能不能做」
- **选品决策 + 净利计算** —— 成本 / 运费 / 平台佣金一起算，选品不靠感觉
- **SKU / 变体管理** —— 商品下维护颜色、尺寸、售价、成本、库存、条码和变体图片
- **Listing 生成** —— 标题、五点、描述、SEO 元数据，适配 Amazon / Shopify / eBay，可按 17 种目标市场语言产出
- **合规审查** —— 生成后自动复检，命中违禁词直接拦下
- **品牌调性 Brand Kit** —— 填一次调性，之后每条文案、每张图都按同一套品牌风格产出
- **AI 出图** —— 阿里云通义万相文生图，Replicate FLUX 降级兜底
- **批量 CSV** —— 自有货源批量导入，批量 AI 生成与发布
- **Shopify 全链路** —— OAuth 授权、多渠道切换、一键发布、订单查看、自动退款
- **整店巡检** —— 每天凌晨自动巡检全店商品 + 看板手动巡检 + 历史记录
- **竞品雷达** —— 多竞品对比
- **AI Agent** —— ReAct 推理循环、12 个工具、6 个预设工作流、生成后自我反思（质量不过关自动重做）
- **积分与套餐** —— 消耗式计费，每次 AI 生成 / 抓取扣 1 分；升级申请 + 后台审批
- **双端** —— Web 全功能，微信小程序端覆盖高频查看场景

> 适合两类卖家：
>
> - **1688 拿货卖家**：粘贴链接 → AI 抓取 → 生成 Listing → 上架
> - **自有货源卖家**：CSV 批量导入 → AI 生成 Listing → 上架

---

## 技术栈

| 层     | 选型                                                                                                    |
| ------ | ------------------------------------------------------------------------------------------------------- |
| 后端   | Python 3.12 · FastAPI · SQLAlchemy 2.0 (async) · asyncpg · Alembic · Pydantic v2 · APScheduler           |
| 前端   | React 18 · TypeScript · Vite 5 · Tailwind CSS 3.4 · Shadcn/ui · Zustand · TanStack React Query · i18next |
| 小程序 | 微信小程序原生 —— 只做轻量高频场景（品类分析 / 利润计算 / AI 对话 / 订单查看）                             |
| 数据库 | PostgreSQL 16（生产） / SQLite（本地开发，`USE_SQLITE=true`）                                             |
| AI     | DeepSeek（文本 / Function Calling）· 阿里云通义万相（图片）· Replicate FLUX（降级）· LangGraph（编排）     |
| 数据源 | Just One API（1688 优先）· Onebound 降级 · 直抓链路 · BeautifulSoup 解析                                 |
| 交付   | Nginx · systemd · GitHub Actions（push `main` 自动部署）                                                  |

---

## 快速开始

> 以下为**开发者**内容。终端卖家不需要看这一节 —— 平台侧已把数据服务与 AI 能力配置好，注册即可用。

需要 **Python 3.12+** 与 **Node 20+**。本地默认走 SQLite，不必先装数据库。

### 后端

```bash
cd backend
python -m venv venv
source venv/Scripts/activate        # Windows；macOS/Linux 用 source venv/bin/activate
pip install -r requirements.txt

uvicorn app.main:app --reload --port 8000
```

接口文档：<http://localhost:8000/docs>

### 前端

```bash
cd frontend
npm install
npm run dev                         # http://localhost:5173
```

> 构建命令是 **`vite build`** 而非 `tsc -b && vite build` —— 历史 tsconfig 冲突（TS6310）导致类型检查阻塞构建，类型错误单独列为技术债，详见 [DEPLOYMENT.md](DEPLOYMENT.md)。

### 跑测试

```bash
cd backend
pytest -q                           # 28 个测试文件；本地 174 passed + 4 PostgreSQL gates skipped
```

前端 Vitest：

```bash
cd frontend
npm test
```

真实 PostgreSQL 门禁：

```bash
cd backend
$env:DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/veyaship_ci"
$env:JWT_SECRET_KEY="local-ci-secret"
python -m alembic upgrade head
$env:POSTGRES_TEST_URL=$env:DATABASE_URL
python -m pytest tests/test_postgres_gate.py -q
```

---

## 项目结构

```
backend/                      FastAPI 服务
  app/core/                   配置 · 异步数据库 · JWT/bcrypt · 限流 · Redis · 权限控制 · 可观测性
  app/models/                 15 张表的 SQLAlchemy 模型
  app/schemas/                Pydantic 请求/响应校验
  app/routers/                13 个路由：auth / products / content / images / agent /
                              shopify / batch / radar / ledger / analytics / billing / settings / users
  app/services/
    ai/                       DeepSeek · 通义万相 · Replicate 降级 · Agent 编排 ·
                              ReAct 工具 · 合规审查 · Brand Kit · RAG
    crawler/                  1688 / Shopify 采集
    scraper.py                1688 多级抓取核心（接口优先 + 直抓降级）
    scheduler.py              APScheduler 定时任务（整店巡检等）
  tests/                      28 个测试文件（含 PostgreSQL gate）
  migrations/                 Alembic 迁移
frontend/                     React SPA
  src/pages/                  17 个页面：Dashboard / Products / Content / Images / Agent /
                              Shopify / Batch / Radar / Ledger / Billing / Settings / Landing ...
  src/components/             ui（Shadcn）/ layout / agent / dashboard
  src/api/                    Axios 客户端
  src/i18n/locales/           9 种界面语言
miniprogram/                  微信小程序端（7 个页面）
specs/                        SDD 行为规格：onboarding-retention · scrape-1688
docs/                         诊断报告与商业优化方案 · 生产就绪度 · 收口记录
nginx/                        网关配置（SPA + /api 反代）
deploy/                       服务器运维脚本（Nginx 上线 · 数据库备份）
cicd-deploy.sh                服务器端自动部署脚本
```

---

## 架构要点

```
用户浏览器 ──► https://veyaship.com ──► Nginx（SSL 终止 / 静态资源 / 反向代理）
                                          ├─► /            前端静态 SPA
                                          ├─► /api/*       FastAPI（uvicorn × 4 worker）
                                          └─► /interview/* 同服务器另一项目（路径隔离）
                                                │
                                                ├─► PostgreSQL 16
                                                ├─► APScheduler   定时巡检 / 批量任务
                                                └─► AI 服务       DeepSeek · 通义万相 · Replicate（降级）
```

几条贯穿全局的设计约束，改代码时请留意：

1. **平台侧配置，用户侧无感** —— 第三方 Key（DeepSeek / 通义万相 / Just One / Onebound）由平台在设置页配置，改动即时生效，**不改文件、不重启服务**；卖家界面永不出现 `.env`、路径与 API Key。
2. **错误信息给卖家看，不给机器看** —— 抓取失败要有稳定错误码 + 中文可读建议（换链接 / 重试 / 手动录入），不允许把英文异常裸抛到前端。
3. **外部依赖必须有降级** —— 1688 抓取「Just One → Onebound → 直抓」、出图「通义万相 → Replicate」，降级要在响应里标注 `data_source`，让问题可归因。
4. **合规是生成后的第二道闸** —— 违禁词拦截不只在输入侧，生成结果必须再过一次，命中即拦。
5. **定时任务与请求会话隔离** —— 调度器与后台任务各自持有独立 session，绝不共享请求级会话。
6. **积分扣减走行级锁** —— 并发扣减用 `select_for_update()`，防止余额被扣穿。

---

## 部署

生产为**单台阿里云 ECS（2C2G / Ubuntu 24.04）+ systemd + Nginx**：前端构建成静态文件由 Nginx 托管，后端跑 `uvicorn --workers 4` 的 systemd 服务，数据在原生 PostgreSQL 16。

推送到 `main` 后由 GitHub Actions 触发服务器脚本自动部署：**同步代码 → 装后端依赖 → `npm ci` + `vite build` → 发布静态资源 → Alembic 迁移 → 重启后端 → 健康检查（最长等 120s）**，任一步失败即中断，不留「半部署」状态。回滚 = `git reset` 到上一版本 + 重跑同一套脚本。

完整架构说明、环境变量清单、CI/CD 流水线与回滚方案见 **[DEPLOYMENT.md](DEPLOYMENT.md)**，配置模板见 [`.env.example`](.env.example)。

---

## 文档索引

| 文档                                                             | 内容                                                                         |
| ---------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| [CLAUDE.md](CLAUDE.md)                                           | **开发约定**：技术栈、目录规范、后端/前端编码规范、F1–F9 模块清单、关键规则   |
| [AGENT_ROADMAP.md](AGENT_ROADMAP.md)                             | **Agent 全貌**：1.0→5.0 演进、能力矩阵、9 工具 / 6 工作流、整店巡检闭环、未来路线 |
| [DEPLOYMENT.md](DEPLOYMENT.md)                                   | **部署与运维**：系统架构、CI/CD 流水线、技术决策与权衡、安全、回滚            |
| [docs/product/诊断报告与商业优化方案-2026-09-03.md](docs/product/诊断报告与商业优化方案-2026-09-03.md) | 产品诊断、商业化短板与改进方案                       |
| [docs/production-readiness.md](docs/production-readiness.md)     | 生产就绪度评估                                                               |
| [docs/收口-2026-09-08.md](docs/收口-2026-09-08.md)               | CAP-01~07 批次收口记录、根因修复与回归门禁                                    |
| [AGENT_TESTING.md](AGENT_TESTING.md)                             | Agent 测试指南：闭环验证方法、检查清单                                        |
| [specs/](specs/)                                                 | SDD 行为规格（能力点 + 需求场景）                                             |
| [DOCS_INDEX.md](DOCS_INDEX.md)                                   | 全部文档导航（含历史与规划类文档）                                            |

---

## 工程状态

- 后端 78 个 Python 文件 / 约 11,700 行；前端 51 个 TS/TSX 文件 / 约 7,200 行
- 15 张表 · 13 个路由模块 · 17 个前端页面 · 微信小程序 7 个页面
- 28 个测试文件：本地 174 passed + 4 PostgreSQL gate skipped
- 前端 Vitest：5 个测试文件 / 17 个用例
- Agent 已完成 4.2 自我反思与 5.0 整店巡检闭环；下一步为价格监控 / 销量预警
- 生产已上线：<https://veyaship.com>

### 已知技术债

| 项                 | 说明                                                                     |
| ------------------ | ------------------------------------------------------------------------ |
| 前端类型检查       | `vite build` 本身仍不执行 `tsc`，由独立类型检查和 CI 门禁覆盖              |
| 界面多语言         | 9 种语言资源已就位，部分页面文案尚未全部接入 `t()`                        |
| 单元测试运行器     | 后端 174 个 pytest 用例；前端 Vitest 5 个测试文件 / 17 个用例              |
| 可视化工作流编排   | 5.1 规划中（用户自拖拽搭建工作流）                                        |

---

## 📄 License

Private / Proprietary — All rights reserved.
