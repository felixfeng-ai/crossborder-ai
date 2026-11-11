"""营销视频字幕生成与烧录契约测试。"""

from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.models.marketing_video import MarketingVideoProject, MarketingVideoShot
from app.models.user import User
from app.services.marketing_subtitles import (
    build_marketing_subtitle_cues,
    build_marketing_srt,
)
from app.services.marketing_video_executor import assemble_marketing_video


BRIEF = {
    "hook": "Meet your next travel essential.",
    "script": "Lightweight design. All-day comfort. Packs in seconds.",
    "cta": "Shop now.",
}
SHOTS = [
    {"position": 1, "title": "Hook", "duration": 5},
    {"position": 2, "title": "Demo", "duration": 7},
    {"position": 3, "title": "CTA", "duration": 3},
]


def test_subtitle_cues_follow_shot_timeline_and_include_cta():
    cues = build_marketing_subtitle_cues(BRIEF, SHOTS)

    assert cues
    assert cues[0]["start_ms"] == 0
    assert cues[-1]["end_ms"] == 15_000
    assert "Meet your next travel essential" in " ".join(
        cue["text"] for cue in cues
    )
    assert "Shop now" in " ".join(cue["text"] for cue in cues)
    assert all(cue["end_ms"] > cue["start_ms"] for cue in cues)


def test_build_srt_uses_standard_timestamp_and_blank_lines():
    srt = build_marketing_srt(BRIEF, SHOTS)

    assert srt.startswith("1\n00:00:00,000 --> ")
    assert "00:00:15,000" in srt
    assert "Shop now." in srt
    assert "\n\n" in srt


def test_assemble_marketing_video_burns_srt_when_supported(tmp_path, monkeypatch):
    segment = tmp_path / "shot.mp4"
    subtitle = tmp_path / "marketing.srt"
    output = tmp_path / "final.mp4"
    segment.write_bytes(b"\x00\x00\x00\x18ftypmp42shot")
    subtitle.write_text("1\n00:00:00,000 --> 00:00:05,000\nHello\n", encoding="utf-8")
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        if len(calls) == 1:
            Path(command[-1]).write_bytes(b"\x00\x00\x00\x18ftypmp42joined")
        else:
            Path(command[-1]).write_bytes(b"\x00\x00\x00\x18ftypmp42subtitled")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(
        "app.services.marketing_video_executor.subprocess.run",
        fake_run,
    )

    burned = assemble_marketing_video([segment], output, subtitle_path=subtitle)

    assert burned is True
    assert output.is_file()
    assert len(calls) == 2
    assert any("subtitles=" in str(part) for part in calls[1])


def test_assemble_marketing_video_keeps_raw_when_subtitle_filter_fails(
    tmp_path,
    monkeypatch,
):
    segment = tmp_path / "shot.mp4"
    subtitle = tmp_path / "marketing.srt"
    output = tmp_path / "final.mp4"
    segment.write_bytes(b"\x00\x00\x00\x18ftypmp42shot")
    subtitle.write_text("1\n00:00:00,000 --> 00:00:05,000\nHello\n", encoding="utf-8")
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        if len(calls) == 1:
            Path(command[-1]).write_bytes(b"\x00\x00\x00\x18ftypmp42joined")
            return SimpleNamespace(returncode=0)
        return SimpleNamespace(returncode=1)

    monkeypatch.setattr(
        "app.services.marketing_video_executor.subprocess.run",
        fake_run,
    )

    burned = assemble_marketing_video([segment], output, subtitle_path=subtitle)

    assert burned is False
    assert output.read_bytes().endswith(b"joined")


@pytest.mark.parametrize(
    ("milliseconds", "expected"),
    [
        (0, "00:00:00,000"),
        (3_723_456, "01:02:03,456"),
    ],
)
def test_srt_timestamp_supports_hours(milliseconds, expected):
    from app.services.marketing_subtitles import format_srt_timestamp

    assert format_srt_timestamp(milliseconds) == expected


@pytest.mark.asyncio
async def test_subtitle_endpoint_returns_owned_project_srt(
    client,
    db_session,
    auth_headers,
):
    user = (
        await db_session.execute(select(User).where(User.email == "test@example.com"))
    ).scalar_one()
    project = MarketingVideoProject(
        user_id=user.id,
        source_asset_id=None,
        title="Terra campaign",
        product_name="Terra",
        idea="show the product",
        platform="tiktok",
        market="US",
        language="en",
        duration=15,
        template_id="presenter_demo",
        model="MiniMax-H3-Lite",
        resolution="480P",
        status="succeeded",
        brief_json='{"hook":"Meet Terra", "script":"One light layer.", "cta":"Shop now"}',
    )
    db_session.add(project)
    await db_session.flush()
    for position, duration in enumerate((5, 7, 3), 1):
        db_session.add(
            MarketingVideoShot(
                project_id=project.id,
                position=position,
                title=f"Shot {position}",
                purpose="demo",
                prompt="demo",
                duration=duration,
                status="succeeded",
            )
        )
    await db_session.flush()

    response = await client.get(
        f"/api/v1/marketing-videos/projects/{project.id}/subtitles",
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-subrip")
    assert "Meet Terra" in response.text
    assert "Shop now" in response.text
