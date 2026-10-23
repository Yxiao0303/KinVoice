"""
家庭成员档案 Pydantic Schema（每个用户只有一份自己的档案）
"""
from pydantic import BaseModel, Field
from datetime import datetime


# ── 创建 ──
class ProfileCreate(BaseModel):
    name: str = Field(default="", max_length=100, description="姓名（可选，默认空）")
    relation: str = Field(default="本人", max_length=50, description="关系")
    birth_date: str | None = Field(default=None, max_length=20, description="生日 YYYY-MM-DD")
    avatar_url: str | None = Field(default=None, max_length=500, description="头像链接")
    content_md: str = Field(default="", description="Markdown 正文")


# ── 更新（全可选）──
class ProfileUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    relation: str | None = Field(default=None, max_length=50)
    birth_date: str | None = Field(default=None, max_length=20)
    avatar_url: str | None = Field(default=None, max_length=500)
    content_md: str | None = Field(default=None)


# ── 输出 ──
class ProfileOut(BaseModel):
    id: int
    user_id: str
    name: str
    relation: str
    birth_date: str | None
    avatar_url: str | None
    content_md: str
    created_at: datetime | None
    updated_at: datetime | None

    model_config = {"from_attributes": True}


class ProfileListOut(BaseModel):
    profiles: list[ProfileOut]
    total: int
