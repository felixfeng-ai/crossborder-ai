import { spawn } from "node:child_process";
import { mkdir } from "node:fs/promises";
import path from "node:path";

/**
 * 一键截图：导出预览包（可跳过）→ 复用或启动预览服务 → 截 390x844 与 375x812。
 *
 *   node scripts/shot.mjs --route /plan
 *   node scripts/shot.mjs --route / --skip-export
 *
 * 前置：需要一个开着 CDP 的 Chrome（端口 9336）。没有时脚本会提示而不是静默失败。
 */

const CDP_PORT = 9336;
const PREVIEW_PORT = 4193;
const BUILD_DIR = "dist-preview-v40";

const argv = process.argv.slice(2);
const opts = { route: "/", out: null, export: true };
for (let i = 0; i < argv.length; i += 1) {
  const flag = argv[i];
  if (flag === "--route") opts.route = argv[i + 1] ?? "/";
  else if (flag === "--out") opts.out = argv[i + 1] ?? null;
  else if (flag === "--skip-export") opts.export = false;
}

const slug =
  opts.route.replace(/[^a-z0-9]+/gi, "-").replace(/^-+|-+$/g, "") || "root";
const outDir = opts.out ?? path.join("artifacts", "ui-verify", slug);
await mkdir(outDir, { recursive: true });

function run(command, args) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      stdio: "inherit",
      shell: process.platform === "win32",
    });
    child.on("exit", (code) =>
      code === 0 ? resolve() : reject(new Error(`${command} 退出码 ${code}`)),
    );
  });
}

if (opts.export) {
  // 截图链路始终走预览数据：没有这个开关，导出包会连真实 API 并显示空态。
  process.env.EXPO_PUBLIC_PREVIEW_MODE = "1";
  await run("npx", ["expo", "export", "--platform", "web", "--output-dir", BUILD_DIR]);
}

try {
  const probe = await fetch(`http://127.0.0.1:${PREVIEW_PORT}/`, {
    signal: AbortSignal.timeout(3000),
  });
  if (!probe.ok) throw new Error("preview server not ok");
} catch {
  const server = spawn("node", ["scripts/spa-preview-server.mjs"], {
    detached: true,
    stdio: "ignore",
    shell: process.platform === "win32",
    env: {
      ...process.env,
      PREVIEW_ROOT: path.resolve(BUILD_DIR),
      PORT: String(PREVIEW_PORT),
    },
  });
  server.unref();
  await new Promise((resolve) => setTimeout(resolve, 1500));
}

try {
  const cdp = await fetch(`http://127.0.0.1:${CDP_PORT}/json/version`, {
    signal: AbortSignal.timeout(3000),
  });
  if (!cdp.ok) throw new Error("cdp not ok");
} catch {
  console.error(
    `未发现 CDP 端口 ${CDP_PORT}。请先开启调试端口：\n` +
      '  chrome.exe --headless=new --remote-debugging-port=9336 --user-data-dir=.chrome-preview about:blank',
  );
  process.exit(1);
}

const target = `http://127.0.0.1:${PREVIEW_PORT}${opts.route}?v=${Date.now()}`;
await run("node", ["scripts/capture.mjs", String(CDP_PORT), target, outDir]);
console.log(`截图输出目录：${outDir}`);
