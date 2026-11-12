# 自有货源商品录入

## 目标

商品库必须明确区分 1688 货源和自有货源。自动抓取只支持 1688；自有货源
不要求商品链接，并支持图片、描述、成本、品牌、MOQ、库存和 CSV 批量导入。

## 能力一：明确货源类型

### Requirement

商品记录必须保存来源类型，前端必须使用独立入口录入 1688 商品和自有商品。

### Scenario: 1688 货源

- Given 用户选择 1688 货源
- When 粘贴 1688 商品链接
- Then 使用现有 Just One/Onebound 抓取链路
- And 商品来源保存为 `1688`

### Scenario: 自有货源

- Given 用户选择自有货源
- When 不填写商品链接但填写商品名称和必要信息
- Then 商品可以成功创建
- And 商品来源保存为 `own`

## 能力二：自有商品字段

### Requirement

自有商品手动录入必须支持：

- 商品名称
- 商品描述
- 主图 URL
- 品牌
- 成本价和币种
- MOQ
- 交付周期
- 初始库存

### Scenario: 创建自有商品

- Given 自有商品没有外部商品链接
- When 用户填写名称、成本、库存并上传主图
- Then 商品和初始库存信息成功落库
- And 后续可以在详情页继续添加 SKU 变体

## 能力三：CSV 自有商品模板

### Requirement

CSV 必须支持自有商品模板，至少包含：
`title, cost_price, currency, stock_quantity, description, main_image_url,
brand_name, moq, lead_time_days`。

### Scenario: 批量导入自有商品

- Given 用户上传自有商品 CSV
- When 行中没有 URL
- Then 仍然创建商品
- And 成本、库存、描述、图片、品牌、MOQ 和交付周期写入对应记录

## 能力四：数据与兼容

### Requirement

历史商品必须兼容，缺失来源时默认视为 `1688`；同一用户仍不能重复录入同一 URL。

### Scenario: 历史数据

- Given 旧商品没有 `source_type`
- When 新版本读取旧商品
- Then 返回 `source_type=1688`

## 验收标准

- 商品库页面有明确的 1688/自有货源切换。
- 自有货源手动录入不需要 URL。
- 商品列表展示来源类型。
- CSV 支持无 URL 的自有商品并导入图片、成本、库存等字段。
- 后端迁移、API 测试、前端测试和构建通过。
