const baseUrl = (
  process.env.EXPO_PUBLIC_API_URL || "https://veyaship.com"
).replace(/\/+$/, "");

async function statusOf(path, method = "GET") {
  const response = await fetch(`${baseUrl}${path}`, { method });
  return response.status;
}

async function main() {
  // 先验证公开 API 可达，避免把整体服务故障误判成移动路由缺失。
  const authStatus = await statusOf("/api/v1/auth/login");
  if (authStatus === 404 || authStatus >= 500) {
    throw new Error(`公开 API 不可用，/api/v1/auth/login 返回 ${authStatus}`);
  }

  const requiredRoutes = [
    "/api/mobile/v1/bootstrap",
    "/api/mobile/v1/workspaces/00000000-0000-0000-0000-000000000000/commerce-stores",
  ];

  const missing = [];
  for (const path of requiredRoutes) {
    const status = await statusOf(path);
    // 未登录时返回 401/403 说明路由已部署；404 才是移动后端缺失。
    if (status === 404 || status >= 500) {
      missing.push(`${path} -> ${status}`);
    }
  }

  if (missing.length > 0) {
    throw new Error(
      `生产环境缺少移动 API：\n${missing.map((item) => `- ${item}`).join("\n")}`,
    );
  }

  console.log(`移动 API 检查通过：${baseUrl}`);
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
});
