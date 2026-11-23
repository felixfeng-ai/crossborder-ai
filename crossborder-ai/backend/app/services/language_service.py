"""轻量语言识别与回复翻译接口。"""

import re
from typing import Protocol

from app.services.ai.deepseek import DeepSeekService


def detect_language(text: str) -> str:
    """用字符脚本和常见词识别首发客服语言，无法判断时回退英文。"""

    value = (text or "").strip()
    if not value:
        return "en"
    if re.search(r"[\u3040-\u30ff]", value):
        return "ja"
    if re.search(r"[\uac00-\ud7af]", value):
        return "ko"
    if re.search(r"[\u4e00-\u9fff]", value):
        return "zh"
    if re.search(r"[\u0400-\u04ff]", value):
        return "ru"
    if re.search(r"[\u0600-\u06ff]", value):
        return "ar"
    lowered = value.lower()
    hints = {
        "es": {"hola", "gracias", "pedido", "dónde", "donde", "envío", "envio"},
        "fr": {"bonjour", "merci", "commande", "colis", "livraison"},
        "de": {"hallo", "danke", "bestellung", "paket", "lieferung"},
        "pt": {"olá", "obrigado", "pedido", "entrega", "rastreio"},
        "it": {"ciao", "grazie", "ordine", "pacco", "consegna"},
    }
    tokens = set(re.findall(r"[a-zà-ÿ]+", lowered))
    for language, words in hints.items():
        if len(tokens & words) >= 2:
            return language
    return "en"


class ReplyTranslator(Protocol):
    async def translate(
        self,
        *,
        text: str,
        source_language: str,
        target_language: str,
        customer_message: str,
    ) -> str:
        """把卖家的中文指令改写成目标语言的客户回复。"""


class DeepSeekReplyTranslator:
    """默认翻译器：只翻译表达，不允许改写订单事实。"""

    async def translate(
        self,
        *,
        text: str,
        source_language: str,
        target_language: str,
        customer_message: str,
    ) -> str:
        service = DeepSeekService()
        return await service.generate(
            system_prompt=(
                "你是跨境客服回复翻译器。将卖家指令转化为客户可发送的回复，"
                "只改变语言和语气，不编造物流、退款、价格或送达承诺。"
                "保留订单号、SKU、物流单号、金额、日期和品牌名原样。"
                "只输出最终回复正文，不要解释。"
            ),
            user_prompt=(
                f"源语言：{source_language}\n"
                f"目标语言：{target_language}\n"
                f"客户原话：{customer_message}\n"
                f"卖家指令：{text}"
            ),
            temperature=0.2,
        )
