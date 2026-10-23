"""
Chat 接口 —— 陪伴式 AI 对话（Cloudie 主 Agent）

Cloudie 是主 Agent，后端自动编排以下子能力：
1. 每次对话自动读取用户档案（stable + dynamic），注入 system prompt
2. 对话中自动 FTS 检索传承笔记和对话历史，作为上下文注入
3. 每 N 轮对话自动调用 Profile AI 更新动态档案（fire-and-forget）
4. 每 M 轮对话自动调用 Cards AI 提取传承卡片（fire-and-forget）

子 AI（Profile AI / Cards AI）各有独立 prompt，与 Cloudie 完全解耦。
"""
import asyncio
import re
from fastapi import APIRouter, HTTPException, Depends, Request
from sqlalchemy import select, delete, func
from app.services.llm_service import call_llm
from app.services.cloudie_prompt import build_system_prompt
from app.services.profile_writer import read_profiles, update_dynamic_profile
from app.services.card_summarizer import summarize_to_notes
from app.services.search_service import search_context
from app.services.family_service import get_user_family_id
from app.schemas.chat import (
    ChatRequest, ChatResponse,
    ConversationListOut, ConversationOut,
    HistoryOut, MessageOut,
)
from app.models.card import Conversation, ChatMessage, Card
from app.db.session import AsyncSessionLocal
from app.middleware.user_identity import get_user_id
from app.middleware.rate_limiter import check_rate_limit
from app.utils.logger import logger

router = APIRouter(prefix="/chat", tags=["陪伴对话"])


# ── 会话管理辅助函数 ──

async def get_or_create_conversation(session, conv_id: int | None, first_message: str, user_id: str) -> Conversation:
    """
    获取或创建会话（仅限 AI 对话类型，且归属当前用户）。

    设计决策：当 conv_id 在 DB 中找不到时（包括前端本地 Date.now() ID），
    创建新会话而非抛 404。这比要求前端区分"本地ID"和"远端ID"更健壮。
    用户隔离由 user_id 过滤保证 —— 即使传入他人的 conv_id 也只会创建新会话。
    """
    if conv_id:
        result = await session.execute(
            select(Conversation).where(
                Conversation.id == conv_id,
                Conversation.type == "ai",
                Conversation.user_id == user_id,
            )
        )
        conv = result.scalar_one_or_none()
        if conv:
            return conv
        logger.info(f"会话 {conv_id} 未找到（可能为前端本地 ID），创建新会话")
    title = first_message[:50] if first_message else "新对话"
    conv = Conversation(title=title, type="ai", user_id=user_id)
    session.add(conv)
    await session.flush()
    return conv


async def build_history(session, conv_id: int) -> list[dict]:
    """
    从数据库构建对话历史。

    安全限制：最多取最近 50 条消息，防止超长对话导致 token 爆炸。
    """
    result = await session.execute(
        select(ChatMessage)
        .where(ChatMessage.conversation_id == conv_id)
        .order_by(ChatMessage.created_at.asc())
        .limit(50)
    )
    return [{"role": m.role, "content": m.content} for m in result.scalars()]


# ── 信号解析 ──

_SIGNAL_PROFILE = re.compile(r'<!--\s*PROFILE\s*-->')
_SIGNAL_CARD = re.compile(r'<!--\s*CARD\s*-->')


def _parse_signals(reply: str) -> tuple[str, bool, bool]:
    """
    从 Cloudie 回复中解析主动触发标记，返回 (清洁回复, 是否触发档案更新, 是否触发卡片提取)。
    标记会被从回复中移除，用户永远看不到。
    """
    has_profile = bool(_SIGNAL_PROFILE.search(reply))
    has_card = bool(_SIGNAL_CARD.search(reply))
    clean = _SIGNAL_PROFILE.sub('', reply)
    clean = _SIGNAL_CARD.sub('', clean)
    clean = clean.strip()
    return clean, has_profile, has_card


# ── 子 AI 提取（公共逻辑）──

