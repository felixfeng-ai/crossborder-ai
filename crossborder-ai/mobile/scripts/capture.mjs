import { Buffer } from "node:buffer";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

const [portArg, urlArg, outputDirArg] = process.argv.slice(2);
const port = Number(portArg || 9336);
const pageUrl = urlArg || "http://127.0.0.1:4175";
const outputDir = path.resolve(outputDirArg || "artifacts");

const targets = await (
  await fetch(`http://127.0.0.1:${port}/json/list`)
).json();
const target = targets.find((item) => item.type === "page");
if (!target?.webSocketDebuggerUrl) {
  throw new Error("未找到可调试页面");
}

const socket = new WebSocket(target.webSocketDebuggerUrl);
const pending = new Map();
let nextId = 1;

const send = (method, params = {}) =>
  new Promise((resolve, reject) => {
    const id = nextId++;
    pending.set(id, { resolve, reject });
    socket.send(JSON.stringify({ id, method, params }));
  });

socket.addEventListener("message", (event) => {
  const message = JSON.parse(event.data);
  if (!message.id || !pending.has(message.id)) return;
  const { resolve, reject } = pending.get(message.id);
  pending.delete(message.id);
  if (message.error) reject(new Error(message.error.message));
  else resolve(message.result);
});

await new Promise((resolve, reject) => {
  socket.addEventListener("open", resolve, { once: true });
  socket.addEventListener("error", reject, { once: true });
});

await send("Page.enable");
await send("Runtime.enable");
await mkdir(outputDir, { recursive: true });

for (const viewport of [
  { width: 390, height: 844 },
  { width: 375, height: 812 },
]) {
  await send("Emulation.setDeviceMetricsOverride", {
    ...viewport,
    screenWidth: viewport.width,
    screenHeight: viewport.height,
    // 2 倍图：截图既要验收布局，也要验收发丝线/胶囊边/图标描边的精细度。
    deviceScaleFactor: 2,
    mobile: true,
  });

  const loaded = new Promise((resolve) => {
    const listener = (event) => {
      const message = JSON.parse(event.data);
      if (message.method !== "Page.loadEventFired") return;
      socket.removeEventListener("message", listener);
      resolve();
    };
    socket.addEventListener("message", listener);
  });

  await send("Page.navigate", { url: pageUrl });
  await loaded;
  // 首帧绘制 + 字体落地后再截，否则会截到整页空白。
  // 固定等待在冷启动时不够（首次导出后第一张常是白图），改成轮询到正文出现。
  await new Promise((resolve) => setTimeout(resolve, 1200));
  for (let attempt = 0; attempt < 20; attempt += 1) {
    const probe = await send("Runtime.evaluate", {
      expression: "document.body.innerText.trim().length",
      returnByValue: true,
    });
    if (Number(probe?.result?.value) > 0) break;
    await new Promise((resolve) => setTimeout(resolve, 400));
  }

  const metrics = await send("Runtime.evaluate", {
    expression: `(async () => {
      await document.fonts.ready;
      return {
        title: document.title,
        text: document.body.innerText.slice(0, 1200),
        width: innerWidth,
        height: innerHeight,
        scrollWidth: document.documentElement.scrollWidth,
        scrollHeight: document.documentElement.scrollHeight,
      };
    })()`,
    awaitPromise: true,
    returnByValue: true,
  });

  // 截图只用于视觉验收，不写入生产产物。
  const screenshot = await send("Page.captureScreenshot", {
    format: "png",
    fromSurface: true,
    captureBeyondViewport: false,
  });
  const filename = `home-${viewport.width}x${viewport.height}.png`;
  await writeFile(
    path.join(outputDir, filename),
    Buffer.from(screenshot.data, "base64"),
  );
  console.log(JSON.stringify({ file: filename, metrics: metrics.result.value }));
}

socket.close();
