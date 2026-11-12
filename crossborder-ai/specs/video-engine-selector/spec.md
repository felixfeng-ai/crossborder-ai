# 视频生成引擎选择与 Seedance 2.0/2.5 档位

## 目标

三个视频入口统一提供“自动匹配、MiniMax、即梦 Seedance”切换。
用户无需理解模型 ID，但必须能在提交前看到实际引擎、质量档位、分辨率和积分。

## 能力一：引擎切换

### Requirement

营销成片、专业分镜和商品图生视频共用同一组引擎和质量选择控件。

### Scenario: 自动匹配

- Given 用户未手动选择引擎
- When 页面加载视频能力
- Then 营销成片和专业分镜默认推荐 Seedance 2.0 Standard
- And 商品图生视频默认推荐 MiniMax Standard
- And 页面明确展示推荐结果和原因

### Scenario: 手动切换

- Given 用户点击 MiniMax 或即梦 Seedance
- When 切换引擎
- Then 质量档位只展示该引擎支持的选项
- And 自动选中该引擎的默认档位
- And 积分和分辨率立即刷新

### Scenario: 引擎未配置

- Given 管理员未配置某个视频 Provider
- When 页面展示引擎选项
- Then 该引擎置灰且不可提交

## 能力二：Seedance 档位

### Requirement

Seedance Provider 支持以下固定档位：

- 2.0 Mini：480P，5 积分/秒
- 2.0 Fast：720P，15 积分/秒
- 2.0 Standard：720P，19 积分/秒
- 2.0 Standard HD：1080P，44 积分/秒
- 2.5 Pro：720P，31 积分/秒
- 2.5 Pro HD：1080P，68 积分/秒

### Scenario: 模型能力

- Given 任务选择 Seedance 2.0
- Then 时长支持 4-15 秒
- And 参考图最多 9 张
- Given 任务选择 Seedance 2.5
- Then 时长支持 4-30 秒
- And 参考图最多 30 张

## 能力三：项目快照

### Requirement

自动匹配和手动选择最终都落为具体质量档位和 Provider 快照。

### Scenario: 创建项目

- Given 用户选择 Seedance 2.5 Pro
- When 创建任务或项目
- Then 保存 `provider=jimeng`
- And 保存对应的模型和质量档位
- And 项目开始后不允许中途更换 Provider

## 兼容要求

- 历史质量档位 ID 和 MiniMax 任务继续有效。
- 历史 `seedance` 档位继续映射到 Seedance 2.0 Standard 720P。
- 用户只需在管理员页配置火山方舟 API Key；模型需在方舟控制台开通。
- 原生音频本阶段保持关闭，继续使用现有营销 TTS 链路。

## 验收标准

- 桌面和 390px 移动视口都能完成引擎切换。
- 质量选项、积分和 Provider 快照一致。
- 后端、前端、类型检查、构建和真实截图验证通过。
