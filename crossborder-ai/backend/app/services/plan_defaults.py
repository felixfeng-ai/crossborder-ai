"""套餐与积分包的代码内兜底配置。

数据库还没有已发布版本时使用这些默认值，正式运营修改应进入版本表。
"""

PLAN_CATALOG: dict[str, dict] = {
    "free": {
        "name": "Free",
        "price": 0,
        "monthly_credits": 30,
        "valid_days": 0,
        "rank": 0,
    },
    "standard": {
        "name": "Standard",
        "price": 99,
        "first_month_price": 79,
        "annual_price": 990,
        "annual_full_price": 1188,
        "monthly_credits": 800,
        "valid_days": 30,
        "rank": 1,
    },
    "professional": {
        "name": "Professional",
        "price": 249,
        "first_month_price": 199,
        "annual_price": 2490,
        "annual_full_price": 2988,
        "first_month_bonus_credits": 100,
        "monthly_credits": 3000,
        "valid_days": 30,
        "rank": 2,
    },
}

CREDIT_PACKS = (
    {
        "id": "pack_trial_50",
        "name": "首购体验包",
        "credits": 50,
        "price": 9.9,
        "trial_once": True,
    },
    {
        "id": "pack_200",
        "name": "入门积分包",
        "credits": 200,
        "price": 19,
        "trial_once": False,
    },
    {
        "id": "pack_500",
        "name": "常用积分包",
        "credits": 500,
        "price": 45,
        "trial_once": False,
    },
    {
        "id": "pack_1200",
        "name": "专业积分包",
        "credits": 1200,
        "price": 99,
        "trial_once": False,
    },
)
