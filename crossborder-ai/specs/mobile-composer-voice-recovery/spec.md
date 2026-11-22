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

## 验收

- 发送按钮状态和语音错误映射有单元测试。
- 后端空运行时配置回退环境变量有测试。
- 生产 API 使用真实语音样本返回转写结果。
- 移动端测试、TypeScript、ESLint 和真实页面检查通过。
