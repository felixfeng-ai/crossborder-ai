# 公网法务与合规页面

## 目标

为 VeyaShip 补齐 Shopify 应用审核、商家尽调和普通用户访问所需的公网法务入口。页面必须无需登录即可访问，内容与实际数据处理方式一致，并明确 AI 输出、Shopify 客户数据、删除请求和安全事件的边界。

## 能力点

### CAP-01 公开法务地址

#### Requirement

系统提供以下可被搜索引擎和审核人员直接访问的公开路由：

- `/terms`：服务条款
- `/privacy`：隐私政策
- `/data-processing`：数据处理与删除说明
- `/ai-disclosure`：AI 使用说明
- `/security`：安全与事件响应
- `/report`：侵权与违规举报
- `/contact`：联系我们

每个页面必须包含版本、生效日期、正文、联系入口和返回首页入口。

#### Scenario

- Given 用户未登录
- When 用户直接打开任一法务地址
- Then 页面正常渲染，不跳转登录页
- And 页面展示对应标题、版本、日期和完整正文

### CAP-02 数据与合规披露

#### Requirement

隐私、数据处理和 AI 说明必须明确：

- 处理的账号、商品、素材、店铺 Token 和 AI 提示词范围
- 第三方处理方类别，不虚构未部署的服务
- Shopify 原始订单仅按商家指令读取，不持久化客户姓名、邮箱、电话和地址
- 商家可请求导出、更正或删除数据，并可解绑店铺和注销账号
- AI 输出可能错误，发布前必须人工复核
- 安全事件的报告渠道和响应原则

#### Scenario

- Given 审核人员阅读隐私与数据处理说明
- When 核验 Shopify Protected Customer Data 用途
- Then 可以确认平台只申请订单履约与运营分析所需的最小数据
- And 可以找到数据删除和安全事件联系方式

### CAP-03 登录与注册告知

#### Requirement

登录和注册页提供可点击的《服务条款》《隐私政策》同意文案，链接不得只展示不可交互的纯文本。

#### Scenario

- Given 用户首次登录或注册
- When 用户查看主操作附近
- Then 用户可打开公网服务条款和隐私政策

### CAP-04 公网页脚

#### Requirement

首页和法务页面共用低干扰公开页脚，至少包含服务条款、隐私政策、数据处理、AI 使用说明、安全说明、举报和联系我们。

#### Scenario

- Given 用户位于首页或任一法务页
- When 用户滚动至页脚
- Then 可从同一组链接访问全部公开法务页面

### CAP-05 可读性与移动端

#### Requirement

法务页面以正文为主角，桌面端显示目录，移动端使用单列正文；文本不得溢出，所有交互具有可见键盘焦点，长中文可正常换行。

#### Scenario

- Given 用户使用 1440px 桌面或 390px 手机
- When 阅读长法务正文
- Then 内容保持可读宽度，目录可跳转且页脚不遮挡正文

## 不在本次范围

- 不在页面中宣称 Shopify 已批准 Protected Customer Data
- 不承诺法定主体名称、地址或电话等尚未确认的信息
- 不实现 Shopify 强制隐私 webhook；该项作为后续审核阻断单独跟踪

## 验收

- `npm test` 通过
- `npx tsc -p tsconfig.tscheck.json --noEmit` 通过
- `npm run build` 通过
- 使用真实浏览器检查 1440px、768px、390px
- 提交并推送 `main`，GitHub Actions 自动部署成功
