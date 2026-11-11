"""数据保留、加密密钥和基础设施安全契约测试。"""

import json
import ssl
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import select

from app.core import crypto
from app.core.database import _database_connect_args
from app.models.agent_task import AgentTask
from app.models.content import ContentGeneration, ContentStatus, ContentType
from app.models.data_retention import DataRetentionRun
from app.models.image_generation_task import ImageGenerationTask
from app.models.store_check_log import StoreCheckLog
from app.models.user import User
from app.services.data_retention import run_retention_cleanup


BACKEND_DIR = Path(__file__).resolve().parents[1]


async def _create_user(db_session) -> User:
    user = User(
        id=uuid.uuid4(),
        email=f"retention-{uuid.uuid4().hex[:8]}@example.com",
        username="retention-user",
        password_hash="not-used-in-this-test",
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.mark.asyncio
async def test_retention_cleanup_deletes_only_old_terminal_records(db_session):
    """超过保留期的终态任务删除；新记录和运行中记录必须保留。"""
    user = await _create_user(db_session)
    now = datetime.now(timezone.utc)
    old = now - timedelta(days=120)
    recent = now - timedelta(days=10)

    old_image = ImageGenerationTask(
        user_id=user.id,
        prompt="old image",
        status="completed",
        image_urls="[]",
        created_at=old,
    )
    recent_image = ImageGenerationTask(
        user_id=user.id,
        prompt="recent image",
        status="completed",
        image_urls="[]",
        created_at=recent,
    )
    running_image = ImageGenerationTask(
        user_id=user.id,
        prompt="running image",
        status="processing",
        image_urls=None,
        created_at=old,
    )
    old_agent = AgentTask(
        user_id=user.id,
        task_type="agent_run",
        status="succeeded",
        input="{}",
        result="{}",
        created_at=old,
    )
    running_agent = AgentTask(
        user_id=user.id,
        task_type="agent_run",
        status="running",
        input="{}",
        created_at=old,
    )
    old_content = ContentGeneration(
        user_id=user.id,
        content_type=ContentType.PRODUCT_TITLE,
        status=ContentStatus.COMPLETED,
        model_used="deepseek",
        source_text="source",
        generated_text="old generated",
        created_at=old,
    )
    old_store_check = StoreCheckLog(
        user_id=user.id,
        total=1,
        healthy=1,
        issue_count=0,
        issues_json="[]",
        created_at=now - timedelta(days=220),
    )
    db_session.add_all(
        [
            old_image,
            recent_image,
            running_image,
            old_agent,
            running_agent,
            old_content,
            old_store_check,
        ]
    )
    await db_session.flush()

    result = await run_retention_cleanup(
        db_session,
        now=now,
        retention_days=90,
        store_check_retention_days=180,
        dry_run=False,
    )

    remaining_image_ids = set(
        (
            await db_session.execute(select(ImageGenerationTask.id))
        ).scalars().all()
    )
    remaining_agent_ids = set(
        (await db_session.execute(select(AgentTask.id))).scalars().all()
    )
    remaining_content_ids = set(
        (await db_session.execute(select(ContentGeneration.id))).scalars().all()
    )
    remaining_store_check_ids = set(
        (await db_session.execute(select(StoreCheckLog.id))).scalars().all()
    )

    assert old_image.id not in remaining_image_ids
    assert old_agent.id not in remaining_agent_ids
    assert old_content.id not in remaining_content_ids
    assert old_store_check.id not in remaining_store_check_ids
    assert recent_image.id in remaining_image_ids
    assert running_image.id in remaining_image_ids
    assert running_agent.id in remaining_agent_ids
    assert result["deleted"]["image_generation_tasks"] == 1
    assert result["deleted"]["agent_tasks"] == 1
    assert result["deleted"]["content_generations"] == 1
    assert result["deleted"]["store_check_logs"] == 1

    audit = (
        await db_session.execute(select(DataRetentionRun))
    ).scalar_one()
    assert audit.status == "completed"
    assert audit.dry_run is False
    assert json.loads(audit.deleted_counts)["image_generation_tasks"] == 1


@pytest.mark.asyncio
async def test_retention_dry_run_counts_without_deleting(db_session):
    """dry-run 只统计候选记录，不删除，并保留演练审计。"""
    user = await _create_user(db_session)
    now = datetime.now(timezone.utc)
    task = ImageGenerationTask(
        user_id=user.id,
        prompt="expired but kept in dry-run",
        status="failed",
        image_urls=None,
        created_at=now - timedelta(days=100),
    )
    db_session.add(task)
    await db_session.flush()

    result = await run_retention_cleanup(
        db_session,
        now=now,
        retention_days=90,
        store_check_retention_days=180,
        dry_run=True,
    )

    assert result["dry_run"] is True
    assert result["deleted"]["image_generation_tasks"] == 1
    assert (
        await db_session.execute(
            select(ImageGenerationTask).where(ImageGenerationTask.id == task.id)
        )
    ).scalar_one_or_none() is not None

    audit = (
        await db_session.execute(select(DataRetentionRun))
    ).scalar_one()
    assert audit.status == "completed"
    assert audit.dry_run is True


def test_data_encryption_key_rotation_keeps_old_ciphertext_readable(monkeypatch):
    """新密钥负责加密，旧密钥仍可解密历史密文。"""
    monkeypatch.setattr(crypto.settings, "JWT_SECRET_KEY", "jwt-secret")
    monkeypatch.setattr(crypto.settings, "SECRET_KEY", "app-secret")
    monkeypatch.setattr(crypto.settings, "DATA_ENCRYPTION_KEY", "data-key-v1")
    monkeypatch.setattr(crypto.settings, "DATA_ENCRYPTION_PREVIOUS_KEYS", "")

    ciphertext = crypto.encrypt_value("shop-token")
    assert ciphertext != "shop-token"
    assert crypto.decrypt_value(ciphertext) == "shop-token"

    monkeypatch.setattr(crypto.settings, "DATA_ENCRYPTION_KEY", "data-key-v2")
    monkeypatch.setattr(
        crypto.settings,
        "DATA_ENCRYPTION_PREVIOUS_KEYS",
        "data-key-v1",
    )

    assert crypto.decrypt_value(ciphertext) == "shop-token"
    new_ciphertext = crypto.encrypt_value("new-shop-token")
    assert crypto.decrypt_value(new_ciphertext) == "new-shop-token"


def test_verify_full_database_connection_uses_ssl_context():
    """verify-full 必须创建启用证书校验的 SSLContext。"""
    connect_args = _database_connect_args(
        use_sqlite=False,
        ssl_mode="verify-full",
        ssl_ca_path="",
        ssl_cert_path="",
        ssl_key_path="",
    )
    context = connect_args["ssl"]
    assert isinstance(context, ssl.SSLContext)
    assert context.check_hostname is True
    assert context.verify_mode == ssl.CERT_REQUIRED


def test_security_scripts_include_encryption_and_verification():
    """部署脚本必须包含加密备份和可执行安全核验入口。"""
    backup = (BACKEND_DIR.parent / "deploy" / "backup.sh").read_text(encoding="utf-8")
    deploy = (
        BACKEND_DIR.parent / "deploy" / "veyaship" / "cicd-deploy.sh"
    ).read_text(encoding="utf-8")
    verifier = (
        BACKEND_DIR.parent / "deploy" / "security-check.sh"
    ).read_text(encoding="utf-8")

    assert "openssl enc -aes-256-cbc" in backup
    assert "BACKUP_ENCRYPTION_KEY_FILE" in backup
    assert "DATA_ENCRYPTION_KEY" in deploy
    assert "BACKUP_ENCRYPTION_KEY_FILE" in deploy
    assert "DB_SSL_MODE" in verifier
    assert "DATA_ENCRYPTION_KEY" in verifier
    assert "AT_REST_ENCRYPTION_EVIDENCE" in verifier
