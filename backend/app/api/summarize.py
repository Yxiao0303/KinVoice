"""
对话总结接口 —— POST /chat/summarize（精简版）
前端在离开 Companion 页面时调用，传入完整对话历史
后端用 LLM 总结 → 创建传承笔记
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_session, AsyncSessionLocal
from app.models.card import Card
from app.services.card_summarizer import summarize_to_notes
from app.services.family_service import get_user_family_id
from app.schemas.memory import CardOut
from app.middleware.user_identity import get_user_id
from app.utils.logger import logger

router = APIRouter(prefix="/chat", tags=["对话总结"])

from pydantic import BaseModel, Field


class SummarizeRequest(BaseModel):
    """总结请求"""
    history: list[dict] = Field(..., min_length=1, description="对话历史 [{role, content}, ...]")


class SummarizeResult(BaseModel):
    """单条操作结果"""
    action: str = "create"
    card_id: int | None = None
    card: CardOut | None = None
    message: str = ""


class SummarizeResponse(BaseModel):
    """总结响应"""
    results: list[SummarizeResult]
    total_created: int


@router.post("/summarize", response_model=SummarizeResponse)
async def summarize_chat(
    request: SummarizeRequest,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_user_id),
):
    """
    总结多轮对话，自动生成传承笔记。

    流程：
    1. LLM 从对话中提取值得记录的笔记
    2. 创建 Card 记录（自动归属到用户的家庭组）
    """
    history = request.history
    logger.info(f"收到总结请求，对话轮数: {len(history)}")

    # 解析用户的 family_id
    family_id = await get_user_family_id(session, user_id) or "1"

    # LLM 总结
    notes = await summarize_to_notes(history)

    if not notes:
        return SummarizeResponse(results=[], total_created=0)

    # 创建笔记
    results = []
    created = 0

    for note_data in notes:
        try:
            title = note_data.get("title", "未命名笔记")
            content = note_data.get("content", "")
            if not title or not content:
                continue

            card = Card(
                title=title,
                content=content,
                author=user_id,
                family_id=family_id,
            )
            session.add(card)
            await session.flush()
            await session.refresh(card)
            results.append(SummarizeResult(
                action="create",
                card_id=card.id,
                card=CardOut.model_validate(card),
                message="笔记已创建"
            ))
            created += 1
            logger.info(f"总结创建笔记: id={card.id} title={title} family_id={family_id}")

        except Exception as e:
            logger.error(f"创建笔记失败: {e}")

    return SummarizeResponse(
        results=results,
        total_created=created,
    )
