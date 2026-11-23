"""语音临时素材保留与文件删除测试。"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models.audio_asset import AudioAsset
from app.models.user import User
from app.services.data_retention import run_retention_cleanup
from app.services.workspaces import ensure_personal_workspace


@pytest.mark.asyncio
async def test_audio_retention_deletes_expired_file_and_row(
    db_session,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(settings, "AUDIO_STORAGE_DIR", str(tmp_path))
    user = User(
        email="audio-retention@example.com",
        username="audio-retention",
        password_hash="not-used",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    workspace = await ensure_personal_workspace(db_session, user)
    expired_file = tmp_path / "expired.m4a"
    active_file = tmp_path / "active.m4a"
    expired_file.write_bytes(b"expired")
    active_file.write_bytes(b"active")
    now = datetime.now(timezone.utc)
    db_session.add_all(
        [
            AudioAsset(
                user_id=user.id,
                workspace_id=workspace.id,
                original_name="expired.m4a",
                storage_key=expired_file.name,
                content_type="audio/mp4",
                duration_ms=1000,
                file_size=7,
                sha256="a" * 64,
                transcript="过期语音",
                detected_language="zh",
                provider="aliyun",
                model="qwen3-asr-flash",
                status="ready",
                idempotency_key="expired-audio",
                expires_at=now - timedelta(hours=1),
            ),
            AudioAsset(
                user_id=user.id,
                workspace_id=workspace.id,
                original_name="active.m4a",
                storage_key=active_file.name,
                content_type="audio/mp4",
                duration_ms=1000,
                file_size=6,
                sha256="b" * 64,
                transcript="仍在保留期内",
                detected_language="zh",
                provider="aliyun",
                model="qwen3-asr-flash",
                status="ready",
                idempotency_key="active-audio",
                expires_at=now + timedelta(hours=1),
            ),
        ]
    )
    await db_session.commit()

    result = await run_retention_cleanup(
        db_session,
        now=now,
        dry_run=False,
    )

    assert result["deleted"]["audio_assets"] == 1
    rows = (await db_session.execute(select(AudioAsset))).scalars().all()
    assert [row.idempotency_key for row in rows] == ["active-audio"]
    assert not expired_file.exists()
    assert active_file.exists()
