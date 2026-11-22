type VoiceFailure = {
  status?: number;
  message?: string;
};

export function describeVoiceFailure(reason: unknown) {
  const failure =
    reason && typeof reason === "object"
      ? (reason as VoiceFailure)
      : {};
  const message = String(failure.message ?? "");

  if (failure.status === 401) {
    return "登录状态已过期，请重新登录后再试。";
  }
  if (failure.status === 400) {
    return "录音格式无法识别，请重新录制一段语音。";
  }
  if (failure.status === 503 && message.includes("尚未配置")) {
    return "语音转写服务暂不可用，请联系管理员检查服务配置。";
  }
  if (failure.status === 503) {
    return "语音转写服务暂时不可用，请稍后重试。";
  }
  return "语音发送失败，请检查网络后重新录制。";
}
