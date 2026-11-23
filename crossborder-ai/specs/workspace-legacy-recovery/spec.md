# 历史工作区数据恢复

## 背景

Web 与 App 开始显式传递 `X-Workspace-Id` 后，查询会严格匹配当前工作区。
历史上尚未写入 `workspace_id` 的店铺、素材、任务和营销数据仍然保存在数据库中，
但不会再出现在任何显式工作区中，用户会误以为数据已被清空。

## 原则

- 不通过放宽工作区过滤来兼容旧数据，避免跨用户或跨工作区泄漏。
- 默认只执行 dry-run，先输出可回填数量和无法归属数量。
- 只把有明确用户所有者的记录回填到该用户的个人工作区。
- 用户已删除、所有者为空或无法唯一确定工作区的记录保持原状并报告。
- 回填只修改 `workspace_id` 和缺失的 `created_by_user_id`，不删除业务记录。

## 覆盖范围

- Shopify 店铺连接。
- 商品、SKU、Listing 和 Listing 草稿。
- 工作区图片、图片任务、视频任务和视频项目。
- 商品分析、营销文案、营销活动、营销套图与发布记录。
- Agent 任务、对话、品牌配置、运营告警和店铺检查记录。

## 生产执行顺序

1. 生产数据库备份。
2. 执行 `python -m scripts.backfill_workspace_scope --table all`，只读检查。
3. 对 `unresolved` 为 0 或已逐条确认的结果执行
   `python -m scripts.backfill_workspace_scope --table all --apply`。
4. 使用原账号重新登录，确认店铺、商品、素材、Agent 任务和通知显示在个人工作区。
5. 保留 dry-run 与 apply 输出作为发布证据。

## 验收

- dry-run 不写数据库，并准确报告 `would_update` 与 `unresolved`。
- apply 可重复执行，第二次不应再产生更新。
- 店铺和素材回填后，工作区接口可以读取原有记录。
- 团队工作区仍不能读取其他用户的个人历史数据。
