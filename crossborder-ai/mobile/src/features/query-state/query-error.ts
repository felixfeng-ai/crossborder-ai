export type QueryErrorKind =
  | "offline"
  | "auth"
  | "contract"
  | "server"
  | "request"
  | "unknown";

export type QueryErrorCopy = {
  kind: QueryErrorKind;
  title: string;
  description: string;
};

function readStatus(error: unknown) {
  if (!error || typeof error !== "object") return null;
  const status = (error as { status?: unknown }).status;
  return typeof status === "number" ? status : null;
}

function readMessage(error: unknown) {
  if (!error || typeof error !== "object") return "";
  const message = (error as { message?: unknown }).message;
  return typeof message === "string" ? message : "";
}

/**
 * 将请求异常还原成用户可行动的原因，避免把服务端 404 或 5xx 误报成断网。
 */
export function describeQueryError(error: unknown): QueryErrorCopy {
  const status = readStatus(error);

  if (status === 401 || status === 403) {
    return {
      kind: "auth",
      title: "登录状态已失效",
      description: "当前账号需要重新登录，已有本地数据不会被清空。",
    };
  }
  if (status === 404) {
    return {
      kind: "contract",
      title: "App 与服务器版本不一致",
      description: "当前服务端尚未部署这个移动接口，请更新服务后再试。",
    };
  }
  if (status !== null && status >= 500) {
    return {
      kind: "server",
      title: "服务暂时不可用",
      description: "服务器已收到请求，但处理失败；请稍后重试。",
    };
  }
  if (status !== null) {
    return {
      kind: "request",
      title: "请求暂时无法完成",
      description: readMessage(error) || "服务返回了异常状态，请稍后重试。",
    };
  }
  if (error instanceof TypeError) {
    return {
      kind: "offline",
      title: "无法连接服务",
      description: "请检查当前网络、代理或 VPN 后重试。",
    };
  }

  return {
    kind: "unknown",
    title: "暂时无法同步",
    description: "当前页面不会用空数据替代真实状态，请稍后重试。",
  };
}
