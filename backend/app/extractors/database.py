"""
DatabaseMessageSource —— 从 SQLite 数据库提取今日对话消息
"""
from datetime import date
from sqlalchemy import select
from app.models.card import ChatMessage
from app.db.session import AsyncSessionLocal
from app.utils.logger import logger


class DatabaseMessageSource:
    """
    从数据库 chat_messages 表提取指定用户今日的消息。

    使用方式：
        source = DatabaseMessageSource()
        messages = await source.fetch_today_messages("default")
    """

    async def fetch_today_messages(self, user_id: str) -> list[dict]:
        """
        获取今日所有会话的消息，按时间正序。

        Args:
            user_id: 用户标识（预留，当前忽略）

        Returns:
            [{role, content, created_at}, ...]
        """
        today = date.today()
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ChatMessage)
                .where(ChatMessage.created_at >= today)
                .order_by(ChatMessage.created_at.asc())
            )
            messages = result.scalars().all()

        logger.info(f"提取今日消息: {len(messages)} 条")
        return [
            {
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in messages
        ]
