"""前端 API 调用与 FastAPI OpenAPI 路径契约测试。"""

import re
from pathlib import Path

from app.main import app


FRONTEND_SRC = Path(__file__).resolve().parents[2] / "frontend" / "src"


_CALL_RE = re.compile(
    r"apiClient\.(get|post|put|delete)(?:<[^>]+>)?\(\s*"
    r"(?:`([^`]+)`|'([^']+)'|\"([^\"]+)\")",
    re.DOTALL,
)


def _normalize_path(path: str) -> str:
    """把前端模板路径归一成 OpenAPI 路径形状。"""
    path = path.split("?", 1)[0]
    # SDK 生成的查询参数拼接在路径末尾时直接去掉，例如 /upgrades${params}。
    path = re.sub(r"/\$\{[^}]+\}", "/{param}", path)
    path = re.sub(r"\$\{[^}]+\}", "", path)
    if not path.startswith("/api/v1"):
        path = f"/api/v1/{path.lstrip('/')}"
    # 参数名可能不同，只比较路径结构和参数位置。
    return re.sub(r"\{[^}]+\}", "{}", path.rstrip("/") or "/")


def _frontend_calls() -> set[tuple[str, str]]:
    calls: set[tuple[str, str]] = set()
    for file_path in FRONTEND_SRC.rglob("*"):
        if file_path.suffix not in {".ts", ".tsx"} or not file_path.is_file():
            continue
        source = file_path.read_text(encoding="utf-8")
        for match in _CALL_RE.finditer(source):
            method = match.group(1).upper()
            raw_path = match.group(2) or match.group(3) or match.group(4)
            if not raw_path or not raw_path.startswith("/"):
                continue
            calls.add((method, _normalize_path(raw_path)))
    return calls


def test_all_frontend_api_calls_exist_in_openapi():
    """前端每个静态 API 调用都必须有对应后端路由。"""
    openapi_paths = app.openapi().get("paths", {})
    backend_routes: set[tuple[str, str]] = set()
    for path, methods in openapi_paths.items():
        normalized = re.sub(r"\{[^}]+\}", "{}", path.rstrip("/") or "/")
        for method in methods:
            backend_routes.add((method.upper(), normalized))

    missing = sorted(_frontend_calls() - backend_routes)
    assert missing == [], f"前端调用了不存在的后端接口：{missing}"
