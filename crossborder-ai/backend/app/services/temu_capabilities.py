"""Temu API scope 到 Agent 业务能力的映射。"""


ACTION_SCOPES = {
    "product.read": {
        "bg.local.goods.list.query",
        "temu.local.goods.list.retrieve",
    },
    "product.publish": {
        "bg.local.goods.add",
        "temu.local.goods.v3.add",
    },
    "product.update": {
        "bg.local.goods.update",
        "bg.local.goods.partial.update",
    },
    "inventory.update": {
        "temu.goods.stock.query",
        "bg.local.goods.stock.edit",
    },
    "pricing.update": {
        "bg.local.goods.priceorder.change.sku.price",
        "bg.local.goods.priceorder.query",
    },
    "order.read": {
        "bg.order.list.v2.get",
        "bg.order.list.get",
        "bg.order.detail.get",
    },
    "fulfillment.write": {
        "bg.logistics.shipment.create",
        "bg.logistics.shipment.confirm",
        "bg.logistics.companies.get",
        "bg.logistics.shipment.v2.confirm",
        "bg.logistics.shipment.v2.get",
    },
    "aftersales.read": {
        "bg.aftersales.aftersales.list.get",
        "bg.aftersales.parentaftersales.list.get",
    },
}


def _normalized_store_type(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"local", "semi", "crossborder"}:
        return normalized
    return "unknown"


def derive_temu_capabilities(
    scopes: list[str] | None,
    *,
    store_type: str | None = None,
) -> dict:
    """按实际授权 scope 计算能力，不把授权店铺等同于全部权限。"""

    granted = {
        str(item).strip()
        for item in scopes or []
        if str(item).strip()
    }
    normalized_store_type = _normalized_store_type(store_type)
    capabilities = {}
    for action, required_scopes in ACTION_SCOPES.items():
        matched = sorted(granted & required_scopes)
        available = bool(matched)
        restriction_required = False
        reason = ""
        uses_local_api = any(
            item.startswith(("bg.local.", "temu.local."))
            for item in matched
        )
        if available and uses_local_api and normalized_store_type == "crossborder":
            restriction_required = True
            reason = "该能力使用 LOCAL/SEMI 接口，跨境店铺需要确认平台支持范围"
        elif (
            available
            and uses_local_api
            and normalized_store_type == "unknown"
        ):
            restriction_required = True
            reason = "当前店铺类型未知，LOCAL/SEMI 接口需先确认店铺类型"
        if (
            available
            and action == "order.read"
            and normalized_store_type in {"crossborder", "unknown"}
        ):
            restriction_required = True
            reason = "Temu 订单列表接口对部分跨境卖家有限制，执行前必须校验店铺类型"
        capabilities[action] = {
            "available": available,
            "restriction_required": restriction_required,
            "reason": reason,
            "scopes": matched,
        }
    return capabilities
