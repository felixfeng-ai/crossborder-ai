"""视频素材封面提取与缓存。"""

from pathlib import Path
from types import SimpleNamespace

from app.services.video_thumbnail import ensure_video_thumbnail


def test_ensure_video_thumbnail_extracts_and_reuses_cache(
    tmp_path,
    monkeypatch,
):
    video = tmp_path / "marketing-demo.mp4"
    video.write_bytes(b"\x00\x00\x00\x18ftypmp42video")
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        Path(command[-1]).write_bytes(b"jpeg-cover")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(
        "app.services.video_thumbnail.subprocess.run",
        fake_run,
    )

    first = ensure_video_thumbnail(video)
    second = ensure_video_thumbnail(video)

    assert first.is_file()
    assert first == second
    assert first.name.endswith(".cover.jpg")
    assert len(calls) == 1
    assert "-ss" in calls[0]
    assert "scale=480:-2" in calls[0]


def test_ensure_video_thumbnail_rejects_missing_video(tmp_path):
    try:
        ensure_video_thumbnail(tmp_path / "missing.mp4")
    except FileNotFoundError as exc:
        assert "视频文件不存在" in str(exc)
    else:
        raise AssertionError("missing video should fail")