async def _do_extract(
    messages: list[dict],
    user_id: str,
    family_id: str | None,
    do_profile: bool = False,
    do_cards: bool = False,
    source: str = "",
):
    """
    统一的子 AI 提取逻辑：根据条件更新动态档案 + 提取传承卡片。

    与 Cloudie 主 Agent 完全解耦：使用独立 AI prompt，异常不影响对话。
    """
    if do_profile:
        try:
            result = await update_dynamic_profile(user_id, messages)
            logger.info(f"[{source}] 档案更新: {result.get('content_preview', '')[:100]}")
        except Exception as e:
            logger.warning(f"[{source}] 档案更新失败: {e}")

    if do_cards:
        try:
            notes = await summarize_to_notes(messages)
            if notes:
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
                            family_id=family_id or "1",
                        )
                        session.add(card)
                    await session.commit()
                logger.info(f"[{source}] 卡片提取: 创建了 {len(notes)} 张卡片")
        except Exception as e:
            logger.warning(f"[{source}] 卡片提取失败: {e}")


async def _handle_signals(
    has_profile: bool,
    has_card: bool,
    conv_id: int,
    user_id: str,
    family_id: str | None,
):
    """根据 LLM 主动信号触发子 AI 提取（fire-and-forget）。"""
    if not has_profile and not has_card:
        return
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ChatMessage)
                .where(ChatMessage.conversation_id == conv_id)
                .order_by(ChatMessage.created_at.asc())
                .limit(60)
            )
            messages = [{"role": m.role, "content": m.content} for m in result.scalars()]

        if not messages:
            return
        await _do_extract(messages, user_id, family_id, has_profile, has_card, source="信号")
    except Exception as e:
        logger.warning(f"[信号] 整体异常（不影响对话）: {e}")


async def _background_extract(conv_id: int, user_id: str, family_id: str | None):
    """
    定期后台提取（fire-and-forget）。
    - 每 3 条用户消息 → 更新动态档案
    - 每 5 条用户消息 → 提取传承卡片
    """
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(func.count(ChatMessage.id)).where(
                    ChatMessage.conversation_id == conv_id,
                    ChatMessage.role == "user",
                )
            )
            user_msg_count = result.scalar() or 0

            result = await session.execute(
                select(ChatMessage)
                .where(ChatMessage.conversation_id == conv_id)
                .order_by(ChatMessage.created_at.asc())
                .limit(60)
            )
            messages = [{"role": m.role, "content": m.content} for m in result.scalars()]

        if not messages:
            return

        do_profile = user_msg_count >= 1 and user_msg_count % 3 == 0
        do_cards = user_msg_count >= 1 and user_msg_count % 5 == 0
        await _do_extract(messages, user_id, family_id, do_profile, do_cards, source="定期")
    except Exception as e:
        logger.warning(f"[定期] 整体异常（不影响对话）: {e}")


# ── POST /chat ──

