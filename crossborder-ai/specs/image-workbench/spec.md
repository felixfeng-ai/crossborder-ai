# Image Workbench

## 目标

把当前单次 AI 出图页面升级为商品图片工作台：卖家可以上传真实商品图片，在素材库中复用，按目标平台尺寸导出，并生成确定性白底图。

## 能力点

### CAP-01 图片上传

#### Requirement

用户必须能够上传 JPEG、PNG 或 WebP 商品图片。系统必须校验文件类型、文件大小和像素尺寸，去除原始元数据后保存为当前用户素材。

#### Scenario

- Given 用户登录且上传一张有效 PNG
- When 调用图片上传接口
- Then 创建属于当前用户的素材记录
- And 返回素材 ID、尺寸和可访问图片 URL

#### Scenario

- Given 上传内容不是图片或超过大小限制
- When 调用图片上传接口
- Then 返回 400 可读错误
- And 不创建素材记录

### CAP-02 用户素材隔离

#### Requirement

素材列表、处理和删除接口只能访问当前用户自己的素材；图片文件使用不可预测 UUID 地址供浏览器展示。

#### Scenario

- Given 用户 A 上传一张图片
- When 用户 B 请求处理该图片
- Then 返回 404
- And 不生成处理结果

### CAP-03 平台尺寸预设

#### Requirement

系统必须提供跨境电商常用平台主图尺寸。处理图片时按 contain 模式等比缩放并居中放置，禁止拉伸变形。

#### Scenario

- Given 用户选择 Amazon 主图预设
- When 生成平台尺寸图片
- Then 输出宽高必须等于预设尺寸
- And 原图比例保持不变

### CAP-04 白底图处理

#### Requirement

白底处理必须把透明区域合成到白色画布，并使用目标平台尺寸生成 JPEG。若原图不透明，系统保留原图内容并补白边，不宣称完成 AI 抠图。

#### Scenario

- Given 用户上传透明背景商品图
- When 选择平台预设并执行白底处理
- Then 输出图为白底 JPEG
- And 透明区域变为纯白
- And 输出尺寸符合预设

### CAP-05 素材库

#### Requirement

工作台必须同时展示上传素材、白底处理结果和已有 AI 生成图片。用户可以选择素材预览、下载、复制链接或删除自己的上传素材。

#### Scenario

- Given 用户有上传图和处理后图
- When 打开图片工作台
- Then 两类素材都在素材库中可见
- And 用户可以选择任一素材进入预览区

### CAP-06 图片质量与失败提示

#### Requirement

图片质量档位必须映射为 Provider 实际支持的画布尺寸，并按画幅等比计算。任务失败时必须把供应商异常转换为卖家可执行的中文提示，原始英文异常只写入服务端日志。

#### Scenario

- Given 用户选择高清自由创作和 4:5 画幅
- When 提交生成任务
- Then Provider 收到不超过 1440 长边的画布尺寸
- And 高清档不会被转换为 2048 长边

#### Scenario

- Given 图片 Provider 返回尺寸超出范围
- When 任务执行失败
- Then 任务记录返回包含尺寸原因的中文提示
- And 不把供应商原始英文异常展示给卖家

#### Scenario

- Given 用户选择标准或高清自由创作
- When 系统调用阿里云图片服务
- Then 使用万相 2.2 专业模型而不是低质量极速模型
- And 写实人物提示会自动补充塑料皮肤、蜡像感和错误手部等负面约束

### CAP-07 商品场景多 Provider 路由

#### Requirement

商品场景必须按 Provider 能力和配置选择参考图模型，不得写死单一供应商。Seedream
直连使用火山方舟图片生成 API，Replicate Seedream 作为备用参考图通道；自动模式
可以在两个参考图 Provider 之间降级，但禁止降级为普通文生图。

#### Scenario

- Given 管理员配置了火山方舟 Seedream API Key 和模型
- When 用户提交商品场景参考图任务且 Provider 选择自动
- Then 系统优先调用 Seedream 直连
- And 任务记录保存 Provider 为 `seedream`

#### Scenario

- Given Seedream 直连调用失败且 Replicate 参考图模型已配置
- When 商品场景任务处于自动模式
- Then 系统继续尝试 Replicate Seedream
- And 不会改为不带参考图的文生图

#### Scenario

- Given Seedream 和管理员 Key 均未配置
- When 用户提交商品场景任务
- Then 接口返回需要管理员配置参考图 Provider 的中文错误
