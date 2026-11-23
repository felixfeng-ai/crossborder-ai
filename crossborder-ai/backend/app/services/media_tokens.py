"""私有媒体短时签名令牌。

浏览器和原生图片组件无法稳定携带 Authorization 头，因此媒体文件使用
绑定资源、用户和工作区的短时 JWT 查询参数；数据库主键不再承担访问控制。
"""

from datetime import timedelta
from urllib.parse import urlencode

from app.core.security import create_access_token, decode_token_safe


MEDIA_ACCESS_TTL_MINUTES = 15


def sign_media_path(
    path: str,
    *,
    resource_type: str,
    resource_id,
    user_id,
    workspace_id,
) -> str:
    """为单个媒体资源生成短时可访问 URL。"""

    token = create_access_token(
        subject=str(user_id),
        extra_claims={
            "type": "media_access",
            "resource_type": resource_type,
            "resource_id": str(resource_id),
            "workspace_id": str(workspace_id or ""),
        },
        expires_delta=timedelta(minutes=MEDIA_ACCESS_TTL_MINUTES),
    )
    return f"{path}?{urlencode({'token': token})}"


def media_token_matches(
    token: str | None,
    *,
    resource_type: str,
    resource_id,
    user_id,
    workspace_id,
) -> bool:
    """校验媒体令牌的资源、用户和工作区归属。"""

    if not token:
        return False
    payload = decode_token_safe(token)
    if not payload or payload.get("type") != "media_access":
        return False
    return (
        str(payload.get("sub") or "") == str(user_id or "")
        and str(payload.get("resource_type") or "") == resource_type
        and str(payload.get("resource_id") or "") == str(resource_id)
        and str(payload.get("workspace_id") or "")
        == str(workspace_id or "")
    )
