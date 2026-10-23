"""
Chat 接口的 Pydantic 模型 —— 数据校验
兼容 si 旧字段 + xia 新字段
"""
from datetime import datetime
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """对话请求"""
    message: str = Field(..., min_length=1, max_length=2000, description="用户消息（1-2000 字符）")
    conversation_id: int | None = Field(None, description="会话 ID, 不传则新建会话")
    # 家庭组 ID（用于检索卡片等家庭数据）
    family_id: str | None = Field(None, description="家庭组 ID，用于检索家庭卡片和对话历史")


class ChatResponse(BaseModel):
    """对话响应"""
    reply: str = Field(..., description="AI 回复")
    conversation_id: int | None = None
    message_id: int | None = None
    tokens_used: int = 0


# ── 历史记录 / 会话管理 ──

class ConversationOut(BaseModel):
    """会话列表项"""
    id: int
    title: str | None = None
    created_at: datetime | None = None

    class Config:
        from_attributes = True


class ConversationListOut(BaseModel):
    """会话列表响应"""
    conversations: list[ConversationOut]


class MessageOut(BaseModel):
    """单条消息"""
    id: int
    role: str
    content: str
    created_at: datetime | None = None

    class Config:
        from_attributes = True


class HistoryOut(BaseModel):
    """历史消息响应"""
    conversation_id: int
    messages: list[MessageOut]
