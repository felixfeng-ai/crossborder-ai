"""把动作输入转换为 App 可读的确认前预览。

只允许白名单字段进入 App，平台凭据、渠道 ID 和内部请求参数不能下发。
"""

import json
from decimal import Decimal, InvalidOperation
from typing import Any

from app.models.action_run import ActionRun
from app.schemas.mobile import ActionPreview, ActionPreviewField


def _input_object(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _string(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def _order_number(value: str) -> str:
    normalized = value.rsplit("/", 1)[-1].strip()
    return f"#{normalized}" if normalized.isdigit() else normalized


def _money(amount: Any, currency: Any) -> str:
    value = _string(amount)
    if not value:
        return "未填写"
    try:
        normalized = f"{Decimal(value):.2f}"
    except (InvalidOperation, ValueError):
        normalized = value
    return f"{_string(currency, 'USD')} {normalized}"


def _base_preview(
    run: ActionRun,
    *,
    title: str,
    description: str,
    fields: list[ActionPreviewField],
    warning: str | None = None,
) -> ActionPreview:
    return ActionPreview(
        action_id=run.action_id,
        platform=run.platform,
        target_type=run.target_type,
        target_id=run.target_id,
        title=title,
        description=description,
        risk=run.risk_level,
        fields=fields,
        warning=warning,
    )


def build_action_preview(
    run: ActionRun | None,
    *,
    fallback_title: str,
) -> ActionPreview | None:
    if run is None:
        return None
    data = _input_object(run.input_json)
    high_risk_warning = (
        "该操作会真实写入平台，提交后不能在这里直接撤销。"
        if run.risk_level == "high"
        else None
    )
    if not data:
        titles = {
            "listings.publish": "即将发布商品",
            "orders.fulfill": "即将标记发货",
            "refunds.create": "即将发起退款",
            "messages.reply": "即将发送客户回复",
            "reviews.reply": "即将发布评价回复",
        }
        return _base_preview(
            run,
            title=titles.get(run.action_id, fallback_title),
            description="确认后执行当前动作并回读平台结果。",
            fields=[
                ActionPreviewField(
                    label="目标",
                    value=run.target_id,
                    emphasis=True,
                )
            ],
            warning=high_risk_warning,
        )

    if run.action_id == "orders.fulfill":
        return _base_preview(
            run,
            title="即将标记发货",
            description="确认后向 Shopify 提交履约和物流信息，并回读实际发货状态。",
            fields=[
                ActionPreviewField(
                    label="订单",
                    value=_order_number(run.target_id),
                    emphasis=True,
                ),
                ActionPreviewField(
                    label="承运商",
                    value=_string(data.get("tracking_company"), "未填写"),
                ),
                ActionPreviewField(
                    label="物流单号",
                    value=_string(data.get("tracking_number"), "未填写"),
                ),
                ActionPreviewField(
                    label="通知买家",
                    value="是" if data.get("notify_customer", True) else "否",
                ),
            ],
            warning=high_risk_warning,
        )

    if run.action_id == "refunds.create":
        return _base_preview(
            run,
            title="即将发起退款",
            description="确认后创建真实退款交易，并回读订单退款状态。",
            fields=[
                ActionPreviewField(
                    label="订单",
                    value=_order_number(run.target_id),
                    emphasis=True,
                ),
                ActionPreviewField(
                    label="退款金额",
                    value=_money(data.get("amount"), data.get("currency")),
                    emphasis=True,
                ),
                ActionPreviewField(
                    label="原因",
                    value=_string(data.get("reason"), "未填写"),
                ),
            ],
            warning="退款提交后无法在 App 内直接撤销。",
        )

    if run.action_id == "orders.cancel":
        return _base_preview(
            run,
            title="即将取消订单",
            description="确认后取消 Shopify 订单，并按选项处理退款、库存和买家通知。",
            fields=[
                ActionPreviewField(
                    label="订单",
                    value=_order_number(run.target_id),
                    emphasis=True,
                ),
                ActionPreviewField(
                    label="原因",
                    value=_string(data.get("reason"), "customer"),
                ),
                ActionPreviewField(
                    label="回补库存",
                    value="是" if data.get("restock", True) else "否",
                ),
                ActionPreviewField(
                    label="退款",
                    value="是" if data.get("refund", False) else "否",
                ),
                ActionPreviewField(
                    label="通知买家",
                    value="是" if data.get("notify_customer", True) else "否",
                ),
            ],
            warning="订单取消后无法在 App 内直接恢复，请确认退款和库存选项。",
        )

    if run.action_id == "pricing.update":
        below_cost = bool(data.get("below_cost"))
        return _base_preview(
            run,
            title="即将修改销售价",
            description="确认后写回 Shopify 变体价格，并重新读取平台价格。",
            fields=[
                ActionPreviewField(
                    label="SKU",
                    value=_string(data.get("sku"), run.target_id),
                    emphasis=True,
                ),
                ActionPreviewField(
                    label="新价格",
                    value=_string(data.get("price"), "未填写"),
                    emphasis=True,
                ),
            ],
            warning=(
                "新价格低于当前成本价，请确认毛利风险。"
                if below_cost
                else high_risk_warning
            ),
        )

    if run.action_id == "inventory.update":
        return _base_preview(
            run,
            title="即将更新库存",
            description="确认后写回 Shopify 库存地点，并回读实际可用库存。",
            fields=[
                ActionPreviewField(
                    label="SKU",
                    value=_string(data.get("sku"), run.target_id),
                    emphasis=True,
                ),
                ActionPreviewField(
                    label="库存",
                    value=f"{data.get('stock_quantity')} 件",
                    emphasis=True,
                ),
            ],
            warning=high_risk_warning,
        )

    if run.action_id == "listings.update":
        fields: list[ActionPreviewField] = []
        if data.get("title"):
            fields.append(
                ActionPreviewField(
                    label="标题",
                    value=_string(data.get("title")),
                    emphasis=True,
                )
            )
        if data.get("status"):
            status_labels = {
                "active": "上架",
                "draft": "草稿",
                "archived": "归档",
            }
            fields.append(
                ActionPreviewField(
                    label="状态",
                    value=status_labels.get(
                        _string(data.get("status")),
                        _string(data.get("status")),
                    ),
                )
            )
        if "description" in data:
            fields.append(
                ActionPreviewField(
                    label="描述",
                    value=_string(data.get("description"), "清空描述"),
                )
            )
        return _base_preview(
            run,
            title="即将更新商品内容",
            description="确认后写入 Shopify 商品并回读标题、描述和状态。",
            fields=fields,
            warning=high_risk_warning,
        )

    if run.action_id == "listing.media.attach":
        asset_ids = data.get("asset_ids")
        count = len(asset_ids) if isinstance(asset_ids, list) else 0
        return _base_preview(
            run,
            title="即将附加商品图片",
            description="确认后把所选图片上传到 Shopify 商品并回读图片结果。",
            fields=[
                ActionPreviewField(
                    label="Listing",
                    value=run.target_id,
                    emphasis=True,
                ),
                ActionPreviewField(
                    label="图片",
                    value=f"{count} 张",
                    emphasis=True,
                ),
            ],
            warning=high_risk_warning,
        )

    if run.action_id == "listings.publish":
        fields = [
            ActionPreviewField(
                label="商品",
                value=_string(data.get("title"), fallback_title),
                emphasis=True,
            )
        ]
        variants = data.get("variant_ids")
        if isinstance(variants, list) and variants:
            fields.append(
                ActionPreviewField(
                    label="变体",
                    value=f"{len(variants)} 个",
                )
            )
        if data.get("image_count") is not None:
            fields.append(
                ActionPreviewField(
                    label="图片",
                    value=f"{data.get('image_count')} 张",
                )
            )
        if data.get("shop_domain"):
            fields.append(
                ActionPreviewField(
                    label="店铺",
                    value=_string(data.get("shop_domain")),
                )
            )
        return _base_preview(
            run,
            title="即将发布商品",
            description="确认后在 Shopify 创建商品、变体和媒体，并回读平台结果。",
            fields=fields,
            warning=high_risk_warning,
        )

    if run.action_id == "amazon.listings.publish":
        return _base_preview(
            run,
            title="即将发布到 Amazon",
            description=(
                "确认后通过 SP-API Listings Items 提交商品，"
                "并按 SKU 与 Marketplace 回读 Listing。"
            ),
            fields=[
                ActionPreviewField(
                    label="商品",
                    value=_string(
                        data.get("title"),
                        fallback_title,
                    ),
                    emphasis=True,
                ),
                ActionPreviewField(
                    label="SKU",
                    value=_string(data.get("sku"), "未填写"),
                ),
                ActionPreviewField(
                    label="Marketplace",
                    value=_string(data.get("marketplace_id"), "未填写"),
                ),
                ActionPreviewField(
                    label="Product Type",
                    value=_string(data.get("product_type"), "未填写"),
                ),
            ],
            warning=(
                "该操作会真实提交到 Amazon。权限、类目属性和商品状态"
                "以提交后的平台回读为准。"
            ),
        )

    if run.action_id == "amazon.orders.fulfill":
        return _base_preview(
            run,
            title="即将确认 Amazon 发货",
            description=(
                "确认后向 Amazon 提交商户自履约发货信息，"
                "并按订单包邮件回读物流单号。"
            ),
            fields=[
                ActionPreviewField(
                    label="订单",
                    value=_string(data.get("order_id"), run.target_id),
                    emphasis=True,
                ),
                ActionPreviewField(
                    label="Marketplace",
                    value=_string(data.get("marketplace_id"), "未填写"),
                ),
                ActionPreviewField(
                    label="承运商",
                    value=_string(
                        data.get("carrier_name")
                        or data.get("carrier_code"),
                        "未填写",
                    ),
                ),
                ActionPreviewField(
                    label="物流单号",
                    value=_string(data.get("tracking_number"), "未填写"),
                ),
                ActionPreviewField(
                    label="发货日期",
                    value=_string(data.get("ship_date"), "立即"),
                ),
                ActionPreviewField(
                    label="商品数量",
                    value=f"{data.get('item_count', 0)} 件",
                ),
            ],
            warning=(
                "Amazon 发货确认会真实更新订单履约状态；"
                "提交后不能在本页直接撤销。"
            ),
        )

    if run.action_id == "temu.orders.fulfill":
        warehouse = _string(
            data.get("self_shipping_warehouse_id"),
            "未填写",
        )
        return _base_preview(
            run,
            title="即将确认 Temu 发货",
            description=(
                "确认后向 Temu 提交卖家自发货信息，"
                "并按每个子订单回读物流单号。"
            ),
            fields=[
                ActionPreviewField(
                    label="父订单",
                    value=_string(
                        data.get("parent_order_sn"),
                        run.target_id,
                    ),
                    emphasis=True,
                ),
                ActionPreviewField(
                    label="承运商",
                    value=_string(
                        data.get("carrier_name")
                        or data.get("carrier_id"),
                        "未填写",
                    ),
                ),
                ActionPreviewField(
                    label="物流单号",
                    value=_string(data.get("tracking_number"), "未填写"),
                ),
                ActionPreviewField(
                    label="仓库",
                    value=warehouse,
                ),
                ActionPreviewField(
                    label="商品数量",
                    value=f"{data.get('item_count', 0)} 件",
                ),
            ],
            warning=(
                "Temu 自发货会真实更新订单履约状态；"
                "同一物流单号只能完成一次发货，提交后不能在本页撤销。"
            ),
        )

    if run.action_id == "temu.listings.submit":
        return _base_preview(
            run,
            title="即将提交 Temu 商品",
            description=(
                "确认后先把所选图片发布为公网 HTTPS 地址，"
                "再调用 Temu V3 创建商品并回读。"
            ),
            fields=[
                ActionPreviewField(
                    label="Listing",
                    value=run.target_id,
                    emphasis=True,
                ),
                ActionPreviewField(
                    label="类目",
                    value=_string(
                        data.get("category_name"),
                        "未填写",
                    ),
                ),
                ActionPreviewField(
                    label="币种",
                    value=_string(data.get("currency"), "未填写"),
                ),
                ActionPreviewField(
                    label="图片",
                    value=f"{data.get('asset_count', 0)} 张",
                ),
                ActionPreviewField(
                    label="SKU",
                    value=f"{data.get('sku_count', 0)} 个",
                ),
                ActionPreviewField(
                    label="库存",
                    value=f"{data.get('item_count', 0)} 件",
                ),
            ],
            warning=(
                "所选图片会变成公网可访问图片。提交成功只代表 Temu 已受理，"
                "商品是否可售以 Temu 后续原始状态为准。"
            ),
        )

    if run.action_id == "temu.inventory.update":
        current = data.get("current_stock")
        target = data.get("stock_target")
        return _base_preview(
            run,
            title="即将更新 Temu 库存",
            description=(
                "确认后按目标值覆写 Temu 普通库存，"
                "并重新读取该 SKU 的平台库存。"
            ),
            fields=[
                ActionPreviewField(
                    label="SKU",
                    value=_string(data.get("sku"), run.target_id),
                    emphasis=True,
                ),
                ActionPreviewField(
                    label="商品 ID",
                    value=_string(data.get("goods_id"), "未填写"),
                ),
                ActionPreviewField(
                    label="Temu SKU ID",
                    value=_string(data.get("sku_id"), "未填写"),
                ),
                ActionPreviewField(
                    label="库存",
                    value=(
                        f"{_string(current, '未知')} → "
                        f"{_string(target, '未填写')} 件"
                    ),
                    emphasis=True,
                ),
            ],
            warning=(
                "该动作覆写 Temu 普通库存，不使用增量；"
                "预售库存不会修改。"
            ),
        )

    if run.action_id == "temu.pricing.submit":
        return _base_preview(
            run,
            title="即将提交 Temu 价格变更",
            description=(
                "确认后向 Temu 提交新的基础供货价，"
                "并回读是否创建价格审核单。"
            ),
            fields=[
                ActionPreviewField(
                    label="SKU",
                    value=_string(data.get("sku"), run.target_id),
                    emphasis=True,
                ),
                ActionPreviewField(
                    label="当前本地参考价",
                    value=_money(
                        data.get("current_local_price"),
                        data.get("currency"),
                    ),
                ),
                ActionPreviewField(
                    label="新供货价",
                    value=_money(
                        data.get("amount"),
                        data.get("currency"),
                    ),
                    emphasis=True,
                ),
                ActionPreviewField(
                    label="原因",
                    value=_string(data.get("reason"), "未填写"),
                ),
            ],
            warning=(
                "新供货价是卖家结算基础价，不等于买家售价。"
                "提交成功只代表进入 Temu 价格审核，不代表售价已生效。"
            ),
        )

    if run.action_id in {
        "amazon.inventory.update",
        "amazon.pricing.update",
    }:
        is_inventory = run.action_id == "amazon.inventory.update"
        return _base_preview(
            run,
            title=(
                "即将更新 Amazon 库存"
                if is_inventory
                else "即将修改 Amazon 售价"
            ),
            description=(
                "确认后只 PATCH 目标属性，并回读 Amazon Listing。"
            ),
            fields=[
                ActionPreviewField(
                    label="SKU",
                    value=_string(data.get("sku"), run.target_id),
                    emphasis=True,
                ),
                ActionPreviewField(
                    label="Marketplace",
                    value=_string(data.get("marketplace_id"), "未填写"),
                ),
                ActionPreviewField(
                    label="变更前",
                    value=_string(data.get("before_value"), "未知"),
                ),
                ActionPreviewField(
                    label="变更后",
                    value=_string(data.get("after_value"), "未填写"),
                    emphasis=True,
                ),
            ],
            warning=(
                "库存更新只影响 DEFAULT fulfillment channel。"
                if is_inventory
                else "售价更新会真实改变买家看到的价格。"
            ),
        )

    if run.action_id == "amazon.listings.update":
        label_map = {
            "title": "标题",
            "description": "描述",
            "bullet_points": "卖点",
        }
        changed = data.get("changed_fields")
        changed_text = "、".join(
            label_map.get(str(item), str(item))
            for item in changed
        ) if isinstance(changed, list) and changed else "未填写"
        return _base_preview(
            run,
            title="即将更新 Amazon Listing",
            description=(
                "确认后局部 PATCH 标题、描述或卖点，"
                "并回读 Amazon Listing 属性。"
            ),
            fields=[
                ActionPreviewField(
                    label="SKU",
                    value=_string(data.get("sku"), run.target_id),
                    emphasis=True,
                ),
                ActionPreviewField(
                    label="Marketplace",
                    value=_string(data.get("marketplace_id"), "未填写"),
                ),
                ActionPreviewField(
                    label="修改字段",
                    value=changed_text,
                    emphasis=True,
                ),
            ],
            warning="提交后旧版本合规结果会失效，需要重新检查。",
        )

    if run.action_id == "amazon.listing.media.attach":
        return _base_preview(
            run,
            title="即将绑定 Amazon Listing 图片",
            description=(
                "确认后把持久图片 URL 写入 Amazon 图片定位器，"
                "并回读 Listing 图片属性。"
            ),
            fields=[
                ActionPreviewField(
                    label="SKU",
                    value=_string(data.get("sku"), run.target_id),
                    emphasis=True,
                ),
                ActionPreviewField(
                    label="Marketplace",
                    value=_string(data.get("marketplace_id"), "未填写"),
                ),
                ActionPreviewField(
                    label="图片",
                    value=f"{data.get('image_count', 0)} 张",
                    emphasis=True,
                ),
            ],
            warning=(
                "图片必须是 Amazon 可访问的持久 HTTPS 或 S3 URL，"
                "临时签名地址会失效。"
            ),
        )

    if run.action_id == "amazon.listing.media.attach_assets":
        return _base_preview(
            run,
            title="即将发布并绑定 Amazon 图片",
            description=(
                "确认后先把所选工作区图片发布为公共 URL，"
                "再绑定到 Amazon Listing，并回读图片定位器。"
            ),
            fields=[
                ActionPreviewField(
                    label="Listing",
                    value=run.target_id,
                    emphasis=True,
                ),
                ActionPreviewField(
                    label="Marketplace",
                    value=_string(data.get("marketplace_id"), "未填写"),
                ),
                ActionPreviewField(
                    label="图片",
                    value=f"{data.get('asset_count', 0)} 张",
                    emphasis=True,
                ),
                ActionPreviewField(
                    label="公开范围",
                    value="Amazon 可访问的公网图片",
                ),
            ],
            warning=(
                "所选素材会变成公网可访问图片；请确认图片不含隐私信息。"
            ),
        )

    if run.action_id == "reviews.reply":
        fields = [
            ActionPreviewField(
                label="评价",
                value=_string(
                    data.get("product_title"),
                    data.get("review_id", run.target_id),
                ),
                emphasis=True,
            )
        ]
        if data.get("rating") is not None:
            fields.append(
                ActionPreviewField(
                    label="星级",
                    value=f"{data.get('rating')} 星",
                )
            )
        if data.get("body_text"):
            fields.append(
                ActionPreviewField(
                    label="回复",
                    value=_string(data.get("body_text"))[:240],
                    emphasis=True,
                )
            )
        return _base_preview(
            run,
            title="即将公开发布评价回复",
            description=(
                "确认后把当前回复发布到 Judge.me 公开评价页，"
                "并尽量回读平台结果。"
            ),
            fields=fields,
            warning=(
                "公开回复会展示在商品评价页。Judge.me 当前公开接口"
                "可能只确认受理，不返回回复正文。"
            ),
        )

    if run.action_id in {"messages.reply", "orders.delay_notice"}:
        fields = [
            ActionPreviewField(
                label="目标",
                value=_string(data.get("to"), run.target_id),
            )
        ]
        if data.get("subject"):
            fields.append(
                ActionPreviewField(
                    label="主题",
                    value=_string(data.get("subject")),
                )
            )
        if data.get("language"):
            fields.append(
                ActionPreviewField(
                    label="语言",
                    value=_string(data.get("language")),
                )
            )
        attachment_ids = data.get("attachment_asset_ids")
        if isinstance(attachment_ids, list) and attachment_ids:
            fields.append(
                ActionPreviewField(
                    label="附件",
                    value=f"{len(attachment_ids)} 张图片",
                )
            )
        return _base_preview(
            run,
            title=(
                "即将发送客户回复"
                if run.action_id == "messages.reply"
                else "即将发送延迟说明"
            ),
            description="确认后发送当前回复草稿，并回读客户渠道发送状态。",
            fields=fields,
            warning=high_risk_warning,
        )

    return _base_preview(
        run,
        title=fallback_title,
        description="确认后执行当前动作并回读平台结果。",
        fields=[
            ActionPreviewField(
                label="目标",
                value=run.target_id,
                emphasis=True,
            )
        ],
        warning=high_risk_warning,
    )
