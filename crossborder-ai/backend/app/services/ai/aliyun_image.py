"""VeyaShip - 阿里云通义万相 AI 图片生成

阿里云 DashScope API：先提交任务，再轮询结果。
文档：https://help.aliyun.com/zh/dashscope/developer-reference/quick-start
"""

import asyncio
from typing import List, Optional

import httpx
from app.core.config import settings
from app.services import provider_config

DASHSCOPE_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis"
TASK_URL = "https://dashscope.aliyuncs.com/api/v1/tasks/"


class AliyunImageService:
    """阿里云通义万相图片生成服务"""

    def __init__(self):
        self.api_key = provider_config.get(
            "aliyun",
            "api_key",
            settings.ALIYUN_DASHSCOPE_API_KEY or "",
        )
        self.model = provider_config.get(
            "aliyun",
            "model",
            settings.ALIYUN_IMAGE_MODEL,
        )

    def _headers(self, async_mode: bool = False):
        h = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if async_mode:
            h["X-DashScope-Async"] = "enable"
        return h

    async def generate_image(
        self,
        prompt: str,
        num_outputs: int = 1,
        size: str = "1024*1024",
    ) -> List[str]:
        """生成商品图片（异步提交 + 轮询结果）"""
        if not self.api_key:
            raise RuntimeError("阿里云通义万相 API Key 未配置")

        body = {
            "model": self.model,
            "input": {"prompt": prompt},
            "parameters": {"size": size, "n": min(num_outputs, 4)},
        }

        async with httpx.AsyncClient(timeout=120) as client:
            # 1. 提交任务（异步模式）
            resp = await client.post(DASHSCOPE_URL, headers=self._headers(async_mode=True), json=body)
            if resp.status_code == 401:
                raise RuntimeError("阿里云通义万相认证失败，请检查 API Key")
            if resp.status_code != 200:
                raise RuntimeError(f"提交失败：{resp.text[:200]}")

            result = resp.json()
            task_id = result.get("output", {}).get("task_id")
            if not task_id:
                raise RuntimeError(f"提交响应异常：{resp.text[:200]}")

            # 2. 轮询结果（0.5s 间隔，最快响应）
            for _ in range(120):
                await asyncio.sleep(0.5)
                status_resp = await client.get(
                    f"{TASK_URL}{task_id}", headers=self._headers()
                )
                if status_resp.status_code != 200:
                    continue

                status_data = status_resp.json()
                status = status_data.get("output", {}).get("task_status", "")

                if status == "SUCCEEDED":
                    results = status_data.get("output", {}).get("results", [])
                    return [r.get("url", "") for r in results if r.get("url")]

                if status in ("FAILED", "CANCELED"):
                    err = status_data.get("output", {}).get("message", "未知错误")
                    raise RuntimeError(f"生成失败：{err}")

            raise RuntimeError("生成超时，请稍后重试")
