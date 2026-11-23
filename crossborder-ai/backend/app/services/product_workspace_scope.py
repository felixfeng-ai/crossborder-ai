"""商品与 SKU 的工作区访问条件。"""

from fastapi import HTTPException, status
from sqlalchemy import and_, or_

from app.dependencies import WorkspaceContext
from app.models.listing import Listing
from app.models.listing_draft import ListingDraft
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.user import User


def product_workspace_scope(
    context: WorkspaceContext,
    current_user: User,
):
    """商品读取按工作区隔离，仅个人区兼容未回填历史数据。"""

    workspace_scope = Product.workspace_id == context.workspace.id
    if (
        context.workspace.type == "personal"
        and context.workspace.owner_user_id == current_user.id
    ):
        return or_(
            workspace_scope,
            and_(
                Product.workspace_id.is_(None),
                Product.user_id == current_user.id,
            ),
        )
    return workspace_scope


def variant_workspace_scope(
    context: WorkspaceContext,
    current_user: User,
):
    """SKU 必须跟随商品工作区，个人区兼容历史未回填数据。"""

    workspace_scope = ProductVariant.workspace_id == context.workspace.id
    if (
        context.workspace.type == "personal"
        and context.workspace.owner_user_id == current_user.id
    ):
        return or_(
            workspace_scope,
            and_(
                ProductVariant.workspace_id.is_(None),
                ProductVariant.user_id == current_user.id,
            ),
        )
    return workspace_scope


def listing_draft_workspace_scope(
    context: WorkspaceContext,
    current_user: User,
):
    """ListingDraft 按工作区隔离，个人区兼容未回填历史数据。"""

    workspace_scope = ListingDraft.workspace_id == context.workspace.id
    if (
        context.workspace.type == "personal"
        and context.workspace.owner_user_id == current_user.id
    ):
        return or_(
            workspace_scope,
            and_(
                ListingDraft.workspace_id.is_(None),
                ListingDraft.user_id == current_user.id,
            ),
        )
    return workspace_scope


def legacy_listing_workspace_scope(
    context: WorkspaceContext,
    current_user: User,
):
    """旧 Listing 表按工作区隔离，个人区兼容未回填历史数据。"""

    workspace_scope = Listing.workspace_id == context.workspace.id
    if (
        context.workspace.type == "personal"
        and context.workspace.owner_user_id == current_user.id
    ):
        return or_(
            workspace_scope,
            and_(
                Listing.workspace_id.is_(None),
                Listing.owner_id == current_user.id,
            ),
        )
    return workspace_scope


def ensure_product_writer(context: WorkspaceContext) -> None:
    if context.role not in {"owner", "admin", "operator"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="没有商品操作权限",
        )
