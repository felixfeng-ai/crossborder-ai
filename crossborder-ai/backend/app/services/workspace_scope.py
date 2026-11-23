"""旧 Web 工作区作用域过滤。"""

from sqlalchemy import or_

from app.dependencies import WorkspaceContext


def workspace_access_filter(model, context: WorkspaceContext):
    """显式工作区严格匹配；仅默认个人工作区兼容历史空归属数据。"""

    current_workspace = model.workspace_id == context.workspace.id
    if context.explicit or context.workspace.type != "personal":
        return current_workspace
    return or_(
        current_workspace,
        model.workspace_id.is_(None),
    )
