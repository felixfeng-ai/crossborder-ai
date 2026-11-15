"""VeyaShip - Replicate FLUX Image Generation Service.

Integrates with Replicate API to generate product images
using the black-forest-labs/flux-schnell model.
"""

import asyncio
import base64
from typing import Any, Dict, List, Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.core.config import settings
from app.services import provider_config

REPLICATE_BASE_URL = "https://api.replicate.com/v1"


class ReplicateService:
    """Service for AI image generation via Replicate's FLUX model."""

    def __init__(self):
        self.api_key = provider_config.get(
            "replicate",
            "api_key",
            settings.REPLICATE_API_KEY or "",
        )
        self.model = provider_config.get(
            "replicate",
            "model",
            settings.REPLICATE_MODEL,
        )

    def _build_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _build_product_prompt(
        self,
        product_title: str,
        custom_prompt: Optional[str] = None,
        style: str = "professional product photography",
    ) -> str:
        """Build an optimized image generation prompt for products."""
        if custom_prompt:
            return custom_prompt

        return (
            f"Professional e-commerce product photo of {product_title}. "
            f"{style}. Clean white background, studio lighting, "
            f"high resolution, 8K, product photography, photorealistic, "
            f"sharp focus, commercial photography."
        )

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=2, max=8),
        retry=retry_if_exception_type(
            (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout)
        ),
    )
    async def _run_prediction(
        self,
        model: str,
        input_data: Dict[str, Any],
    ) -> List[str]:
        """提交一次 Replicate prediction 并轮询到终态。"""
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{REPLICATE_BASE_URL}/models/{model}/predictions",
                headers=self._build_headers(),
                json={"input": input_data},
            )
            if response.status_code == 402:
                raise RuntimeError(
                    "Replicate 账户余额不足，请前往 "
                    "https://replicate.com/account/billing 充值"
                )
            if response.status_code == 429:
                raise RuntimeError("图片生成服务繁忙（API 限流），请稍后重试")
            if response.status_code == 401:
                raise RuntimeError("图片生成服务认证失败，请联系管理员检查 API Key 配置")
            response.raise_for_status()
            prediction = response.json()
            prediction_url = (
                f"{REPLICATE_BASE_URL}/predictions/{prediction['id']}"
            )

            for _ in range(80):
                if prediction["status"] in ("succeeded", "failed", "canceled"):
                    break
                await asyncio.sleep(1.5)
                response = await client.get(
                    prediction_url,
                    headers=self._build_headers(),
                )
                response.raise_for_status()
                prediction = response.json()

        if prediction["status"] == "failed":
            raise RuntimeError(
                f"Image generation failed: {prediction.get('error', 'Unknown error')}"
            )
        if prediction["status"] != "succeeded":
            raise RuntimeError("图片生成超时，请稍后重试")

        output = prediction.get("output") or []
        if isinstance(output, str):
            return [output]
        return [str(item) for item in output if str(item).strip()]

    # 仅重试网络连接错误（超时、断连），不重试 HTTP 业务错误（402余额不足、429限流）
    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=2, max=8),
        retry=retry_if_exception_type((httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout)),
    )
    async def generate_image(
        self,
        prompt: str,
        negative_prompt: Optional[str] = None,
        num_outputs: int = 1,
        aspect_ratio: str = "1:1",
    ) -> List[str]:
        """Generate product images using FLUX model.

        Args:
            prompt: Text description of the desired image.
            negative_prompt: Elements to avoid in the output.
            num_outputs: Number of images (1-4).
            aspect_ratio: Image aspect ratio (1:1, 16:9, 9:16, 4:3, 3:4).

        Returns:
            List of generated image URLs.
        """
        if not self.api_key:
            raise ValueError("Replicate API key not configured")

        input_data = {
            "prompt": prompt,
            "num_outputs": min(num_outputs, 4),
            "aspect_ratio": aspect_ratio,
            "output_format": "webp",
            "quality": 90,
        }

        if negative_prompt:
            input_data["negative_prompt"] = negative_prompt

        return await self._run_prediction(self.model, input_data)

    async def generate_reference_image(
        self,
        *,
        prompt: str,
        references: list[tuple[bytes, str]],
        negative_prompt: str = "",
        num_outputs: int = 1,
        aspect_ratio: str = "1:1",
        quality_tier: str = "standard",
        reference_model: str = "",
        reference_input_field: str = "image_input",
    ) -> List[str]:
        """提交带一张或多张商品参考图的生成任务。"""
        if not self.api_key:
            raise ValueError("Replicate API key not configured")
        if not reference_model:
            raise ValueError("Replicate 参考图模型未配置")
        if not references:
            raise ValueError("商品场景参考图不能为空")
        if len(references) > 4:
            raise ValueError("商品场景最多支持 4 张参考图")

        encoded = [
            f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"
            for data, mime in references
        ]
        final_prompt = prompt
        if negative_prompt.strip():
            final_prompt = (
                f"{prompt}\n必须避免以下问题：{negative_prompt.strip()}"
            )
        input_data: Dict[str, Any] = {
            "prompt": final_prompt,
            "aspect_ratio": aspect_ratio,
        }
        # 单图模型接收字符串，多参考图模型（如 Seedream）接收数组。
        if reference_input_field in {"input_image", "image"}:
            input_data[reference_input_field] = encoded[0]
        else:
            input_data[reference_input_field] = encoded

        if "seedream" in reference_model.lower():
            input_data["size"] = {
                "fast": "1K",
                "standard": "2K",
                "hd": "4K",
            }.get(quality_tier, "2K")
            if num_outputs > 1:
                input_data["sequential_image_generation"] = "auto"
                input_data["sequential_image_generation_options"] = {
                    "max_images": min(max(1, num_outputs), 4)
                }
        elif num_outputs > 1:
            input_data["num_outputs"] = min(max(1, num_outputs), 4)

        return await self._run_prediction(reference_model, input_data)

    async def generate_edit_image(
        self,
        *,
        model: str,
        mode: str,
        prompt: str,
        source: tuple[bytes, str],
        mask: tuple[bytes, str] | None = None,
        aspect_ratio: str = "1:1",
    ) -> List[str]:
        """按编辑操作组装 Replicate 输入；调用方必须已校验模型配置。"""
        if not self.api_key:
            raise ValueError("Replicate API key not configured")
        if not model:
            raise ValueError("Replicate 图片编辑模型未配置")
        source_data, source_mime = source
        source_uri = (
            f"data:{source_mime};base64,"
            f"{base64.b64encode(source_data).decode('ascii')}"
        )
        input_data: Dict[str, Any] = {
            "image": source_uri,
            "prompt": prompt,
            "output_format": "webp",
        }
        if mode in {"inpaint", "remove_object"}:
            if mask is None:
                raise ValueError("局部编辑必须提供蒙版图")
            mask_data, mask_mime = mask
            input_data["mask"] = (
                f"data:{mask_mime};base64,"
                f"{base64.b64encode(mask_data).decode('ascii')}"
            )
        if mode == "outpaint":
            input_data["aspect_ratio"] = aspect_ratio
        return await self._run_prediction(model, input_data)

    async def generate_product_image(
        self,
        product_title: str,
        product_description: Optional[str] = None,
        custom_prompt: Optional[str] = None,
        style: str = "professional product photography",
        aspect_ratio: str = "1:1",
    ) -> List[str]:
        """Generate a product image from product information.

        Args:
            product_title: The product name.
            product_description: Optional product description for context.
            custom_prompt: Override the auto-generated prompt.
            style: Photography style description.
            aspect_ratio: Image aspect ratio.

        Returns:
            List of generated image URLs.
        """
        prompt = self._build_product_prompt(product_title, custom_prompt, style)
        if product_description:
            prompt += f" Product features: {product_description[:200]}"

        return await self.generate_image(
            prompt=prompt,
            num_outputs=1,
            aspect_ratio=aspect_ratio,
        )
