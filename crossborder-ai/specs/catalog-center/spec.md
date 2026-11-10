# SKU / Variant / Listing Center

## 目标

把分散在商品详情中的 SKU、变体和 Listing 能力收口为跨商品工作中心。卖家无需逐个进入商品详情即可管理变体矩阵、批量价格和库存、查看多平台 Listing，并完成平台字段就绪检查。

## 能力点

### CAP-01 全局 SKU 列表

#### Requirement

系统必须提供当前用户全部商品的变体列表，支持按商品、SKU/商品名搜索、启用状态和低库存筛选。

#### Scenario

- Given 用户拥有多个商品和 SKU
- When 打开 SKU 中心
- Then 只返回当前用户变体
- And 每条记录包含商品名、SKU、属性、价格、成本、库存和图片

### CAP-02 变体矩阵

#### Requirement

用户可输入多个属性及值，系统生成笛卡尔组合并创建不存在的 SKU。重复执行时不得重复创建相同属性组合。

#### Scenario

- Given 商品没有颜色和尺寸变体
- When 生成“颜色 × 尺寸”矩阵
- Then 创建全部唯一组合
- And 自动生成稳定且唯一的 SKU
- And 再次执行相同矩阵不会重复创建

### CAP-03 批量变体更新

#### Requirement

用户可一次修改多个本人变体的售价、成本、库存、启用状态和素材图片。请求必须先验证全部归属，再执行任何写入。

#### Scenario

- Given 用户选中多个自己的变体
- When 批量修改价格和库存
- Then 所有选中变体更新成功

#### Scenario

- Given 批量请求混入其他用户的变体
- When 提交更新
- Then 整个请求返回 404
- And 任何变体都不被修改

### CAP-04 全局 Listing 中心

#### Requirement

系统必须提供当前用户全部 Listing 的平台、状态、合规状态、版本和平台字段就绪结果。

#### Scenario

- Given 用户有 Amazon 和 Shopify Listing
- When 查看 Listing 中心
- Then 可按平台和状态筛选
- And 每条 Listing 返回平台规则检查结果

### CAP-05 素材绑定

#### Requirement

变体批量更新可引用图片工作台素材 URL，使图片工作台、SKU 和 Listing 使用同一素材来源。

#### Scenario

- Given 用户选择了已处理的图片素材
- When 绑定到多个 SKU
- Then 每个 SKU 的 image_url 指向该素材
