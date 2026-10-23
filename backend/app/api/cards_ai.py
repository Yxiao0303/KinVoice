"""
Cards AI 接口 —— 从对话中提取传承笔记

POST /cards/ai/extract  — 从对话消息中提取传承卡片

此接口独立于聊天流程，使用 card_summarizer.py 中独立的 AI prompt，
与 Cloudie 聊天 AI 完全解耦。

user_id 通过 X-User-Id Header 传递（Depends(get_user_id)）。
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import AsyncSessionLocal
from app.models.card import Card
from app.schemas.cards_ai import CardsExtractRequest, CardsExtractResponse, CardCreated
from app.services.card_summarizer import summarize_to_notes
from app.middleware.user_identity import get_user_id
from app.utils.logger import logger

router = APIRouter(prefix="/cards/ai", tags=["AI卡片提取"])


@router.post("/extract", response_model=CardsExtractResponse)
async def extract_from_chat(
    req: CardsExtractRequest,
    user_id: str = Depends(get_user_id),
):
    """
    从对话消息中提取值得传承的家庭记忆，自动创建传承卡片。

    前端在 Companion 页面聊天后调用此接口，传入最近的对话消息。
    使用独立的 AI prompt（card_summarizer.SUMMARIZE_SYSTEM_PROMPT），
    与 Cloudie 聊天 AI 完全解耦。
    """
    logger.info(f"卡片提取请求: user_id={user_id}, family_id={req.family_id}, msgs={len(req.messages)}")

    if not req.messages:
        return CardsExtractResponse(ok=False, message="无对话消息，跳过提取")

    # 转换消息格式
    history = [{"role": m.role, "content": m.content} for m in req.messages]

    # 调用独立的卡片提取 AI
    try:
        notes = await summarize_to_notes(history)
    except Exception as e:
        logger.error(f"卡片提取 LLM 调用失败: {e}")
        return CardsExtractResponse(ok=False, message=f"AI 提取失败: {str(e)}")

    if not notes:
        return CardsExtractResponse(ok=True, message="对话中无值得记录的内容")

    # 写入数据库
    cards_created = []
    try:
        async with AsyncSessionLocal() as session:
            for note_data in notes:
                title = note_data.get("title", "未命名笔记")
                content = note_data.get("content", "")
                if not title or not content:
                    continue

                card = Card(
                    title=title,
                    content=content,
                    author=user_id,
                    family_id=req.family_id or "1",
                )
                session.add(card)
                await session.flush()
                await session.refresh(card)
                cards_created.append(CardCreated(id=card.id, title=card.title))
                logger.info(f"AI 提取创建卡片: id={card.id} title={title}")

            await session.commit()

    except Exception as e:
        logger.error(f"卡片写入数据库失败: {e}")
        return CardsExtractResponse(
            ok=False,
            cards_created=cards_created,
            total_created=len(cards_created),
            message=f"部分创建成功，但写入数据库时出错: {str(e)}",
        )

    return CardsExtractResponse(
        ok=True,
        cards_created=cards_created,
        total_created=len(cards_created),
        message=f"已从对话中提取 {len(cards_created)} 条传承笔记",
    )
