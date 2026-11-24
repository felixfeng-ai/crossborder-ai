import type { SourcingSourceItem } from "@/api/types";

/** 从已选 1688 货源生成利润分析指令，保持 App 不直接执行采购动作。 */
export function buildSourceProfitPrompt(
  source: SourcingSourceItem,
): string {
  const lines = [
    "请使用 analyze_product_decision 分析下面这个 1688 货源能不能做。",
    `商品：${source.title}`,
    `1688 链接：${source.url}`,
  ];
  if (source.price) lines.push(`页面采购价：${source.price}`);
  if (source.moq != null) lines.push(`MOQ：${source.moq}`);
  lines.push(
    "采购价、物流、平台佣金或履约费用缺少时请明确向我补充。",
    "只做利润和风险分析，不要自动下单或付款；也不要自动询价、加购。",
  );
  return lines.join("\n");
}
