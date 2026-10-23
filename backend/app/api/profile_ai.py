"""
AI 档案编写接口

POST /profile/ai/extract         — 从对话中提取信息，更新用户档案（前端传入 messages）
POST /profile/ai/update-dynamic  — 自动从最近对话更新动态档案（Companion onHide 调用）
POST /profile/ai/update-stable   — 自动从最近对话更新固定档案（Profile 页面调用）
GET  /profile/ai/read            — 读取用户档案

user_id 统一通过 X-User-Id Header 传递（Depends(get_user_id)）。
"""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.card import ChatMessage, Conversation
from app.schemas.profile_ai import (
    ProfileExtractRequest, ProfileExtractResponse,
    ProfileReadResponse,
)
from app.services.profile_writer import update_dynamic_profile, update_stable_profile, read_profiles
from app.middleware.user_identity import get_user_id
from app.utils.logger import logger

router = APIRouter(prefix="/profile/ai", tags=["AI档案编写"])


# ── 辅助：读取用户最近对话消息 ──

async def _get_recent_messages(user_id: str, limit: int = 100) -> list[dict]:
    """读取用户最近 N 条 AI 对话消息（用于自动档案更新）"""
    async with AsyncSessionLocal() as session:
        # 找到用户最近的 AI 对话会话
        conv_result = await session.execute(
            select(Conversation.id)
            .where(Conversation.user_id == user_id, Conversation.type == "ai")
            .order_by(Conversation.created_at.desc())
            .limit(3)
        )
        conv_ids = [row[0] for row in conv_result.all()]
        if not conv_ids:
            return []

        msg_result = await session.execute(
            select(ChatMessage.role, ChatMessage.content)
            .where(ChatMessage.conversation_id.in_(conv_ids))
            .order_by(ChatMessage.created_at.asc())
            .limit(limit)
        )
        return [{"role": row[0], "content": row[1]} for row in msg_result.all()]


@router.post("/extract", response_model=ProfileExtractResponse)
async def extract_from_chat(
    req: ProfileExtractRequest,
    user_id: str = Depends(get_user_id),
):
    """
    从对话消息中提取信息，更新用户档案。

    前端在 Companion 页面聊天后调用此接口，传入最近的对话消息。
    支持 stable（固定信息）和 dynamic（动态信息）两种类型。

    此接口独立于聊天流程，有自己独立的 AI prompt（profile_writer.STABLE_SYSTEM_PROMPT /
    DYNAMIC_SYSTEM_PROMPT），与 Cloudie 聊天 AI 完全解耦。
    """
    logger.info(f"档案提取请求: user_id={user_id}, type={req.profile_type}, msgs={len(req.messages)}")

    if not req.messages:
        return ProfileExtractResponse(
            ok=False,
            profile_type=req.profile_type,
            path="",
            content_preview="（无对话消息，跳过提取）",
            messages_used=0,
        )

    # 转换消息格式
    messages = [{"role": m.role, "content": m.content} for m in req.messages]

    try:
        if req.profile_type == "stable":
            result = await update_stable_profile(user_id, messages)
        else:
            result = await update_dynamic_profile(user_id, messages)
    except Exception as e:
        logger.error(f"档案提取失败: {e}")
        return ProfileExtractResponse(
            ok=False,
            profile_type=req.profile_type,
            path="",
            content_preview=f"提取失败: {str(e)}",
            messages_used=len(messages),
        )

    return ProfileExtractResponse(**result)


@router.post("/update-dynamic", response_model=ProfileExtractResponse)
async def update_dynamic(user_id: str = Depends(get_user_id)):
    """
    自动从用户最近对话中提取信息，更新动态档案。

    Companion 页面 onHide 时调用。后端自动读取最近对话消息，
    无需前端传入 messages。提取逻辑与 Cloudie 聊天 AI 完全解耦。
    """
    logger.info(f"自动更新动态档案: user_id={user_id}")

    try:
        messages = await _get_recent_messages(user_id, limit=60)
    except Exception as e:
        logger.error(f"读取最近对话失败: {e}")
        return ProfileExtractResponse(
            ok=False, profile_type="dynamic", path="",
            content_preview=f"读取对话失败: {str(e)}", messages_used=0,
        )

    if not messages:
        return ProfileExtractResponse(
            ok=True, profile_type="dynamic", path="",
            content_preview="（无对话消息，跳过更新）", messages_used=0,
        )

    try:
        result = await update_dynamic_profile(user_id, messages)
        return ProfileExtractResponse(**result)
    except Exception as e:
        logger.error(f"动态档案更新失败: {e}")
        return ProfileExtractResponse(
            ok=False, profile_type="dynamic", path="",
            content_preview=f"更新失败: {str(e)}", messages_used=len(messages),
        )


@router.post("/update-stable", response_model=ProfileExtractResponse)
async def update_stable(user_id: str = Depends(get_user_id)):
    """
    自动从用户最近对话中提取信息，全量重写固定档案。

    Profile 页面手动触发。后端自动读取最近对话消息，
    无需前端传入 messages。提取逻辑与 Cloudie 聊天 AI 完全解耦。
    """
    logger.info(f"自动更新固定档案: user_id={user_id}")

    try:
        messages = await _get_recent_messages(user_id, limit=200)
    except Exception as e:
        logger.error(f"读取最近对话失败: {e}")
        return ProfileExtractResponse(
            ok=False, profile_type="stable", path="",
            content_preview=f"读取对话失败: {str(e)}", messages_used=0,
        )

    if not messages:
        return ProfileExtractResponse(
            ok=False, profile_type="stable", path="",
            content_preview="（无对话消息，无法生成档案）", messages_used=0,
        )

    try:
        result = await update_stable_profile(user_id, messages)
        return ProfileExtractResponse(**result)
    except Exception as e:
        logger.error(f"固定档案更新失败: {e}")
        return ProfileExtractResponse(
            ok=False, profile_type="stable", path="",
            content_preview=f"更新失败: {str(e)}", messages_used=len(messages),
        )


@router.get("/read", response_model=ProfileReadResponse)
async def read_profile(user_id: str = Depends(get_user_id)):
    """
    读取用户档案（固定 + 动态两份 Markdown）。

    user_id 通过 X-User-Id Header 传入，与项目其他接口保持一致。
    """
    data = read_profiles(user_id)
    return ProfileReadResponse(**data)
