# MiniMax AI Video Generation

## 目标

接入 MiniMax H3 图生视频模型，把图片工作台中的商品首帧转换为短视频。视频任务必须异步、可恢复、可取消，并按模型、分辨率和时长计费。

## 能力点

### CAP-01 模型能力与成本

#### Requirement

系统公开 H3、H3-Highspeed、H3-Lite、H3-Max 的可用分辨率、时长范围和按秒价格，并据此估算平台积分。

#### Scenario

- Given MiniMax API Key 已配置
- When 用户请求视频能力
- Then 返回可用模型、分辨率、时长和积分估算
- And 不暴露 API Key

### CAP-02 图生视频请求

#### Requirement

图生视频必须使用当前用户图片素材作为首帧，并以 data URI 发送，不能泄露服务端文件路径。

#### Scenario

- Given 用户选择自己的原图或白底图
- When 提交图生视频
- Then 请求包含首帧图片和商品一致性 Prompt
- And 其他用户素材返回 404

### CAP-03 异步任务

#### Requirement

视频生成必须实现 queued、running、succeeded、failed、canceled 状态；任务失败或进程重启后可继续对账。

#### Scenario

- Given MiniMax 返回 provider task id
- When 调度器查询到 succeeded
- Then 下载并校验 MP4
- And 保存为当前用户视频素材

### CAP-04 积分与积分保护

#### Requirement

提交 MiniMax 成功后才扣减积分。积分不足时不得调用供应商，也不得创建可执行任务。

#### Scenario

- Given 用户积分不足
- When 提交视频生成
- Then 返回 402
- And 不提交 MiniMax 任务

### CAP-05 视频素材库

#### Requirement

用户可以查看自己的视频任务、播放成片、下载 MP4 和取消运行中任务。

#### Scenario

- Given 用户拥有已完成视频
- When 查询视频历史
- Then 返回本地视频 URL 和任务信息

#### Scenario

- Given 其他用户访问视频文件或任务
- When 读取或取消
- Then 返回 404

