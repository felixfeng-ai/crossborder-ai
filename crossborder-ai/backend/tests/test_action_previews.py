"""高风险动作确认前预览测试。"""

from uuid import uuid4

from app.models.action_run import ActionRun
from app.services.action_previews import build_action_preview


def action_run(
    action_id: str,
    *,
    target_id: str,
    input_json: str,
) -> ActionRun:
    return ActionRun(
        id=uuid4(),
        workspace_id=uuid4(),
        work_item_id=uuid4(),
        action_id=action_id,
        platform="shopify",
        target_type="order",
        target_id=target_id,
        input_json=input_json,
        status="awaiting_confirmation",
        risk_level="high",
        autonomy_level="confirm",
        idempotency_key=f"preview-{uuid4()}",
    )


def test_fulfillment_preview_exposes_tracking_but_not_channel_credentials():
    preview = build_action_preview(
        action_run(
            "orders.fulfill",
            target_id="order/9001",
            input_json=(
                '{"tracking_company":"UPS","tracking_number":"TRACK-1",'
                '"channel_id":"secret-channel-id","notify_customer":true}'
            ),
        ),
        fallback_title="订单准备发货",
    )

    assert preview is not None
    assert preview.title == "即将标记发货"
    assert {field.label: field.value for field in preview.fields} == {
        "订单": "#9001",
        "承运商": "UPS",
        "物流单号": "TRACK-1",
        "通知买家": "是",
    }
    assert "secret-channel-id" not in preview.model_dump_json()


def test_refund_preview_formats_amount_and_risk_warning():
    preview = build_action_preview(
        action_run(
            "refunds.create",
            target_id="9002",
            input_json=(
                '{"amount":"30.00","currency":"USD",'
                '"reason":"商品破损"}'
            ),
        ),
        fallback_title="买家申请退款",
    )

    assert preview is not None
    assert preview.title == "即将发起退款"
    assert preview.warning
    assert {field.label: field.value for field in preview.fields} == {
        "订单": "#9002",
        "退款金额": "USD 30.00",
        "原因": "商品破损",
    }


def test_invalid_action_input_uses_safe_fallback_preview():
    preview = build_action_preview(
        action_run(
            "listings.publish",
            target_id="product-1",
            input_json="{broken-json",
        ),
        fallback_title="新品准备发布",
    )

    assert preview is not None
    assert preview.title == "即将发布商品"
    assert preview.fields[0].label == "目标"
    assert preview.fields[0].value == "product-1"


def test_delay_notice_uses_customer_message_preview():
    preview = build_action_preview(
        action_run(
            "orders.delay_notice",
            target_id="thread-1",
            input_json=(
                '{"language":"en","subject":"Order delay",'
                '"to":"buyer@example.com"}'
            ),
        ),
        fallback_title="延迟说明",
    )

    assert preview is not None
    assert preview.title == "即将发送延迟说明"
    assert {field.label: field.value for field in preview.fields} == {
        "目标": "buyer@example.com",
        "主题": "Order delay",
        "语言": "en",
    }


def test_email_reply_preview_reports_attachment_count_without_asset_ids():
    preview = build_action_preview(
        action_run(
            "messages.reply",
            target_id="thread-1",
            input_json=(
                '{"to":"buyer@example.com",'
                '"attachment_asset_ids":["asset-1","asset-2"]}'
            ),
        ),
        fallback_title="确认发送回复",
    )

    assert preview is not None
    fields = {field.label: field.value for field in preview.fields}
    assert fields["附件"] == "2 张图片"
    assert "asset-1" not in preview.model_dump_json()


def test_amazon_publish_preview_shows_marketplace_and_product_type():
    preview = build_action_preview(
        action_run(
            "amazon.listings.publish",
            target_id="listing-1",
            input_json=(
                '{"title":"Travel Mug","sku":"AMZ-MUG-1",'
                '"marketplace_id":"ATVPDKIKX0DER",'
                '"product_type":"LUGGAGE"}'
            ),
        ),
        fallback_title="Amazon Listing",
    )

    assert preview is not None
    assert preview.title == "即将发布到 Amazon"
    assert {field.label: field.value for field in preview.fields} == {
        "商品": "Travel Mug",
        "SKU": "AMZ-MUG-1",
        "Marketplace": "ATVPDKIKX0DER",
        "Product Type": "LUGGAGE",
    }


def test_price_and_inventory_previews_show_requested_value():
    price = build_action_preview(
        action_run(
            "pricing.update",
            target_id="variant-1",
            input_json=(
                '{"sku":"SKU-1","price":"8.99",'
                '"cost_price":"9.00","below_cost":true}'
            ),
        ),
        fallback_title="调整价格",
    )
    inventory = build_action_preview(
        action_run(
            "inventory.update",
            target_id="variant-1",
            input_json='{"sku":"SKU-1","stock_quantity":12}',
        ),
        fallback_title="调整库存",
    )

    assert price is not None
    assert price.title == "即将修改销售价"
    assert {field.label: field.value for field in price.fields} == {
        "SKU": "SKU-1",
        "新价格": "8.99",
    }
    assert price.warning == "新价格低于当前成本价，请确认毛利风险。"
    assert inventory is not None
    assert inventory.title == "即将更新库存"
    assert {field.label: field.value for field in inventory.fields} == {
        "SKU": "SKU-1",
        "库存": "12 件",
    }


def test_listing_update_preview_shows_changed_fields():
    preview = build_action_preview(
        action_run(
            "listings.update",
            target_id="listing-1",
            input_json=(
                '{"title":"夏季收纳包","status":"draft",'
                '"description":"轻量防泼水"}'
            ),
        ),
        fallback_title="修改已上架商品",
    )

    assert preview is not None
    assert preview.title == "即将更新商品内容"
    assert {field.label: field.value for field in preview.fields} == {
        "标题": "夏季收纳包",
        "状态": "草稿",
        "描述": "轻量防泼水",
    }


def test_order_cancel_preview_shows_refund_and_restock_choices():
    preview = build_action_preview(
        action_run(
            "orders.cancel",
            target_id="9100",
            input_json=(
                '{"reason":"customer","restock":true,'
                '"refund":false,"notify_customer":true}'
            ),
        ),
        fallback_title="取消订单",
    )

    assert preview is not None
    assert preview.title == "即将取消订单"
    assert {field.label: field.value for field in preview.fields} == {
        "订单": "#9100",
        "原因": "customer",
        "回补库存": "是",
        "退款": "否",
        "通知买家": "是",
    }


def test_listing_media_preview_shows_asset_count():
    preview = build_action_preview(
        action_run(
            "listing.media.attach",
            target_id="listing-1",
            input_json='{"asset_ids":["a1","a2"]}',
        ),
        fallback_title="采用商品图片",
    )

    assert preview is not None
    assert preview.title == "即将附加商品图片"
    assert {field.label: field.value for field in preview.fields} == {
        "Listing": "listing-1",
        "图片": "2 张",
    }
