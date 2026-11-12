# 账单积分解释与套餐申请交互

## Requirements

- 账单页总额必须来自 `/billing/wallet` 的 `total_credits`。
- 页面必须直接显示 `total_credits = plan_credits + purchased_credits`。
- 积分显示使用千位分隔符。
- 点击付费套餐后，升级申请表单移动到套餐卡片正下方并自动滚入视野。
- 升级仍为人工审核流程，不宣称立即切换套餐。
