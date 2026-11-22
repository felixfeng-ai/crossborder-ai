import { nowMs } from "./clock";

/**
 * 时间语义统一入口。
 *
 * 页面上出现的时间只有三种口径，不允许各页面自己拼字符串：
 * 1. 过去 —— 「12 分钟前」「4 小时前」
 * 2. 剩余 —— 「差 3 小时 12 分」
 * 3. 时刻 —— 「09:42」「13:42 截止」
 *
 * 所有函数都对脏数据（null、空串、非法日期）返回 null，由调用方决定退化方案，
 * 不允许把 NaN 或 Invalid Date 渲染到界面上。
 */

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

/**
 * 剩余时间超过这个窗口，说明「现在」还没进入这条任务的时效区间（例如凌晨看
 * 当天的计划），此时相对时长会和标题里的时限描述打架，调用方应退回绝对时刻。
 */
export const SLA_WINDOW = 4 * HOUR;

function pad(value: number) {
  return String(value).padStart(2, "0");
}

function parseDate(value?: string | null): Date | null {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

/** 「09:42」。用于精确到分钟的时刻展示。 */
export function clockOf(value?: string | null): string | null {
  const date = parseDate(value);
  if (!date) return null;
  return `${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

/**
 * 过去的相对时间。未来时间（数据时钟异常或计划尚未开始）退回时刻，
 * 绝不显示「-3 分钟前」这类负值。
 */
export function relativePast(
  value?: string | null,
  now: number = nowMs(),
): string | null {
  const date = parseDate(value);
  if (!date) return null;

  const diff = now - date.getTime();
  if (diff < 0) return clockOf(value);
  if (diff < MINUTE) return "刚刚";
  if (diff < HOUR) return `${Math.max(1, Math.round(diff / MINUTE))} 分钟前`;
  if (diff < DAY) return `${Math.round(diff / HOUR)} 小时前`;
  return clockOf(value);
}

/** 「差 3 小时 12 分」。超出 SLA 窗口返回 null。 */
export function remainingTo(
  dueAt?: string | null,
  now: number = nowMs(),
): string | null {
  const due = parseDate(dueAt);
  if (!due) return null;

  const diff = due.getTime() - now;
  if (diff <= 0) return "已超时";
  if (diff > SLA_WINDOW) return null;

  if (diff < HOUR) {
    return `差 ${Math.max(1, Math.round(diff / MINUTE))} 分`;
  }

  const hours = Math.floor(diff / HOUR);
  const minutes = Math.round((diff % HOUR) / MINUTE);
  return minutes === 0 ? `差 ${hours} 小时` : `差 ${hours} 小时 ${minutes} 分`;
}

/**
 * 卡片右下角的时限文案：优先相对时长，退化到绝对截止时刻。
 * 两者都拿不到时返回 null，卡片不显示该字段。
 */
export function deadlineText(
  dueAt?: string | null,
  now: number = nowMs(),
): string | null {
  const remaining = remainingTo(dueAt, now);
  if (remaining) return remaining;
  const clock = clockOf(dueAt);
  return clock ? `${clock} 截止` : null;
}

/**
 * 时间轴填充比例 = 已流逝时间 / 总窗口。
 *
 * 注意语义：这是「时间过去了多少」，不是「任务完成了多少」。
 * 契约里没有任务进度字段，所以时间轴只能表达时效压力，不表达完成度。
 */
export function spanRatio(
  startAt?: string | null,
  dueAt?: string | null,
  now: number = nowMs(),
): number | null {
  const start = parseDate(startAt);
  const due = parseDate(dueAt);
  if (!start || !due) return null;

  const total = due.getTime() - start.getTime();
  if (total <= 0) return null;

  const elapsed = now - start.getTime();
  return Math.min(1, Math.max(0, elapsed / total));
}

/** 「2 小时后」。用于日结这类固定时刻的倒计时。 */
export function untilHour(
  hour: number,
  now: number = nowMs(),
): string | null {
  if (!Number.isFinite(hour) || hour < 0 || hour > 23) return null;

  const target = new Date(now);
  target.setHours(hour, 0, 0, 0);

  let diff = target.getTime() - now;
  if (diff <= 0) {
    target.setDate(target.getDate() + 1);
    diff = target.getTime() - now;
  }

  if (diff < HOUR) return `${Math.max(1, Math.round(diff / MINUTE))} 分钟后`;
  return `${Math.round(diff / HOUR)} 小时后`;
}