@router.post("", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest, request: Request, user_id: str = Depends(get_user_id)):
    """
    Cloudie 陪伴对话 —— 主 Agent 入口。

    后端自动：
    1. 注入用户档案（每次对话）
    2. FTS 检索传承笔记 + 对话历史（作为上下文）
    3. 后台提取档案 + 卡片（fire-and-forget）
    """
    # 频率限制
    await check_rate_limit(request, user_id)

    logger.info(f"收到对话: user_id={user_id}, msg_len={len(req.message)}, conv_id={req.conversation_id}, family_id={req.family_id}")

    # ① 加载用户画像（注入到 system prompt，让 Cloudie 认识用户）
    user_profile = read_profiles(user_id)

    # ② 拼接 system prompt（先不含检索上下文，后面补充）
    system_prompt = build_system_prompt(user_profile, "")

    # ── 会话持久化模式（默认路径）──
    try:
        async with AsyncSessionLocal() as session:
            # 解析 family_id（用于 FTS 检索）
            family_id = req.family_id or await get_user_family_id(session, user_id) or "1"

            # ③ FTS5 检索传承笔记 + 对话历史
            ctx = ""
            if family_id:
                try:
                    ctx = await search_context(session, req.message, user_id, family_id)
                except Exception as e:
                    logger.warning(f"FTS 检索异常（降级忽略）: {e}")

            # 拼接完整 system prompt（画像 + 检索上下文）
            if ctx:
                system_prompt = build_system_prompt(user_profile, ctx)

            conv = await get_or_create_conversation(session, req.conversation_id, req.message, user_id)

            # 保存用户消息
            user_msg = ChatMessage(conversation_id=conv.id, role="user", content=req.message)
            session.add(user_msg)
            await session.flush()

            # 构建历史
            history = await build_history(session, conv.id)
            full_messages = [{"role": "system", "content": system_prompt}] + history

            try:
                reply_text = await call_llm(full_messages)
            except Exception as e:
                logger.error(f"LLM 调用失败: {e}")
                reply_text = "我暂时无法回复，请稍后再试。"

            # ④ 解析主动触发标记（<!--PROFILE--> / <!--CARD-->），剥离后保存清洁文本
            clean_reply, has_profile_signal, has_card_signal = _parse_signals(reply_text)
            if has_profile_signal or has_card_signal:
                logger.info(f"检测到主动信号: PROFILE={has_profile_signal}, CARD={has_card_signal}")

            # 保存 AI 回复（已剥离标记）
            asst_msg = ChatMessage(conversation_id=conv.id, role="assistant", content=clean_reply)
            session.add(asst_msg)
            await session.commit()
            await session.refresh(asst_msg)

            # ⑤ 主动信号触发子 AI（fire-and-forget）
            if has_profile_signal or has_card_signal:
                asyncio.create_task(_handle_signals(
                    has_profile_signal, has_card_signal, conv.id, user_id, family_id
                ))

            # ⑥ 定期后台提取（每 3/5 轮，fire-and-forget）
            asyncio.create_task(_background_extract(conv.id, user_id, family_id))

            return ChatResponse(
                reply=clean_reply,
                conversation_id=conv.id,
                message_id=asst_msg.id,
                tokens_used=0,
            )
    except Exception as e:
        logger.error(f"聊天接口异常: {str(e)}")
        raise


# ── GET /chat/conversations ──

@router.get("/conversations", response_model=ConversationListOut)
async def list_conversations(user_id: str = Depends(get_user_id)):
    """列出当前用户的 AI 对话会话（按创建时间倒序）"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Conversation)
            .where(Conversation.user_id == user_id, Conversation.type == "ai")
            .order_by(Conversation.created_at.desc())
        )
        convs = result.scalars().all()
        return ConversationListOut(
            conversations=[
                ConversationOut(id=c.id, title=c.title, created_at=c.created_at)
                for c in convs
            ]
        )


# ── GET /chat/history ──

@router.get("/history", response_model=HistoryOut)
async def get_history(conversation_id: int, user_id: str = Depends(get_user_id)):
    """拉取某个会话的全部消息历史（仅限当前用户的会话）"""
    async with AsyncSessionLocal() as session:
        conv_result = await session.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.type == "ai",
                Conversation.user_id == user_id,
            )
        )
        conv = conv_result.scalar_one_or_none()
        if not conv:
            raise HTTPException(status_code=404, detail="会话不存在或不是 AI 对话")

        msg_result = await session.execute(
            select(ChatMessage)
            .where(ChatMessage.conversation_id == conversation_id)
            .order_by(ChatMessage.created_at.asc())
        )
        messages = msg_result.scalars().all()

        return HistoryOut(
            conversation_id=conversation_id,
            messages=[
                MessageOut(id=m.id, role=m.role, content=m.content, created_at=m.created_at)
                for m in messages
            ]
        )


# ── DELETE /chat/conversations/{conv_id} ──

@router.delete("/conversations/{conv_id}")
async def delete_conversation(conv_id: int, user_id: str = Depends(get_user_id)):
    """删除会话及其所有关联消息（硬删除，仅限当前用户的会话）"""
    async with AsyncSessionLocal() as session:
        conv_result = await session.execute(
            select(Conversation).where(
                Conversation.id == conv_id,
                Conversation.user_id == user_id,
            )
        )
        conv = conv_result.scalar_one_or_none()
        if not conv:
            raise HTTPException(status_code=404, detail="会话不存在或无权操作")

        await session.execute(
            delete(ChatMessage).where(ChatMessage.conversation_id == conv_id)
        )
        await session.delete(conv)
        await session.commit()

        logger.info(f"已删除会话 {conv_id} 及其消息")
        return {"ok": True, "deleted_id": conv_id}
