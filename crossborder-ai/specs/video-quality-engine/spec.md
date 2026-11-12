# 三入口视频质量引擎

## 目标

营销成片、专业分镜和商品图生视频必须共享质量档位、风格预设、H3 结构化
提示词编译、积分快照和原生分辨率输出；各入口只保留自身需要的镜头规划能力。

## 能力一：质量档位

### Requirement

用户必须通过质量档位选择视频能力，不能通过前端随意组合低档积分与高档模型。

### Scenario: 生成前选择质量

- Given 用户进入任一视频入口
- When 选择快速、标准或电影级
- Then 后端自动确定模型和分辨率
- And 返回对应积分单价、预计消耗和预计耗时

档位：

- `draft`：H3 Lite 480P，8 积分/秒
- `standard`：H3 Highspeed 768P，15 积分/秒
- `cinematic`：H3 2K，24 积分/秒

## 能力二：风格预设

### Requirement

三个视频入口必须共享结构化风格预设，风格不额外计费。

### Scenario: 选择风格

- Given 用户选择高端静奢、真实生活、电影叙事、电商展示、节日氛围或参考图匹配
- When 提交生成
- Then 提示词包含对应的光线、镜头、色彩、材质和运动约束
- And 项目与任务保存风格快照

## 能力三：官方结构化提示词

### Requirement

商品图生视频使用 H3 I2VA 结构；营销成片和专业分镜使用单镜头 I2VA 或
Ref2VA 结构。提示词必须包含模型需要的场景、动作、镜头、声音和连续性字段。

### Scenario: 商品图生视频

- Given 只有一张首帧
- When 编译提示词
- Then 包含 `integrated_multimodal_description`
- And 包含 `overall_soundscape`
- And 包含 `non_diegetic_music`

### Scenario: 多参考图镜头

- Given 镜头使用两张以上商品图
- When 编译提示词
- Then 包含 `subject_definitions`
- And 包含 `summary`
- And 包含 `retention_analysis`
- And 包含 `detailed_description`

## 能力四：原生分辨率

### Requirement

最终合成必须按项目分辨率输出，不允许把 480P 源强制放大到固定 720P。

### Scenario: 480P 项目

- Given 项目质量为 draft 480P
- When 合成多镜头
- Then 输出尺寸为 480x854 或等比例偶数尺寸

### Scenario: 768P 和 2K 项目

- Given 项目质量为 standard 768P 或 cinematic 2K
- When 合成多镜头
- Then 输出分别使用约 768x1366 和 1440x2560，而不是固定 720x1280

## 能力五：三入口接入

### Scenario: 营销成片

- Given 用户确认营销方案
- When 创建和渲染项目
- Then 项目保存质量档位、风格和每秒积分快照

### Scenario: 专业分镜

- Given 用户解析专业脚本
- When 创建项目
- Then 每镜使用结构化提示词和边界连续性
- And 项目保存质量档位和风格

### Scenario: 商品图生视频

- Given 用户提交单镜头任务
- When 生成视频
- Then 使用共享质量档位、风格和 I2VA 提示词
- And 保存任务级质量和风格快照

## 能力六：套餐展示

### Requirement

Professional 套餐积分必须覆盖标准 768P 成片的真实成本，并停止宣传不匹配的
“13 条 30 秒 768P”。

### Scenario: 套餐展示

- Given 用户查看 Professional 套餐
- When 页面展示月度积分和视频能力
- Then 月度积分为 3000
- And 标准档位宣传为约 6 条 30 秒 768P 成片

## 非目标

- 本阶段不引入新的第三方视频模型。
- 本阶段不做自动购买额外候选；失败重试和候选选优后续独立上线。
- 现有已创建项目保留原积分和模型快照，不追溯改价。

## 验收标准

- 三个入口都能选择质量档位和风格。
- 前端无法通过质量档位组合绕过服务端计费。
- 单镜头和多参考图提示词包含规定的官方结构字段。
- 合成尺寸随项目分辨率变化。
- 后端、前端和迁移测试全部通过。
