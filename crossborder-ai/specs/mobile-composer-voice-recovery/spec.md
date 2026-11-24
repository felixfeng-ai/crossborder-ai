# 移动端输入发送与语音失败恢复

> 状态：已确认实施
> 日期：2026-11-23
> 范围：首页 Composer 发送按钮、语音错误提示和生产服务商配置回退。

## COMPOSER-01 可见发送按钮

### Requirement

文字输入非空且未处于语音模式时，Composer 必须展示明确的发送按钮。
发送中按钮显示加载态，发送完成后恢复语音入口。

### Scenario

- Given 用户输入“帮我上架一个新产品”
- When 输入内容非空
- Then 右侧出现可点击的发送按钮

## VOICE-01 真实转写

### Requirement

生产环境 `ALIYUN_DASHSCOPE_API_KEY` 已配置时，语音上传必须调用真实
Qwen ASR，不得因数据库中的空运行时值被判定为“尚未配置”。

### Scenario

- Given 数据库存在空的 `provider:aliyun:api_key`
- And 环境中存在有效 DashScope Key
- When 用户上传有效语音
- Then 服务回退到环境 Key 并返回转写文本

## VOICE-02 错误恢复

### Requirement

语音失败提示必须区分：

- 麦克风权限被拒绝
- 网络不可用
- 录音格式无效
- 转写服务未配置或暂时不可用
- 登录过期

不得把所有失败都显示为“网络恢复后重试”。

## VOICE-03 豆包优先与可靠降级

### Requirement

移动端语音上传继续使用现有 `audio/transcriptions` 契约，服务端默认优先调用
豆包录音文件极速版识别，并允许复用即梦 / Seedance 的火山方舟 API Key。

- 豆包接口只接收受支持的音频格式；服务端必须把 M4A、WebM 等 App 录音转换为
  16k 单声道 WAV 后再提交。
- 请求携带跨境电商常用热词，提升 Shopify、Temu、TikTok Shop、ASIN、SKU 等
  专有名词的识别准确率。
- 豆包权限、限流、网络或服务异常时自动降级到现有 Qwen ASR。
- 静音、损坏音频和请求参数错误不得触发二次供应商调用。
- 转写结果必须返回实际 `provider` 与 `model`，不得把 Qwen 结果伪装成豆包结果。
- API Key、音频内容和供应商原始响应不得进入日志或面向用户的错误信息。

### Scenario

- Given 生产已通过服务商配置或环境变量提供即梦 Ark Key
- When 用户上传一段 60 秒以内的 M4A 语音
- Then 服务端转为 WAV，调用豆包极速版并返回转写文本
- And 响应标明实际使用的供应商和模型

### Scenario

- Given 即梦 Ark Key 未开通豆包语音资源或服务暂时不可用
- When 豆包返回权限、限流或服务错误
- Then 服务端自动改用 Qwen ASR
- And 最终响应仍标明 `provider=aliyun`

## 验收

- 发送按钮状态和语音错误映射有单元测试。
- 后端空运行时配置回退环境变量有测试。
- 豆包请求头、音频载荷、热词、M4A 转码、权限降级和输入错误不降级有测试。
- 生产 API 使用真实语音样本返回转写结果。
- 移动端测试、TypeScript、ESLint 和真实页面检查通过。
