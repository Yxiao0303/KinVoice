"""
AI 档案编写 —— 请求/响应模型
"""
from pydantic import BaseModel, Field


# ── 从对话提取 ──

class MessageItem(BaseModel):
    """单条对话消息"""
    role: str = Field(description="user 或 assistant")
    content: str = Field(description="消息内容")


class ProfileExtractRequest(BaseModel):
    """从对话中提取档案的请求"""
    user_id: str = Field(default="default", description="用户标识")
    profile_type: str = Field(default="dynamic", description="stable 或 dynamic")
    messages: list[MessageItem] = Field(default_factory=list, description="对话消息列表")


class ProfileExtractResponse(BaseModel):
    """档案提取响应"""
    ok: bool
    profile_type: str = Field(description="stable 或 dynamic")
    path: str = Field(description="写入的文件路径")
    content_preview: str = Field(default="", description="新内容前 200 字预览")
    messages_used: int = Field(default=0, description="用于提取的消息条数")


# ── 读取 ──

class ProfileReadResponse(BaseModel):
    """读取档案响应"""
    user_id: str
    stable: str = Field(default="", description="固定档案 Markdown 内容")
    dynamic: str = Field(default="", description="动态档案 Markdown 内容")
