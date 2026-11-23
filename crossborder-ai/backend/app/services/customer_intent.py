"""客服消息的确定性意图与风险分流。"""

import re
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class CustomerRiskAssessment:
    """Agent 自动处理前必须遵守的客户消息风险结论。"""

    intent: str
    risk_level: str
    priority: str
    auto_reply_candidate: bool
    requires_human: bool
    reasons: tuple[str, ...]

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["reasons"] = list(self.reasons)
        return payload


HIGH_RISK_PATTERNS = (
    r"\blawyer\b",
    r"\battorney\b",
    r"\blawsuit\b",
    r"\bsue\b",
    r"\bchargeback\b",
    r"\blegal action\b",
    r"\bprivacy leak\b",
    r"\bgdpr\b",
    r"律师",
    r"起诉",
    r"报警",
    r"拒付",
    r"法律",
    r"泄露隐私",
)
SPAM_PATTERNS = (
    r"\bunsubscribe\b",
    r"\bseo service\b",
    r"\bmarketing service\b",
    r"\bpromotional list\b",
    r"退订",
    r"推广服务",
)
REFUND_PATTERNS = (
    r"\brefund\b",
    r"\bmoney back\b",
    r"\breturn my money\b",
    r"退款",
    r"退钱",
)
QUALITY_PATTERNS = (
    r"\bbroken\b",
    r"\bdamaged\b",
    r"\bdefective\b",
    r"\bquality\b",
    r"破损",
    r"损坏",
    r"质量",
    r"坏了",
)
DELAY_PATTERNS = (
    r"\bdelay(?:ed)?\b",
    r"\blate\b",
    r"\bnot arrived\b",
    r"\bstill waiting\b",
    r"延迟",
    r"还没到",
    r"超时",
)
SHIPPING_PATTERNS = (
    r"\bparcel\b",
    r"\bshipping\b",
    r"\btracking\b",
    r"\bdelivery\b",
    r"\bwhen.*arrive\b",
    r"物流",
    r"快递",
    r"包裹",
    r"什么时候到",
)
ORDER_PATTERNS = (
    r"\border\b",
    r"\bstatus\b",
    r"\bwhere is my order\b",
    r"订单",
    r"状态",
)
PRE_SALE_PATTERNS = (
    r"\bdo you ship\b",
    r"\bis this available\b",
    r"\bsize\b",
    r"\bmaterial\b",
    r"\bhow much\b",
    r"发货吗",
    r"有货吗",
    r"尺寸",
    r"材质",
    r"多少钱",
)
COMPLAINT_PATTERNS = (
    r"\bcomplaint\b",
    r"\bterrible\b",
    r"\bangry\b",
    r"\bbad service\b",
    r"投诉",
    r"差评",
    r"太差",
)


def _matches(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def _assessment(
    *,
    intent: str,
    risk_level: str,
    reasons: list[str],
    auto_reply_candidate: bool = False,
) -> CustomerRiskAssessment:
    priority = {
        "high": "urgent",
        "medium": "attention",
        "low": "normal",
    }.get(risk_level, "normal")
    return CustomerRiskAssessment(
        intent=intent,
        risk_level=risk_level,
        priority=priority,
        auto_reply_candidate=(
            auto_reply_candidate and risk_level == "low"
        ),
        requires_human=risk_level == "high",
        reasons=tuple(reasons),
    )


def classify_customer_message(
    text: str,
    *,
    is_review: bool = False,
    rating: int | None = None,
) -> CustomerRiskAssessment:
    """按确定性关键词和能力边界分流，不依赖模型置信度。"""

    value = str(text or "").strip()
    lowered = value.lower()

    if _matches(lowered, HIGH_RISK_PATTERNS):
        return _assessment(
            intent="complaint",
            risk_level="high",
            reasons=["检测到法律、拒付或隐私风险"],
        )

    if _matches(lowered, SPAM_PATTERNS):
        return _assessment(
            intent="spam",
            risk_level="low",
            reasons=["检测到退订或推广内容"],
        )

    if is_review:
        reasons = ["客户评价需要公开回复"]
        if rating is not None and rating <= 3:
            reasons.append("中差评默认需要人工确认")
            return _assessment(
                intent="review_response",
                risk_level="medium",
                reasons=reasons,
            )
        return _assessment(
            intent="review_response",
            risk_level="low",
            reasons=reasons,
        )

    if _matches(lowered, REFUND_PATTERNS):
        return _assessment(
            intent="refund_request",
            risk_level="medium",
            reasons=["涉及退款或资金承诺"],
        )

    if _matches(lowered, QUALITY_PATTERNS):
        return _assessment(
            intent="product_quality",
            risk_level="medium",
            reasons=["涉及商品质量或售后"],
        )

    if _matches(lowered, DELAY_PATTERNS):
        return _assessment(
            intent="delivery_delay",
            risk_level="medium",
            reasons=["涉及延迟或未送达"],
        )

    if _matches(lowered, SHIPPING_PATTERNS):
        return _assessment(
            intent="shipping",
            risk_level="low",
            reasons=["标准物流查询"],
            auto_reply_candidate=True,
        )

    if _matches(lowered, ORDER_PATTERNS):
        return _assessment(
            intent="order_status",
            risk_level="low",
            reasons=["标准订单状态查询"],
            auto_reply_candidate=True,
        )

    if _matches(lowered, PRE_SALE_PATTERNS):
        return _assessment(
            intent="pre_sale",
            risk_level="low",
            reasons=["标准售前咨询"],
            auto_reply_candidate=True,
        )

    if _matches(lowered, COMPLAINT_PATTERNS):
        return _assessment(
            intent="complaint",
            risk_level="medium",
            reasons=["客户表达不满，需要谨慎回复"],
        )

    return _assessment(
        intent="other",
        risk_level="medium",
        reasons=["无法归入标准低风险问题"],
    )
