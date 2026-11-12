# 营销效果同步与自动优化闭环

## 目标

把 Shopify 订单、广告平台导出数据和营销活动 A/B 文案连接成可追溯的
效果闭环。系统只能根据真实指标给出建议，样本不足时不得宣布赢家或暂停版本。

## 能力一：Shopify 订单自动同步

### Requirement

系统应周期性把已绑定 Shopify 店铺的订单和销售额写入关联营销活动快照。

### Scenario: 定时同步

- Given 用户有启用的 Shopify 店铺和已发布活动商品
- When 定时同步任务执行
- Then 每个启用的店铺按独立用户权限同步最近 30 天数据
- And 单个店铺失败不会阻断其他店铺
- And 同一时间窗口重复同步只更新快照，不重复累加

### Scenario: 用户手动刷新

- Given 用户正在查看营销活动效果
- When 点击“同步订单效果”
- Then 返回本次扫描订单数、更新活动数和失败信息

## 能力二：广告平台标准指标导入

### Requirement

系统应提供 Amazon Ads、TikTok Ads、Meta Ads 的 CSV 导入适配器，
把不同平台的列名统一为曝光、点击、订单、转化、花费和收入。

### Scenario: 识别平台报表

- Given 用户上传 Amazon Ads、TikTok Ads 或 Meta Ads 导出的 CSV
- When 选择对应平台并导入
- Then 适配器识别平台常用列名
- And 无效行返回明确错误，不写入半条数据

### Scenario: 指标归属活动与 A/B 版本

- Given 用户选择当前营销活动
- When 导入报表并可选选择一条 A/B 文案
- Then 快照保存活动、平台、来源和时间窗口
- And 选择文案时快照保存 copy_id
- And 其他用户不能导入到该活动

## 能力三：效果驱动优化建议

### Requirement

系统应根据活动汇总和 A/B 版本指标生成可执行建议，覆盖文案、图片和视频方向。

### Scenario: 版本级建议

- Given 活动存在绑定 copy_id 的效果快照
- When 请求优化结果
- Then 返回每个 A/B 版本的 CTR、CVR、ROAS、样本量和表现状态
- And 低点击建议优化前 3 秒、封面或标题
- And 低转化建议检查价格、承诺、商品页承接和 CTA
- And 低回报建议暂停或缩小投入

### Scenario: 样本不足

- Given 某个版本曝光或点击不足
- When 系统计算表现
- Then 标记为 insufficient_data
- And 不自动暂停、不宣布赢家

## 能力四：A/B 自动暂停与推荐

### Requirement

系统在样本充足、版本可比且差距明确时，自动暂停低表现版本并推荐高表现版本。

### Scenario: 自动判定

- Given 同一活动同一平台至少有两条 A/B 文案存在效果数据
- And 至少一条达到最小曝光和点击阈值
- When 导入效果数据完成
- Then 明显落后的版本 performance_status 变为 paused
- And 高表现版本变为 winner
- And 普通或样本不足版本保持 active 或 insufficient_data

### Scenario: 人工恢复

- Given 文案因效果表现被暂停
- When 用户恢复该版本
- Then performance_status 变回 active
- And 合规状态和文案内容不受影响

## 验收标准

- Shopify 自动任务有跨进程锁和单店铺失败隔离。
- 三种广告报表适配器有表头、金额、百分比和错误行测试。
- 快照可以绑定 copy_id，并保持用户与活动隔离。
- 样本不足时绝不自动暂停。
- 自动暂停和赢家推荐有阈值测试。
- 营销页面在 1440px 和 390px 下可导入、查看状态并恢复版本。
