"""
FTS5 全文检索服务 —— 为陪伴对话提供上下文检索

检索范围：
- cards（家庭卡片）：按 family_id 过滤，检索 title/content/author
- chat_messages（对话历史）：按 user_id 过滤（通过 conversations 关联），检索 content/role

设计决策：
- 使用 SQLite FTS5 外部内容表，不存数据副本
- 返回格式化的 Markdown 上下文，可直接拼入 system prompt
- 每个来源最多返回 K 条，防止 token 爆炸
"""
import re
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.utils.logger import logger

# 每个来源最多返回条数
TOP_K = 3

# FTS5 查询需要转义的字符（MATCH 语法特殊字符）
_FTS_ESCAPE = re.compile(r'[^\w\s]')


def _escape_fts_query(query: str) -> str:
    """
    转义用户查询中的 FTS5 特殊字符。
    
    FTS5 MATCH 语法中，以下字符有特殊含义，需要移除：
    ^ * " - ( ) 以及列名限定符 :
    
    策略：移除所有非字母数字和空格的字符，然后按空格拆分，
    给每个词加上双引号做精确匹配（避免 FTS5 的 OR 默认行为）。
    """
    cleaned = _FTS_ESCAPE.sub(' ', query)
    words = [w.strip() for w in cleaned.split() if w.strip() and len(w.strip()) > 1]
    if not words:
        return None
    # 每个词加引号，用空格连接 = AND 语义
    return ' '.join(f'"{w}"' for w in words[:10])  # 最多 10 个词


async def search_cards(session: AsyncSession, query: str, family_id: str) -> list[dict]:
    """检索家庭笔记"""
    fts_query = _escape_fts_query(query)
    if not fts_query:
        return []

    sql = text("""
        SELECT c.id, c.title, c.content, c.author
        FROM cards_fts fts
        JOIN cards c ON c.id = fts.rowid
        WHERE cards_fts MATCH :query
          AND c.family_id = :family_id
        ORDER BY rank
        LIMIT :limit
    """)
    result = await session.execute(sql, {"query": fts_query, "family_id": family_id, "limit": TOP_K})
    rows = result.fetchall()
    return [dict(r._mapping) for r in rows]


async def search_messages(session: AsyncSession, query: str, user_id: str) -> list[dict]:
    """检索当前用户的对话历史"""
    fts_query = _escape_fts_query(query)
    if not fts_query:
        return []

    sql = text("""
        SELECT cm.content, cm.role, c.title AS conv_title
        FROM chat_messages_fts fts
        JOIN chat_messages cm ON cm.id = fts.rowid
        JOIN conversations c ON c.id = cm.conversation_id
        WHERE chat_messages_fts MATCH :query
          AND c.user_id = :user_id
          AND c.type = 'ai'
        ORDER BY rank
        LIMIT :limit
    """)
    result = await session.execute(sql, {"query": fts_query, "user_id": user_id, "limit": TOP_K})
    rows = result.fetchall()
    return [dict(r._mapping) for r in rows]


def format_context(cards: list[dict], messages: list[dict]) -> str:
    """
    将检索结果格式化为 system prompt 可用的上下文文本。

    Returns:
        格式化后的 Markdown 文本；无结果时返回空字符串
    """
    parts = []

    if cards:
        card_lines = []
        for c in cards:
            author = f"（{c['author']}）" if c.get('author') else ""
            title = c.get('title') or "未命名笔记"
            body = c.get('content') or title
            card_lines.append(f"- **{title}**{author}：{body}")
        parts.append("【传承笔记】\n" + "\n".join(card_lines))

    if messages:
        msg_lines = []
        for m in messages:
            role_label = "用户" if m.get('role') == 'user' else "Cloudie"
            conv = f"「{m['conv_title']}」" if m.get('conv_title') else ""
            msg_lines.append(f"- {conv}{role_label}：{m['content']}")
        parts.append("【相关对话历史】\n" + "\n".join(msg_lines))

    return "\n\n".join(parts) if parts else ""


async def search_context(
    session: AsyncSession,
    query: str,
    user_id: str,
    family_id: str | None,
) -> str:
    """
    一站式检索：根据用户消息搜索卡片和对话历史，返回格式化的上下文。

    Args:
        session: 数据库会话
        query: 用户当前消息
        user_id: 当前用户 ID
        family_id: 用户所属家庭组 ID（None 时仅搜索对话历史）

    Returns:
        格式化的上下文文本，可直接拼入 system prompt；无结果时返回 ""
    """
    cards = []
    messages = []

    if family_id:
        try:
            cards = await search_cards(session, query, family_id)
        except Exception as e:
            logger.warning(f"卡片 FTS 检索失败: {e}")

    try:
        messages = await search_messages(session, query, user_id)
    except Exception as e:
        logger.warning(f"对话 FTS 检索失败: {e}")

    context = format_context(cards, messages)
    if context:
        logger.info(
            f"检索完成: query_len={len(query)}, cards={len(cards)}, msgs={len(messages)}, "
            f"context_len={len(context)}"
        )
    return context
