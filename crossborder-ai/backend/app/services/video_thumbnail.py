"""视频成片封面帧提取与本地缓存。"""

import shutil
import subprocess
from pathlib import Path


def _ffmpeg_executable() -> str:
    """优先使用系统 FFmpeg，缺失时使用 Python 包内置二进制。"""
    executable = shutil.which("ffmpeg")
    if executable:
        return executable
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def ensure_video_thumbnail(video_path: Path) -> Path:
    """从视频约 1 秒处提取封面；已有缓存时直接复用。"""
    if not video_path.is_file():
        raise FileNotFoundError("视频文件不存在")

    cover_path = video_path.with_suffix(".cover.jpg")
    if cover_path.is_file() and cover_path.stat().st_size > 0:
        return cover_path

    temporary = video_path.with_suffix(".cover.tmp.jpg")
    temporary.unlink(missing_ok=True)
    command = [
        _ffmpeg_executable(),
        "-y",
        "-ss",
        "1",
        "-i",
        str(video_path),
        "-frames:v",
        "1",
        "-vf",
        "scale=480:-2",
        "-q:v",
        "3",
        str(temporary),
    ]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if result.returncode != 0 or not temporary.is_file():
        temporary.unlink(missing_ok=True)
        raise RuntimeError("视频封面生成失败")
    temporary.replace(cover_path)
    return cover_path
