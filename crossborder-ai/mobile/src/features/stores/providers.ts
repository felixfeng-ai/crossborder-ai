export type StoreProviderId = "shopify" | "amazon" | "temu";

export type StoreProvider = {
  id: StoreProviderId;
  title: string;
  description: string;
};

export const STORE_PROVIDERS: StoreProvider[] = [
  {
    id: "shopify",
    title: "Shopify",
    description: "输入店铺域名后前往 Shopify 授权",
  },
  {
    id: "amazon",
    title: "Amazon",
    description: "通过 Seller Central 授权卖家店铺",
  },
  {
    id: "temu",
    title: "Temu",
    description: "使用 Temu 卖家中心完成店铺授权",
  },
];

export function normalizeShopInput(raw: string) {
  const value = raw
    .trim()
    .toLowerCase()
    .replace(/^https?:\/\//, "")
    .replace(/\/.*$/, "")
    .replace(/\.myshopify\.com$/, "");
  return /^[a-z0-9][a-z0-9-]*$/.test(value) ? value : null;
}

export function storeStatusLabel(status: string) {
  if (status === "active") return "已连接";
  if (status === "inactive") return "已停用";
  return "需要检查";
}
