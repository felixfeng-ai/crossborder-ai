# 营销视频字幕与配音规格

## CAP-01 SRT 字幕

- 字幕时间轴严格使用分镜 `duration` 累加，从 0 开始。
- 第一条承载 hook，最后一条承载 cta，中间承载 script。
- SRT 可独立下载；渲染时优先烧录，烧录失败回退为无内嵌字幕成片。
- 响应模型通过 `subtitles_burned_in` 告知前端最终是否成功烧录。

## CAP-02 MiniMax TTS

- 运行时读取 `api_key`、`group_id`、`tts_model`、`voice_id`。
- 只有 API Key 缺少 GroupId 时，能力状态必须明确说明缺少 GroupId。
- T2A 响应中的十六进制音频解码后以 `audio/mpeg` 返回。
- 密钥与 GroupId 不进入前端响应和日志。
