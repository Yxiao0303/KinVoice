"""
传承笔记 + 文件夹 —— 请求/响应模型（精简版）
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════
# 文件夹
# ═══════════════════════════════════════════════════

class FolderCreate(BaseModel):
    """创建文件夹"""
    name: str = Field(..., min_length=1, max_length=50, description="文件夹名称")

class FolderOut(BaseModel):
    """文件夹响应"""
    id: int
    name: str
    family_id: str = "1"
    note_count: int = 0
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}

class FolderListOut(BaseModel):
    """文件夹列表"""
    folders: list[FolderOut]

# ═══════════════════════════════════════════════════
# 笔记
# ═══════════════════════════════════════════════════

class CardCreate(BaseModel):
    """创建笔记"""
    title: str = Field(default="", max_length=200, description="标题")
    content: str = Field(default="", description="正文（Markdown）")
    author: str = Field(default="我", max_length=100, description="作者/讲述人")
    folder_id: Optional[int] = Field(None, description="所属文件夹 ID")


class CardUpdate(BaseModel):
    """更新笔记（全字段可选）"""
    title: Optional[str] = Field(None, max_length=200)
    content: Optional[str] = None
    author: Optional[str] = Field(None, max_length=100)
    folder_id: Optional[int] = None


class CardOut(BaseModel):
    """笔记响应"""
    id: int
    title: Optional[str] = None
    content: Optional[str] = None
    author: Optional[str] = None
    folder_id: Optional[int] = None
    family_id: str = "1"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class CardListOut(BaseModel):
    """笔记列表响应"""
    cards: list[CardOut]
    total: int


class DeleteResponse(BaseModel):
    """删除响应"""
    success: bool
