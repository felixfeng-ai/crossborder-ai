import { Buffer } from "node:buffer";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

// 交互后截图：用于确认面板这类需要点开才出现的层。
const [portArg, urlArg, outputDirArg, clickTextArg] = process.argv.slice(2);
const port = Number(portArg || 9336);
const pageUrl = urlArg;
const outputDir = path.resolve(outputDirArg || "artifacts");
const clickText = clickTextArg;

const targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
const target = targets.find((item) => item.type === "page");
if (!target?.webSocketDebuggerUrl) throw new Error("未找到可调试页面");

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

const viewport = { width: 390, height: 844 };
await send("Emulation.setDeviceMetricsOverride", {
  ...viewport,
  screenWidth: viewport.width,
  screenHeight: viewport.height,
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

await new Promise((resolve) => setTimeout(resolve, 1200));
for (let attempt = 0; attempt < 20; attempt += 1) {
  const probe = await send("Runtime.evaluate", {
    expression: "document.body.innerText.trim().length",
    returnByValue: true,
  });
  if (Number(probe?.result?.value) > 0) break;
  await new Promise((resolve) => setTimeout(resolve, 400));
}
await send("Runtime.evaluate", {
  expression: "document.fonts.ready",
  awaitPromise: true,
});

const clickResult = await send("Runtime.evaluate", {
  expression: `(() => {
    const wanted = ${JSON.stringify(clickText)};
    const buttons = Array.from(document.querySelectorAll('[role="button"], button'));
    const target = buttons.find((n) => n.innerText && n.innerText.trim() === wanted)
      || buttons.find((n) => n.innerText && n.innerText.includes(wanted));
    if (!target) {
      return "no-button:" + buttons.map((n) => n.innerText.trim()).slice(0, 12).join("|");
    }
    const r = target.getBoundingClientRect();
    const init = {
      bubbles: true,
      cancelable: true,
      clientX: r.left + r.width / 2,
      clientY: r.top + r.height / 2,
    };
    const pointer = { ...init, pointerId: 1, isPrimary: true, pointerType: "mouse" };
    target.dispatchEvent(new PointerEvent("pointerdown", pointer));
    target.dispatchEvent(new PointerEvent("pointerup", pointer));
    target.dispatchEvent(new MouseEvent("click", init));
    return "dispatched:" + target.tagName + ":" + Math.round(r.top);
  })()`,
  returnByValue: true,
});
console.log(JSON.stringify({ click: clickResult.result.value }));

// 面板有 250-300ms 的滑入动画，等动画结束再截。
await new Promise((resolve) => setTimeout(resolve, 1200));

const metrics = await send("Runtime.evaluate", {
  expression: `(() => ({
    text: document.body.innerText.slice(0, 900),
    width: innerWidth,
    height: innerHeight,
  }))()`,
  returnByValue: true,
});

const screenshot = await send("Page.captureScreenshot", {
  format: "png",
  fromSurface: true,
  captureBeyondViewport: false,
});
const filename = `home-${viewport.width}x${viewport.height}.png`;
await writeFile(path.join(outputDir, filename), Buffer.from(screenshot.data, "base64"));
console.log(JSON.stringify({ file: filename, metrics: metrics.result.value }));

socket.close();
