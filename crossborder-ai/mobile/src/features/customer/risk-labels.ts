const intentLabels: Record<string, string> = {
  shipping: "物流查询",
  order_status: "订单状态",
  refund_request: "退款请求",
  product_quality: "商品质量",
  delivery_delay: "物流延迟",
  complaint: "投诉",
  review_response: "评价回复",
  pre_sale: "售前咨询",
  spam: "垃圾消息",
  other: "客户消息",
};

const riskLabels: Record<string, string> = {
  high: "高风险",
  medium: "需要确认",
  low: "常规",
};

export function customerIntentLabel(intent?: string | null) {
  return (intent && intentLabels[intent]) || "客户消息";
}

export function customerRiskLabel(risk?: string | null) {
  return (risk && riskLabels[risk]) || "需要确认";
}
