"""选品报告字段归一化和品类模式边界测试。"""


def test_normalizes_title_and_english_price_aliases():
    from app.services.selection_report import normalize_selection_report

    report = normalize_selection_report(
        {
            "market": {"monthly_search_volume": 50000},
            "products": [
                {
                    "title": "圣诞主题陶瓷马克杯礼盒",
                    "price_usd": "32.99",
                    "rating": 4.6,
                    "reviews": 2300,
                    "features": "含杯垫和勺子",
                }
            ],
            "recommendation": {"top_pick": "圣诞主题陶瓷马克杯礼盒"},
        },
        include_products=True,
    )

    product = report["products"][0]
    assert product["name"] == "圣诞主题陶瓷马克杯礼盒"
    assert product["suggested_price_usd"] == 32.99


def test_normalizes_chinese_product_aliases():
    from app.services.selection_report import normalize_selection_report

    report = normalize_selection_report(
        {
            "products": [
                {
                    "商品名": "30件防碎圣诞树球套装",
                    "价格美元": "24.99",
                    "采购价": "¥45",
                    "净利率": "38%",
                    "竞争度": "4",
                    "主要痛点": "挂钩偏软、金色款易掉粉",
                }
            ]
        },
        include_products=True,
    )

    product = report["products"][0]
    assert product["name"] == "30件防碎圣诞树球套装"
    assert product["suggested_price_usd"] == 24.99
    assert product["cost_cny"] == 45
    assert product["net_margin"] == 38
    assert product["competition"] == 4
    assert product["risk_tips"] == ["挂钩偏软", "金色款易掉粉"]


def test_category_report_forces_products_empty():
    from app.services.selection_report import normalize_selection_report

    report = normalize_selection_report(
        {
            "products": [
                {"title": "竞品 A", "price_usd": 19.99},
                {"title": "竞品 B", "price_usd": 29.99},
            ]
        },
        include_products=False,
    )

    assert report["products"] == []


def test_invalid_products_without_name_are_removed():
    from app.services.selection_report import normalize_selection_report

    report = normalize_selection_report(
        {
            "products": [
                {"price_usd": 19.99},
                {"title": "有效商品", "price_usd": 29.99},
            ]
        },
        include_products=True,
    )

    assert [item["name"] for item in report["products"]] == ["有效商品"]
