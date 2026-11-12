"""专业脚本文案解析与逐镜头执行约束。

该模式不调用 LLM。用户写什么就保存什么，只补充生成供应商需要的
连续性锁、禁止编造和画幅提示。
"""

from dataclasses import asdict, dataclass, field
import re
from typing import Any

from app.services.minimax_video import PRODUCT_LOCK_PROMPT, estimate_video_credits


MAX_STORYBOARD_SHOTS = 12
MAX_SCRIPT_CHARS = 30_000
MAX_SHOT_SECONDS = 15

_HEADER_PATTERN = re.compile(
    r"^\s*分镜\s*(\d+)\s*[|｜]\s*"
    r"(\d{1,2}:\d{2})\s*[-–—~～至]\s*(\d{1,2}:\d{2})\s*[|｜]\s*"
    r"(.+?)\s*(?:[（(]\s*时长\s*(\d+)\s*秒\s*[)）])?\s*$",
    re.IGNORECASE,
)
_CONSTRAINT_HEADER = re.compile(
    r"^\s*(?:[一二三四五六七八九十]+[、.．]\s*)?生成约束\s*$",
    re.IGNORECASE,
)


@dataclass
class StoryboardShot:
    position: int
    title: str
    source_text: str
    start_seconds: int
    end_seconds: int
    duration: int
    purpose: str = "script"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProfessionalStoryboard:
    title: str
    shots: list[StoryboardShot]
    global_constraints: str = ""
    no_dialogue: bool = False
    no_subtitles: bool = False
    no_watermark: bool = False
    preamble: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def shot_count(self) -> int:
        return len(self.shots)

    @property
    def total_duration(self) -> int:
        return sum(shot.duration for shot in self.shots)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "shot_count": self.shot_count,
            "total_duration": self.total_duration,
            "shots": [shot.to_dict() for shot in self.shots],
            "global_constraints": self.global_constraints,
            "no_dialogue": self.no_dialogue,
            "no_subtitles": self.no_subtitles,
            "no_watermark": self.no_watermark,
            "preamble": self.preamble,
            "metadata": self.metadata,
        }


def parse_timecode(value: str) -> int:
    """解析 MM:SS 或 HH:MM:SS 为秒。"""
    parts = [int(item) for item in value.strip().split(":")]
    if len(parts) == 2:
        minutes, seconds = parts
        if seconds >= 60:
            raise ValueError("分镜时间码的秒数必须小于 60")
        return minutes * 60 + seconds
    if len(parts) == 3:
        hours, minutes, seconds = parts
        if minutes >= 60 or seconds >= 60:
            raise ValueError("分镜时间码格式无效")
        return hours * 3_600 + minutes * 60 + seconds
    raise ValueError("分镜时间码必须使用 MM:SS 或 HH:MM:SS")


def _default_title(preamble_lines: list[str]) -> str:
    for line in preamble_lines:
        clean = line.strip()
        if not clean:
            continue
        match = re.match(r"^(?:标题|项目名称)\s*[:：]\s*(.+)$", clean)
        if match:
            return match.group(1).strip()[:255]
        if clean.endswith("脚本") and len(clean) <= 80:
            return clean.removesuffix("脚本").strip() or "专业脚本分镜"
    return "专业脚本分镜"


def parse_professional_storyboard(script: str) -> ProfessionalStoryboard:
    """原样解析分镜标题、时间码、动作描述和全局约束。"""
    text = (script or "").strip()
    if not text:
        raise ValueError("脚本不能为空")
    if len(text) > MAX_SCRIPT_CHARS:
        raise ValueError(f"脚本不能超过 {MAX_SCRIPT_CHARS} 字")

    lines = text.splitlines()
    headers: list[tuple[int, re.Match[str]]] = []
    constraint_index: int | None = None
    for index, line in enumerate(lines):
        match = _HEADER_PATTERN.match(line)
        if match:
            headers.append((index, match))
        elif _CONSTRAINT_HEADER.match(line):
            constraint_index = index
            break

    if not headers:
        raise ValueError("没有识别到分镜，请使用“分镜 1｜00:00–00:04｜标题（时长 4 秒）”格式")
    if len(headers) > MAX_STORYBOARD_SHOTS:
        raise ValueError(f"专业分镜最多支持 {MAX_STORYBOARD_SHOTS} 个镜头")

    shots: list[StoryboardShot] = []
    expected_start = 0
    for header_index, (line_index, match) in enumerate(headers):
        position = int(match.group(1))
        if position != header_index + 1:
            raise ValueError("分镜编号必须从 1 开始连续递增")

        start_seconds = parse_timecode(match.group(2))
        end_seconds = parse_timecode(match.group(3))
        title = match.group(4).strip()
        explicit_duration = int(match.group(5)) if match.group(5) else None
        duration = end_seconds - start_seconds
        if duration <= 0:
            raise ValueError(f"分镜 {position} 的结束时间必须晚于开始时间")
        if explicit_duration is not None and explicit_duration != duration:
            raise ValueError(
                f"分镜 {position} 的时间码与显式时长不一致"
            )
        if start_seconds != expected_start:
            raise ValueError(
                f"分镜 {position} 的时间码不连续，应从 {expected_start // 60:02d}:"
                f"{expected_start % 60:02d} 开始"
            )
        if duration > MAX_SHOT_SECONDS:
            raise ValueError(
                f"分镜 {position} 超过模型单镜头最长 {MAX_SHOT_SECONDS} 秒"
            )

        next_header_index = (
            headers[header_index + 1][0]
            if header_index + 1 < len(headers)
            else (constraint_index if constraint_index is not None else len(lines))
        )
        body_lines = [
            line.strip()
            for line in lines[line_index + 1: next_header_index]
            if line.strip()
        ]
        source_text = "\n".join(body_lines).strip()
        if not source_text:
            raise ValueError(f"分镜 {position} 缺少画面描述")

        shots.append(
            StoryboardShot(
                position=position,
                title=title[:255],
                source_text=source_text,
                start_seconds=start_seconds,
                end_seconds=end_seconds,
                duration=duration,
            )
        )
        expected_start = end_seconds

    first_header_line = headers[0][0]
    preamble_lines = lines[:first_header_line]
    preamble = "\n".join(line.strip() for line in preamble_lines if line.strip())
    global_constraints = ""
    if constraint_index is not None:
        global_constraints = "\n".join(
            line.strip()
            for line in lines[constraint_index + 1:]
            if line.strip()
        )

    # 只根据用户文本识别策略，不在缺失时擅自补写对白、字幕或水印。
    searchable = text.lower()
    return ProfessionalStoryboard(
        title=_default_title(preamble_lines),
        shots=shots,
        global_constraints=global_constraints,
        no_dialogue=bool(re.search(r"无对白|无旁白|no\s+dialogue", searchable)),
        no_subtitles=bool(re.search(r"无字幕|no\s+subtitles?", searchable)),
        no_watermark=bool(re.search(r"无水印|no\s+watermarks?", searchable)),
        preamble=preamble,
    )


