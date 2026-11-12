# 视频 Provider 抽象

## 目标

把视频任务执行器从 MiniMax 专用实现中解耦。业务层只处理统一的视频请求、
任务状态和错误；供应商差异由 Provider 适配器负责。本阶段只迁移 MiniMax，
即梦暂不实现真实接口。

## 能力一：统一 Provider 协议

### Requirement

所有视频供应商必须实现统一能力：

- `capabilities`
- `submit`
- `query`
- `cancel`
- `download`

统一请求和结果不得包含 MiniMax 专属字段。

### Scenario: 提交任务

- Given 任务指定 `provider=minimax`
- When 视频执行器提交任务
- Then 通过 Provider Registry 获取适配器
- And 传入统一的提示词、模型、时长、首帧和多参考图
- And 返回统一供应任务 ID

### Scenario: 未知供应商

- Given 任务指定了未注册的 Provider
- When 提交、查询或取消任务
- Then 返回明确的中文错误
- And 任务失败时仍按现有规则退还积分

## 能力二：MiniMax 适配器

### Requirement

现有 MiniMax 请求构造、状态解析、取消和下载必须保持行为不变，只通过适配器接入。

### Scenario: 历史 MiniMax 任务

- Given 历史任务 `provider=minimax`
- When 轮询任务
- Then 使用 MiniMax Adapter 查询并下载视频

## 能力三：Provider Registry

### Requirement

Registry 必须支持注册和按名称解析 Provider，并为未来 `jimeng` 留出扩展能力。

### Scenario: 注册即梦

- Given 后续新增 `JimengVideoProvider`
- When 注册到 Registry
- Then 业务执行器无需修改提交、查询、取消和下载代码

## 能力四：质量档位与项目 Provider 快照

### Requirement

质量档位必须指定 Provider；营销项目和视频任务必须保存 Provider 快照。

### Scenario: 营销项目

- Given 用户选择标准商用质量
- When 创建营销项目
- Then 项目保存 `provider=minimax`
- And 全部镜头任务继承项目 Provider

## 兼容要求

- 历史营销项目缺失 Provider 时默认 `minimax`。
- 历史视频任务已有 Provider 时继续使用原值。
- 本阶段不增加即梦 API Key、接口地址或前端供应商选择。

## 验收标准

- Registry 可注册、解析和拒绝未知 Provider。
- MiniMax Adapter 覆盖提交、查询、取消、下载。
- 视频执行器不再直接调用 MiniMax 业务函数。
- 新旧任务测试全部通过。
