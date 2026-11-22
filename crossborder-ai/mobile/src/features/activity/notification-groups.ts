import type { NotificationItem } from "@/api/types";

export type NotificationDisplayItem = NotificationItem & {
  timeLabel: string;
  typeLabel: string;
  unread: boolean;
};

export type NotificationDayGroup = {
  key: string;
  title: string;
  items: NotificationDisplayItem[];
};

type GroupNotificationsOptions = {
  now?: Date;
  timeZone?: string;
};

const typeLabels: Record<string, string> = {
  needs_action: "待处理",
  morning_brief: "今日计划",
  day_closeout: "日结",
  action_failed: "执行失败",
  authorization_expired: "需要重新连接",
};

function dateParts(value: Date, timeZone: string) {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(value);
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return {
    year: Number(values.year),
    month: Number(values.month),
    day: Number(values.day),
  };
}

function dateKey(value: Date, timeZone: string) {
  const parts = dateParts(value, timeZone);
  return `${parts.year}-${String(parts.month).padStart(2, "0")}-${String(
    parts.day,
  ).padStart(2, "0")}`;
}

function dayDifference(
  value: Date,
  now: Date,
  timeZone: string,
) {
  const current = dateParts(now, timeZone);
  const target = dateParts(value, timeZone);
  const currentUtc = Date.UTC(current.year, current.month - 1, current.day);
  const targetUtc = Date.UTC(target.year, target.month - 1, target.day);
  return Math.round((currentUtc - targetUtc) / 86_400_000);
}

function groupTitle(value: Date, now: Date, timeZone: string) {
  const difference = dayDifference(value, now, timeZone);
  if (difference === 0) return "今天";
  if (difference === 1) return "昨天";
  const parts = dateParts(value, timeZone);
  return `${parts.month}月${parts.day}日`;
}

function timeLabel(value: Date, timeZone: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone,
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(value);
}

export function groupNotificationsByDay(
  items: NotificationItem[],
  options: GroupNotificationsOptions = {},
): NotificationDayGroup[] {
  const now = options.now ?? new Date();
  const timeZone =
    options.timeZone ??
    Intl.DateTimeFormat().resolvedOptions().timeZone ??
    "Asia/Shanghai";
  const sorted = [...items].sort(
    (left, right) =>
      new Date(right.created_at).getTime() -
      new Date(left.created_at).getTime(),
  );
  const groups = new Map<string, NotificationDayGroup>();

  for (const item of sorted) {
    const createdAt = new Date(item.created_at);
    const key = dateKey(createdAt, timeZone);
    const group = groups.get(key) ?? {
      key,
      title: groupTitle(createdAt, now, timeZone),
      items: [],
    };
    group.items.push({
      ...item,
      timeLabel: timeLabel(createdAt, timeZone),
      typeLabel: typeLabels[item.notification_type] ?? "提醒",
      unread: !item.read_at,
    });
    groups.set(key, group);
  }

  return [...groups.values()];
}
