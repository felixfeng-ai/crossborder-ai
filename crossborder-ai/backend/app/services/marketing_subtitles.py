"""营销视频字幕时间轴与 SRT 生成。"""

import re
from typing import Any


_SENTENCE_SPLIT = re.compile(r"(?<=[。！？.!?])\s+")
_MAX_CUE_CHARS = 56


def format_srt_timestamp(milliseconds: int) -> str:
    """把毫秒转换为 SRT 使用的 HH:MM:SS,mmm。"""
    value = max(0, int(milliseconds))
    hours, remainder = divmod(value, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _split_text(value: str, max_chars: int = _MAX_CUE_CHARS) -> list[str]:
    """按句末和长度拆分字幕，避免单行覆盖过大。"""
    clean = _clean_text(value)
    if not clean:
        return []

    sentences = [item.strip() for item in _SENTENCE_SPLIT.split(clean) if item.strip()]
    if len(sentences) == 1:
        # 中文评论和中英混排不一定有空格，按标点保留句尾再切分。
        sentences = [
            item.strip()
            for item in re.findall(r"[^。！？.!?]+[。！？.!?]?", clean)
            if item.strip()
        ]

    chunks: list[str] = []
    current = ""
    for sentence in sentences or [clean]:
        candidate = f"{current} {sentence}".strip()
        if current and len(candidate) > max_chars:
            chunks.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        chunks.append(current)

    result: list[str] = []
    for chunk in chunks:
        while len(chunk) > max_chars:
            split_at = max(
                chunk.rfind(" ", 0, max_chars),
                chunk.rfind("，", 0, max_chars),
                chunk.rfind(",", 0, max_chars),
            )
            if split_at < max_chars // 2:
                split_at = max_chars
            result.append(chunk[:split_at].strip())
            chunk = chunk[split_at:].strip()
        if chunk:
            result.append(chunk)
    return result


def _distribute_text(value: str, slots: int) -> list[str]:
    """把正文尽量均匀分配到中间分镜。"""
    if slots <= 0:
        return []
    parts = _split_text(value)
    if not parts:
        return [""] * slots
    if len(parts) >= slots:
        buckets = [""] * slots
        for index, part in enumerate(parts):
            bucket = min(slots - 1, index * slots // len(parts))
            buckets[bucket] = f"{buckets[bucket]} {part}".strip()
        return buckets
    return [
        parts[min(index, len(parts) - 1)]
        for index in range(slots)
    ]


def build_marketing_subtitle_cues(
    brief: dict[str, Any],
    shots: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """按分镜时长生成连续字幕，首镜头承载 hook，末镜头承载 CTA。"""
    if not shots:
        return []

    texts: list[str] = []
    if len(shots) == 1:
        texts = [
            " ".join(
                filter(
                    None,
                    (
                        _clean_text(brief.get("hook")),
                        _clean_text(brief.get("script")),
                        _clean_text(brief.get("cta")),
                    ),
                )
            )
        ]
    else:
        middle_slots = max(0, len(shots) - 2)
        middle = _distribute_text(_clean_text(brief.get("script")), middle_slots)
        texts = [_clean_text(brief.get("hook") or shots[0].get("title"))]
        for index, item in enumerate(middle):
            fallback = _clean_text(shots[index + 1].get("title"))
            texts.append(item or fallback)
        texts.append(_clean_text(brief.get("cta") or shots[-1].get("title")))

    cues: list[dict[str, Any]] = []
    cursor_ms = 0
    for index, shot in enumerate(shots):
        duration_ms = max(1, int(shot.get("duration") or 1)) * 1_000
        pieces = _split_text(texts[index]) or [
            _clean_text(shot.get("title")) or f"Scene {index + 1}"
        ]
        piece_duration = max(1, duration_ms // len(pieces))
        for piece_index, piece in enumerate(pieces):
            start_ms = cursor_ms + piece_index * piece_duration
            end_ms = (
                cursor_ms + duration_ms
                if piece_index == len(pieces) - 1
                else start_ms + piece_duration
            )
            cues.append(
                {
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "text": piece,
                }
            )
        cursor_ms += duration_ms
    return cues


def build_marketing_srt(
    brief: dict[str, Any],
    shots: list[dict[str, Any]],
) -> str:
    """输出标准 SRT 文本。"""
    blocks = []
    for index, cue in enumerate(build_marketing_subtitle_cues(brief, shots), 1):
        blocks.append(
            "\n".join(
                [
                    str(index),
                    f"{format_srt_timestamp(cue['start_ms'])} --> "
                    f"{format_srt_timestamp(cue['end_ms'])}",
                    cue["text"],
                ]
            )
        )
    return "\n\n".join(blocks) + ("\n" if blocks else "")
