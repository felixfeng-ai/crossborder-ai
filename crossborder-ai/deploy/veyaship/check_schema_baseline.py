"""检测已有生产库是否需要在 Alembic 中建立历史基线。"""

import asyncio

from sqlalchemy import text

from app.core.database import engine


async def main() -> None:
    """输出 1 表示已有核心表，0 表示全新数据库。"""

    async with engine.connect() as conn:
        exists = await conn.scalar(
            text("SELECT to_regclass('public.users') IS NOT NULL")
        )
    print("1" if exists else "0")


if __name__ == "__main__":
    asyncio.run(main())