def build_shot_prompt(
    shot: StoryboardShot,
    *,
    product_name: str,
    global_constraints: str,
    no_dialogue: bool,
    no_subtitles: bool,
    no_watermark: bool,
    previous_shot: StoryboardShot | None = None,
    next_shot: StoryboardShot | None = None,
    reference_assets: list[dict[str, Any]] | None = None,
) -> str:
    """构造供应商提示词，同时把用户原文完整保留在提示词内。"""
    def first_sentence(value: str) -> str:
        parts = [item.strip() for item in re.split(r"(?<=[。！？.!?])\s*", value) if item.strip()]
        return (parts[0] if parts else value.strip())[:180]

    def last_sentence(value: str) -> str:
        parts = [item.strip() for item in re.split(r"(?<=[。！？.!?])\s*", value) if item.strip()]
        return (parts[-1] if parts else value.strip())[:180]

    policy = [
        "- No dialogue or narration text." if no_dialogue else "",
        "- No burned-in subtitles or captions." if no_subtitles else "",
        "- No watermark, logo overlay or extra text." if no_watermark else "",
    ]
    policy_text = "\n".join(item for item in policy if item)
    constraints = global_constraints.strip() or "Keep character, product and scene continuity."
    boundary_text = ""
    if previous_shot is not None or next_shot is not None:
        boundary_lines = ["SHOT BOUNDARY CONTINUITY:"]
        if previous_shot is not None:
            boundary_lines.extend(
                [
                    "PREVIOUS SHOT BOUNDARY",
                    f'- Title: {previous_shot.title}',
                    f"- Ending action: {last_sentence(previous_shot.source_text)}",
                    "- Start from the same subject, object state, lighting, color and scene logic.",
                ]
            )
        if next_shot is not None:
            boundary_lines.extend(
                [
                    "NEXT SHOT BOUNDARY",
                    f'- Title: {next_shot.title}',
                    f"- Opening action: {first_sentence(next_shot.source_text)}",
                    "- End with a compatible action direction and composition for the next shot.",
                ]
            )
        boundary_text = "\n".join(boundary_lines)

    reference_text = build_reference_asset_prompt(reference_assets or [])

    return (
        f"PROFESSIONAL SCRIPT SHOT {shot.position}\n"
        f"Product reference: {product_name}\n"
        f"Shot title: {shot.title}\n"
        f"Target duration: {shot.duration} seconds\n"
        f"Original user direction (do not rewrite or invent):\n{shot.source_text}\n\n"
        f"Project continuity constraints:\n{constraints}\n\n"
        f"{boundary_text}\n\n"
        f"{reference_text}\n\n"
        "Only render information explicitly present in the original direction. "
        "Do not invent people, brands, product details, locations, dialogue, text, "
        "prices or performance claims.\n"
        f"{policy_text}\n\n"
        f"{PRODUCT_LOCK_PROMPT}"
    ).strip()


def build_reference_asset_prompt(reference_assets: list[dict[str, Any]]) -> str:
    """把商品图的顺序和用途写成供应商可理解的参考图映射。"""
    if not reference_assets:
        return ""
    lines = ["PRODUCT REFERENCE IMAGE MAP:"]
    for index, item in enumerate(reference_assets, start=1):
        role = str(item.get("role") or "detail")
        lines.append(
            f"- Reference image {index} ({role}): preserve the exact product "
            "shape, color, material, label, logo and package structure shown in this image."
        )
    lines.append(
        "- Use the images as complementary product evidence; do not morph one view into another."
    )
    return "\n".join(lines)


def provider_render_duration(
    model: str,
    target_duration: int,
    provider_name: str = "minimax",
) -> int:
    """返回供应商实际可接受的镜头时长，短镜头在合成阶段再裁切。"""
    # 延迟导入避免 Provider 适配器与分镜提示词模块循环依赖。
    from app.services.video_provider import get_video_provider

    return get_video_provider(provider_name).render_duration(
        model,
        target_duration,
    )


def estimate_storyboard_credits(
    shots: list[StoryboardShot],
    *,
    model: str,
    resolution: str,
) -> int:
    """按供应商实际渲染时长估算项目积分。"""
    return sum(
        estimate_video_credits(
            model,
            resolution,
            provider_render_duration(model, shot.duration),
        )
        for shot in shots
    )
