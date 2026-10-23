"""
AI 卡片提取 —— 请求/响应模型
"""
from pydantic import BaseModel, Field


class MessageItem(BaseModel):
    """单条对话消息"""
    role: str = Field(description="user 或 assistant")
    content: str = Field(description="消息内容")


class CardsExtractRequest(BaseModel):
    """从对话中提取卡片的请求"""
    user_id: str = Field(default="default", description="用户标识")
    family_id: str = Field(default="1", description="家庭组 ID")
    messages: list[MessageItem] = Field(default_factory=list, description="对话消息列表")


class CardCreated(BaseModel):
    """已创建的卡片简要信息"""
    id: int
    title: str


class CardsExtractResponse(BaseModel):
    """卡片提取响应"""
    ok: bool
    cards_created: list[CardCreated] = Field(default_factory=list)
    total_created: int = 0
    message: str = ""
