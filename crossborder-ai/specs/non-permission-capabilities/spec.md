# 非外部授权能力补齐

## 背景

本批次只处理不需要向 Amazon、Temu、SHEIN 等第三方平台重新申请开发者权限或商家授权的能力。目标是补齐已有 AI 素材链路中可由平台自身完成的部分。

## CAP-01 VOC 评论洞察

### Requirement: 评论导入

商家可以把纯文本评论或 CSV 评论粘贴到商品 Listing 工作区，也可以选择本地 `.txt` / `.csv` 文件导入。

#### Scenario: 生成聚合洞察

- Given 商家已选择自己的商品并导入至少一条评论
- When 商家提交 VOC 分析
- Then 系统只保存聚合摘要、痛点、卖点、异议、关键词、情感和建议
- And 系统不保存原始买家评论
- And 成功分析后扣除 1 积分
- And 最近一次 VOC 洞察会作为后续 Listing 生成的可信上下文

### Requirement: 回看分析

#### Scenario: 查看历史

- Given 商家此前分析过该商品评论
- When 商家重新打开商品 Listing 工作区
- Then 页面展示该商品最近的 VOC 洞察
- And 商家可以切换历史分析记录

## CAP-02 营销视频字幕

### Requirement: SRT 字幕生成

#### Scenario: 分镜时长对齐

- Given 营销项目已有 hook、script、cta 和 3-5 个分镜时长
- When 系统生成字幕
- Then 字幕从 0 秒开始，按分镜时长连续推进
- And 最后一条字幕不早于视频总时长
- And 字幕包含 hook、正文和 cta

### Requirement: 字幕下载与成片烧录

#### Scenario: 成片完成

- Given 营销项目已完成渲染
- When 商家下载字幕
- Then 系统返回标准 SRT 文件
- And 成片合成时优先烧录同一份字幕
- And 当前 FFmpeg 环境不支持字幕滤镜时仍保留可播放成片和独立 SRT

## CAP-03 MiniMax 配音

### Requirement: 运行时配置

#### Scenario: 缺少 GroupId

- Given 管理员已配置 MiniMax API Key
- And 管理员未配置 GroupId
- When 商家请求配音或查看能力
- Then 系统明确返回“语音服务未配置 GroupId”
- And 不影响营销方案和视频成片主流程

#### Scenario: 配音生成

- Given 管理员已配置 API Key、GroupId、模型和音色
- When 商家为营销项目生成配音
- Then 后端调用 MiniMax T2A HTTP 接口
- And 返回的音频只返回给项目所有者下载
- And API Key 与 GroupId 不返回到前端

## 验收

- 后端定向测试和全量回归通过
- 前端 Vitest、TypeScript、生产构建通过
- 1440px 与 390px 真实页面截图检查通过
- 不提交或输出任何真实 API Key
