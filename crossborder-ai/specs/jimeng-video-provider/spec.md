# 即梦 / Seedance 视频 Provider

## 目标

在现有统一视频 Provider 抽象下接入火山方舟 Seedance，作为 MiniMax 之后的
第二视频供应商。当前支持 2.0 Mini、2.0 Fast、2.0 Standard 和 2.5 Pro，
默认使用 `doubao-seedance-2-0-260128`。管理员主要配置 API Key 和接口地址。

## 能力一：方舟任务协议

### Requirement

即梦 Provider 必须实现统一协议中的提交、查询、取消和下载能力。

### Scenario: 首帧图生视频

- Given 请求包含一张商品首帧
- When 提交即梦视频任务
- Then 首帧使用 `role=first_frame`
- And 请求包含模型、提示词、清晰度、时长和画幅
- And 请求关闭供应商水印
- And 返回方舟任务 ID

### Scenario: 多商品参考图

- Given 请求包含模型允许范围内的商品参考图
- When 提交即梦视频任务
- Then 每张图片使用 `role=reference_image`
- And 不得同时提交首帧
- And 2.0 最多 9 张、2.5 最多 30 张

### Scenario: 查询与取消

- Given 已获得方舟任务 ID
- When 查询任务
- Then `queued/running/succeeded/failed/cancelled/expired` 被归一为统一状态
- And 成功时返回 `content.video_url`
- When 取消任务
- Then 调用方舟 DELETE 任务接口

## 能力二：配置与可用性

### Requirement

管理员可在服务商配置页保存即梦 API Key、Base URL、模型和分辨率。

### Scenario: 未配置

- Given 管理员尚未配置即梦 API Key
- When 获取视频能力
- Then 即梦档位不出现在可选质量档位中
- And MiniMax 现有档位不受影响

### Scenario: 已配置

- Given 管理员已配置即梦 API Key
- When 获取视频能力
- Then 返回 Seedance 质量档位
- And 用户可创建带 `provider=jimeng` 快照的视频任务

## 能力三：质量档位与执行器

### Requirement

Seedance 档位必须保存模型、分辨率、积分和 Provider 快照。

### Scenario: 创建 Seedance 视频

- Given 用户选择 Seedance 质量档位
- When 创建单视频、营销成片或专业分镜项目
- Then Provider 快照为 `jimeng`
- And 执行器通过 Registry 获取即梦 Adapter
- And MiniMax 既有任务继续使用 `provider=minimax`

## 兼容与失败处理

- 历史任务和项目保持不变。
- 未注册 Provider、鉴权、余额、内容审核、限流和服务端错误继续使用中文业务错误。
- 任务提交失败或运行失败时沿用现有积分退还逻辑。
- 不接入非官方网页逆向接口。

## 验收标准

- 首帧、多参考图、查询、取消和下载均有单元测试。
- 管理员配置写入加密存储并立即刷新缓存。
- 未配置时不展示不可用档位。
- 后端全量测试、前端测试、类型检查和生产构建通过。
