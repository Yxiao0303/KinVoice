"""
聊天室 API —— 家庭组成员互聊（私聊 + 群聊）

与 /chat（AI 对话）完全独立，共用 conversations + chat_messages 表。
通过 Conversation.type 区分：
  - "ai"      → 现有 AI 对话（chat.py 管理，本模块不碰）
  - "private" → 1v1 私聊
  - "group"   → 家庭群聊

路由前缀：/chatroom
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import AsyncSessionLocal
from app.models.card import Conversation, ChatMessage
from app.models.family import FamilyMembership, User
from app.schemas.chatroom import (
    SendMessageRequest, SendMessageResponse,
    MessagesResponse, MessageOut,
    ConversationItem, ConversationListResponse,
)
from app.middleware.user_identity import get_user_id
from app.services.family_service import get_user_family_id
from app.utils.logger import logger

router = APIRouter(prefix="/chatroom", tags=["家庭聊天室"])


# ── 辅助：解析用户家庭组 ID ──

async def resolve_family_id(user_id: str) -> str | None:
    """获取用户所在家庭组 ID"""
    async with AsyncSessionLocal() as session:
        return await get_user_family_id(session, user_id)


# ── 辅助：查询用户昵称 ──

async def get_nickname(session: AsyncSession, user_id: str) -> str:
    """查询用户昵称，不存在返回空字符串"""
    result = await session.execute(select(User.nickname).where(User.id == user_id))
    row = result.scalar_one_or_none()
    return row or ""


# ════════════════════════════════════════════════════════════════
# POST /chatroom/send  —  发送消息
# ════════════════════════════════════════════════════════════════

@router.post("/send", response_model=SendMessageResponse)
async def send_message(
    req: SendMessageRequest,
    user_id: str = Depends(get_user_id),
):
    """
    发送一条聊天消息。

    - 已有 conversation_id → 追加到已有会话
    - 无 conversation_id → 新建会话：
        - private: 查找 sender+receiver 之间的已有会话，有则复用
        - group: 新建群聊会话（一个家庭组只有一个群聊会话）
    """
    async with AsyncSessionLocal() as session:
        conv = None

        if req.conversation_id:
            # 续接已有会话
            result = await session.execute(
                select(Conversation).where(
                    Conversation.id == req.conversation_id,
                    Conversation.type.in_(["private", "group"]),
                )
            )
            conv = result.scalar_one_or_none()
            if not conv:
                raise HTTPException(status_code=404, detail="会话不存在或不是聊天室会话")

        elif req.chat_type == "private":
            if not req.receiver_id:
                raise HTTPException(status_code=400, detail="私聊需要指定 receiver_id")

            # 查找两人之间是否已有私聊会话（双向查找）
            result = await session.execute(
                select(Conversation).where(
                    Conversation.type == "private",
                    or_(
                        and_(
                            Conversation.sender_id == user_id,
                            Conversation.receiver_id == req.receiver_id,
                        ),
                        and_(
                            Conversation.sender_id == req.receiver_id,
                            Conversation.receiver_id == user_id,
                        ),
                    ),
                ).order_by(Conversation.created_at.desc()).limit(1)
            )
            conv = result.scalar_one_or_none()

            if not conv:
                # 新建私聊会话
                sender_nick = await get_nickname(session, user_id)
                receiver_nick = await get_nickname(session, req.receiver_id)
                conv = Conversation(
                    type="private",
                    sender_id=user_id,
                    receiver_id=req.receiver_id,
                    title=f"{sender_nick or '我'} ↔ {receiver_nick or '对方'}",
                )
                session.add(conv)
                await session.flush()

        elif req.chat_type == "group":
            # 获取用户家庭组
            fid = await resolve_family_id(user_id)
            if not fid:
                raise HTTPException(status_code=400, detail="你还没有加入家庭组，无法群聊")

            # 查找该家庭组是否已有群聊会话
            # 群聊会话通过 sender_id 存储 family_id（复用字段，不新增列）
            result = await session.execute(
                select(Conversation).where(
                    Conversation.type == "group",
                    Conversation.sender_id == fid,  # sender_id 存储 family_id
                ).order_by(Conversation.created_at.desc()).limit(1)
            )
            conv = result.scalar_one_or_none()

            if not conv:
                # 新建群聊会话
                conv = Conversation(
                    type="group",
                    family_id=fid,   # 显式设置 family_id，保持与 sender_id 一致
                    sender_id=fid,   # 复用 sender_id 存 family_id（兼容历史查询）
                    title="家庭群聊",
                )
                session.add(conv)
                await session.flush()
        else:
            raise HTTPException(status_code=400, detail="不支持的 chat_type")

        # 保存消息
        # ChatMessage.role: 用 "user" 存储发送者 user_id（复用 role 字段）
        msg = ChatMessage(
            conversation_id=conv.id,
            role=user_id,  # 复用 role 字段存 sender_id
            content=req.content,
        )
        session.add(msg)
        await session.commit()
        await session.refresh(msg)

        logger.info(f"聊天消息: conv={conv.id}, type={conv.type}, sender={user_id}")

        return SendMessageResponse(
            conversation_id=conv.id,
            message_id=msg.id,
            content=req.content,
            created_at=msg.created_at,
        )


# ════════════════════════════════════════════════════════════════
# GET /chatroom/messages  —  拉取消息（轮询用）
# ════════════════════════════════════════════════════════════════

@router.get("/messages", response_model=MessagesResponse)
async def get_messages(
    conversation_id: int = Query(..., description="会话 ID"),
    after_id: int = Query(0, description="增量拉取：只返回 id > after_id 的消息"),
    limit: int = Query(50, ge=1, le=200),
    user_id: str = Depends(get_user_id),
):
    """
    拉取会话消息列表。

    - after_id=0：首次加载，返回最近 limit 条
    - after_id>0：增量轮询，只返回新消息
    """
    async with AsyncSessionLocal() as session:
        # 验证会话存在且用户有权限
        result = await session.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        conv = result.scalar_one_or_none()
        if not conv:
            raise HTTPException(status_code=404, detail="会话不存在")

        # 权限检查：私聊必须是参与者，群聊必须在同一家庭组
        if conv.type == "private":
            if user_id not in (conv.sender_id, conv.receiver_id):
                raise HTTPException(status_code=403, detail="无权访问此私聊")
        elif conv.type == "group":
            fid = await resolve_family_id(user_id)
            if not fid or fid != conv.sender_id:
                raise HTTPException(status_code=403, detail="你不在该家庭组中")

        # 查询消息
        stmt = select(ChatMessage).where(
            ChatMessage.conversation_id == conversation_id
        )
        if after_id > 0:
            stmt = stmt.where(ChatMessage.id > after_id)

        stmt = stmt.order_by(ChatMessage.created_at.asc()).limit(limit)
        result = await session.execute(stmt)
        msgs = result.scalars().all()

        # 批量获取发送者昵称（去重）
        sender_ids = list(set(m.role for m in msgs))
        nickname_map: dict[str, str] = {}
        for sid in sender_ids:
            nickname_map[sid] = await get_nickname(session, sid)

        messages_out = [
            MessageOut(
                id=m.id,
                sender_id=m.role,
                sender_nickname=nickname_map.get(m.role, ""),
                content=m.content,
                created_at=m.created_at,
            )
            for m in msgs
        ]

        return MessagesResponse(
            conversation_id=conversation_id,
            messages=messages_out,
            has_more=len(messages_out) >= limit,
        )


# ════════════════════════════════════════════════════════════════
# GET /chatroom/conversations  —  聊天列表
# ════════════════════════════════════════════════════════════════

@router.get("/conversations", response_model=ConversationListResponse)
async def list_conversations(
    user_id: str = Depends(get_user_id),
):
    """
    获取用户的聊天列表（私聊 + 群聊）。

    返回：
    - 私聊列表：该用户参与的所有 1v1 对话
    - 群聊：该用户所在家庭组的群聊（如果存在）
    """
    async with AsyncSessionLocal() as session:
        items: list[ConversationItem] = []

        # ── 1. 私聊列表 ──
        private_result = await session.execute(
            select(Conversation).where(
                Conversation.type == "private",
                or_(
                    Conversation.sender_id == user_id,
                    Conversation.receiver_id == user_id,
                ),
            ).order_by(Conversation.created_at.desc())
        )
        private_convs = private_result.scalars().all()

        for conv in private_convs:
            # 确定对方是谁
            peer_id = conv.receiver_id if conv.sender_id == user_id else conv.sender_id
            peer_nick = await get_nickname(session, peer_id)

            # 最后一条消息
            last_msg = await _get_last_message(session, conv.id)

            items.append(ConversationItem(
                id=conv.id,
                type="private",
                title=conv.title,
                last_message=last_msg["content"] if last_msg else None,
                last_time=last_msg["created_at"] if last_msg else conv.created_at,
                peer_user_id=peer_id,
                peer_nickname=peer_nick,
            ))

        # ── 2. 群聊 ──
        fid = await resolve_family_id(user_id)
        if fid:
            group_result = await session.execute(
                select(Conversation).where(
                    Conversation.type == "group",
                    Conversation.sender_id == fid,
                ).order_by(Conversation.created_at.desc()).limit(1)
            )
            group_conv = group_result.scalar_one_or_none()

            if group_conv:
                # 统计成员数
                count_result = await session.execute(
                    select(func.count()).select_from(FamilyMembership).where(
                        FamilyMembership.family_id == fid
                    )
                )
                member_count = count_result.scalar() or 0

                last_msg = await _get_last_message(session, group_conv.id)

                items.append(ConversationItem(
                    id=group_conv.id,
                    type="group",
                    title=group_conv.title or "家庭群聊",
                    last_message=last_msg["content"] if last_msg else None,
                    last_time=last_msg["created_at"] if last_msg else group_conv.created_at,
                    member_count=member_count,
                ))

        return ConversationListResponse(conversations=items)


async def _get_last_message(session: AsyncSession, conv_id: int) -> dict | None:
    """获取会话的最后一条消息"""
    result = await session.execute(
        select(ChatMessage)
        .where(ChatMessage.conversation_id == conv_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(1)
    )
    msg = result.scalar_one_or_none()
    if msg:
        return {"content": msg.content, "created_at": msg.created_at}
    return None
