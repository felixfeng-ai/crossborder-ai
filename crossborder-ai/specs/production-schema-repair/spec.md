# 生产数据库漂移修复与部署可靠性

## 能力目标

修复生产数据库“迁移版本已到 head、实际列却缺失”的漂移状态，并确保后续部署不会再次通过 `stamp head` 掩盖迁移失败。

## Requirement 1：可恢复生产 schema 漂移

### Scenario 1.1：数据库标记为 021 但缺少历史迁移列

- Given 数据库 `alembic_version` 为 `021_marketing_video_projects`
- And `product_variants.daily_sales_rate` 等历史迁移列缺失
- When 执行新的修复迁移到 head
- Then 缺失列、索引和约束被补齐
- And 已有表数据不被清空

### Scenario 1.2：修复迁移在正常数据库上重复执行

- Given 数据库已经包含修复迁移要补齐的列和约束
- When 执行修复迁移
- Then 迁移保持幂等，不产生重复列或重复约束

## Requirement 2：部署必须执行迁移且失败即停

### Scenario 2.1：代码发布

- Given 新提交推送到 `main`
- When GitHub Actions 执行生产部署
- Then 流水线必须运行 `alembic upgrade head`
- And 迁移成功后重启后端
- And 健康检查通过后才报告部署成功

### Scenario 2.2：迁移失败

- Given 数据库迁移执行失败
- When 部署流程到达迁移步骤
- Then 部署立即失败
- And 不允许通过 `alembic stamp head` 继续发布

## Requirement 3：SKU 保存错误可诊断

### Scenario 3.1：后端返回可读业务错误

- Given 后端返回中文错误 `该 SKU 已存在`
- When 用户保存 SKU 失败
- Then 页面显示 `该 SKU 已存在`

### Scenario 3.2：后端返回未知服务器错误

- Given 后端没有提供可读错误
- When 用户保存 SKU 失败
- Then 页面显示稳定的中文兜底提示
- And 不再固定误报为“SKU 重复”
