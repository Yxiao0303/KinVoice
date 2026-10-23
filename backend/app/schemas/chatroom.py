"""
聊天室（家庭组成员互聊）的 Pydantic 模型

与 /chat（AI 对话）完全解耦，共用 conversations + chat_messages 表，
通过 Conversation.type 字段区分。
"""
from datetime import datetime
from pydantic import BaseModel, Field


# ── 发送消息 ──

class SendMessageRequest(BaseModel):
    """发送消息请求（user_id 通过 X-User-Id Header 传递）"""
    conversation_id: int | None = Field(None, description="已有会话 ID，不传则新建")
    receiver_id: str | None = Field(None, description="私聊接收者 user_id（新建私聊时必传）")
    chat_type: str = Field(default="group", description="会话类型: private / group")
    content: str = Field(..., min_length=1, max_length=2000, description="消息内容")


class SendMessageResponse(BaseModel):
    """发送消息响应"""
    conversation_id: int
    message_id: int
    content: str
    created_at: datetime | None = None


# ── 拉取消息（轮询） ──

class MessageOut(BaseModel):
    """单条消息"""
    id: int
    sender_id: str  # 发送者 user_id
    sender_nickname: str = ""
    content: str
    created_at: datetime | None = None


class MessagesResponse(BaseModel):
    """消息列表响应"""
    conversation_id: int
    messages: list[MessageOut]
    has_more: bool = False


# ── 聊天列表 ──

class ConversationItem(BaseModel):
    """聊天列表项"""
    id: int
    type: str  # private / group
    title: str | None = None
    last_message: str | None = None
    last_time: datetime | None = None
    # 私聊专用
    peer_user_id: str | None = None
    peer_nickname: str | None = None
    # 群聊专用
    member_count: int = 0


class ConversationListResponse(BaseModel):
    """聊天列表响应"""
    conversations: list[ConversationItem]
