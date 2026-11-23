import { describe, expect, it } from "vitest";

import { describeVoiceFailure } from "./voice-errors";

describe("voice failure recovery", () => {
  it("区分登录过期、录音格式和转写服务配置", () => {
    expect(describeVoiceFailure({ status: 401, message: "未登录" })).toContain(
      "重新登录",
    );
    expect(describeVoiceFailure({ status: 400, message: "格式错误" })).toContain(
      "重新录制",
    );
    expect(
      describeVoiceFailure({
        status: 503,
        message: "语音转写服务尚未配置",
      }),
    ).toContain("服务配置");
  });

  it("网络或未知错误保留重试说明", () => {
    expect(describeVoiceFailure(new TypeError("Network request failed")))
      .toContain("检查网络");
  });

  it("不把未部署的语音接口误报成用户网络问题", () => {
    expect(describeVoiceFailure({ status: 404, message: "Not Found" }))
      .toContain("版本不一致");
  });
});
