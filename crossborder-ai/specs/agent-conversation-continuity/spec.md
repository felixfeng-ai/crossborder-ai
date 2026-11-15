# Agent Conversation Continuity

## 目标

让营销 Agent 与 AI 决策助手能够可靠延续同一会话，正确处理确认、补充参数和指代，
同时避免孤立确认语句误触发扣费操作。

## 能力点

### CAP-01 历史消息注入

#### Requirement

执行 Agent 任务时必须加载当前会话最近有限条消息，并将用户和助手文本按时间顺序
传给模型。历史消息必须按字符预算裁剪，不允许无限增长。

#### Scenario

- Given 同一会话上一轮助手询问是否开始生成视频
- When 用户回复“可以”
- Then 模型输入包含上一轮助手问题
- And 当前指令仍作为最后一条用户消息

### CAP-02 工作区角色

#### Requirement

Agent 编排器必须接收 `workspace` 并使用对应系统提示词。营销 Agent 与 AI 决策助手
共享执行引擎，但工具优先级、角色说明和任务边界必须不同。

#### Scenario

- Given 营销工作区执行任务
- Then 系统提示词包含营销方案、商品素材、视频和广告文案职责

### CAP-03 结构化确认

#### Requirement

所有会扣积分的工具在未确认时必须返回 `pending_action`，其中包含工具名、完整参数和
预计积分。确认语句必须恢复到该工具执行，并使用原参数。

#### Scenario

- Given 上一轮生成视频工具返回 `pending_action`
- When 用户回复“可以”
- Then 系统直接调用生成视频工具并设置 `confirmed=true`
- And 不重新让模型猜测任务

#### Scenario

- Given 新会话没有 `pending_action`
- When 用户只回复“可以”
- Then 不执行任何扣积分工具
- And 返回需要补充任务的说明

### CAP-04 安全边界

#### Requirement

否定表达、超过有效期或不属于当前用户的待确认任务不得执行。确认操作必须保持
工具参数、活动和用户所有权不变。

#### Scenario

- Given 用户回复“先不要生成”
- Then 不执行待确认操作

#### Scenario

- Given 待确认任务来自其他会话
- Then 不能通过当前会话确认执行
