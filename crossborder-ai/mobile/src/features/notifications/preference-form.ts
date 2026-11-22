type EditableRole = "owner" | "admin" | "operator" | "viewer" | undefined;

type PreferenceDraftInput = {
  timezone: string;
  quietStartHour: number | null;
  quietEndHour: number | null;
};

export function canEditNotificationPreferences(role: EditableRole) {
  return role === "owner" || role === "admin" || role === "operator";
}

export function formatHour(value: number | null | undefined) {
  if (value == null) return "不启用";
  return `${String(value).padStart(2, "0")}:00`;
}

export function validatePreferenceDraft(input: PreferenceDraftInput) {
  try {
    new Intl.DateTimeFormat("en-US", {
      timeZone: input.timezone.trim(),
    }).format();
  } catch {
    return "请输入有效的 IANA 时区";
  }
  const hours = [input.quietStartHour, input.quietEndHour];
  if (
    hours.some(
      (hour) =>
        hour != null &&
        (!Number.isInteger(hour) || hour < 0 || hour > 23),
    )
  ) {
    return "免打扰小时必须在 0–23 之间";
  }
  return "";
}
