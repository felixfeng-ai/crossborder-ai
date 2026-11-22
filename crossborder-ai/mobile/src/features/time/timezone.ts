const FALLBACK_TIME_ZONE = "Asia/Shanghai";

/** 校验 IANA 时区；设备返回异常值时使用产品默认时区。 */
export function normalizeTimeZone(value: string | null | undefined) {
  const candidate = String(value || "").trim();
  if (!candidate) return FALLBACK_TIME_ZONE;
  try {
    new Intl.DateTimeFormat("en-US", { timeZone: candidate }).format();
    return candidate;
  } catch {
    return FALLBACK_TIME_ZONE;
  }
}

/** 读取设备时区，并保证后端总能拿到可识别值。 */
export function currentTimeZone(
  resolve: () => string | undefined = () =>
    Intl.DateTimeFormat().resolvedOptions().timeZone,
) {
  try {
    return normalizeTimeZone(resolve());
  } catch {
    return FALLBACK_TIME_ZONE;
  }
}
