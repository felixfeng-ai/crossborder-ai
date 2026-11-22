/**
 * 时间源。
 *
 * 预览模式下数据必须是「可重复的」：同一个页面在任何时刻打开，
 * 相对时间、时间轴圆点都应该落在同一个位置，否则截图无法比对。
 * 所以预览数据在被请求时把时钟锚定到固定的业务时刻；
 * 生产环境永远走真实时钟。
 */
let anchorMs: number | null = null;

export function setClockAnchor(value: number | null) {
  anchorMs = value;
}

export function nowMs(): number {
  return anchorMs ?? Date.now();
}
