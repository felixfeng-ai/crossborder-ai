"""Creem webhook signature verification gates."""

import hashlib
import hmac

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.v1.endpoints import payments as payments_endpoint
from app.core.database import get_db
from app.services.payment import PaymentService


def _sign(payload: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def _webhook_app() -> FastAPI:
    app = FastAPI()
    app.include_router(payments_endpoint.router, prefix="/api/v1")

    async def override_get_db():
        yield None

    app.dependency_overrides[get_db] = override_get_db
    return app


@pytest.mark.asyncio
async def test_verify_webhook_accepts_valid_signature(monkeypatch):
    secret = "whsec_ci_test_secret"
    payload = b'{"eventType":"checkout.completed","id":"evt_1"}'
    monkeypatch.setattr(
        "app.services.payment.settings.CREEM_WEBHOOK_SECRET",
        secret,
    )

    service = PaymentService()
    assert await service.verify_webhook(payload, _sign(payload, secret)) is True


@pytest.mark.asyncio
async def test_verify_webhook_rejects_tampered_payload(monkeypatch):
    secret = "whsec_ci_test_secret"
    original = b'{"eventType":"checkout.completed","id":"evt_1"}'
    tampered = b'{"eventType":"checkout.completed","id":"evt_2"}'
    monkeypatch.setattr(
        "app.services.payment.settings.CREEM_WEBHOOK_SECRET",
        secret,
    )

    service = PaymentService()
    assert await service.verify_webhook(
        tampered,
        _sign(original, secret),
    ) is False


@pytest.mark.asyncio
async def test_verify_webhook_fails_closed_without_secret(monkeypatch):
    monkeypatch.setattr(
        "app.services.payment.settings.CREEM_WEBHOOK_SECRET",
        None,
    )
    service = PaymentService()
    assert await service.verify_webhook(b"{}", "0" * 64) is False


@pytest.mark.asyncio
async def test_verify_webhook_rejects_invalid_hex(monkeypatch):
    monkeypatch.setattr(
        "app.services.payment.settings.CREEM_WEBHOOK_SECRET",
        "whsec",
    )
    service = PaymentService()
    assert await service.verify_webhook(b"{}", "not-a-hex-signature") is False


@pytest.mark.asyncio
async def test_webhook_endpoint_accepts_valid_signature(monkeypatch):
    secret = "whsec_endpoint_secret"
    payload = b'{"id":"evt_1","eventType":"checkout.completed","object":{}}'
    monkeypatch.setattr(
        "app.services.payment.settings.CREEM_WEBHOOK_SECRET",
        secret,
    )

    async with AsyncClient(
        transport=ASGITransport(app=_webhook_app()),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/payments/webhook",
            content=payload,
            headers={
                "content-type": "application/json",
                "creem-signature": _sign(payload, secret),
            },
        )
    assert response.status_code == 200, response.text


@pytest.mark.asyncio
async def test_webhook_endpoint_rejects_invalid_signature(monkeypatch):
    monkeypatch.setattr(
        "app.services.payment.settings.CREEM_WEBHOOK_SECRET",
        "whsec_endpoint_secret",
    )

    async with AsyncClient(
        transport=ASGITransport(app=_webhook_app()),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/payments/webhook",
            content=b'{"eventType":"checkout.completed"}',
            headers={
                "content-type": "application/json",
                "creem-signature": "0" * 64,
            },
        )
    assert response.status_code == 401, response.text
