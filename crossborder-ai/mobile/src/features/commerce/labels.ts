import type { TimelineCommerce } from "@/api/types";

/**
 * 币种符号表。认不出的币种一律显示代码本身（例如 USD），
 * 绝不默认成 ¥ —— 默认符号等于把用户的钱数报错。
 */
const CURRENCY_SYMBOLS: Record<string, string> = {
  CNY: "¥",
  USD: "$",
  EUR: "€",
  GBP: "£",
  JPY: "JP¥",
  HKD: "HK$",
  SGD: "S$",
  AUD: "A$",
  CAD: "C$",
};

/**
 * 「涉及 2 单 ¥1,284」。
 * 金额是字符串：先用 Number 判断能否安全格式化，不能就原样输出，
 * 绝不让 NaN 或 1,284.000000001 出现在界面上。
 */
export function commerceLabel(
  commerce?: TimelineCommerce | null,
): string | null {
  if (!commerce) return null;

  const amount = commerce.amount?.trim();
  if (!amount) return null;

  const numeric = Number(amount);
  const value = Number.isFinite(numeric)
    ? numeric.toLocaleString("zh-CN", { maximumFractionDigits: 2 })
    : amount;

  const code = commerce.currency?.trim().toUpperCase() ?? "";
  const symbol = code ? (CURRENCY_SYMBOLS[code] ?? `${code} `) : "";
  const money = `${symbol}${value}`;

  // 只有一单时不写「涉及 1 单」：跨订单聚合还没做，单个订单说「涉及几单」是句废话。
  return commerce.order_count && commerce.order_count > 1
    ? `涉及 ${commerce.order_count} 单 ${money}`
    : money;
}

/**
 * 商品缩略图最多三张：再多会把列表行挤变形，也失去「一眼扫过」的作用。
 * 只接受 http(s) 与同源绝对路径：脏数据（本地文件路径、base64 大串）会把 Image 组件弄崩。
 */
export function thumbnailsOf(value?: string[] | null): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => (typeof item === "string" ? item.trim() : ""))
    .filter((item) => /^(https?:\/\/|\/)[^/]/i.test(item))
    .slice(0, 3);
}
