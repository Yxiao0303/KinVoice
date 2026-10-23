"""
家庭组 —— 请求/响应 Pydantic 模型
"""
from datetime import datetime
from pydantic import BaseModel, Field


# ── 请求模型 ──

class RegisterRequest(BaseModel):
    """首次注册用户"""
    nickname: str = Field(..., min_length=1, max_length=50, description="用户昵称")


class CreateGroupRequest(BaseModel):
    """创建家庭组"""
    nickname: str = Field(..., min_length=1, max_length=50, description="创建者昵称（若用户不存在则自动注册）")


class JoinGroupRequest(BaseModel):
    """加入家庭组"""
    family_id: str = Field(..., min_length=8, max_length=8, description="8位家庭组ID")
    password: str = Field(..., min_length=6, max_length=6, description="6位数字密码")
    nickname: str = Field(..., min_length=1, max_length=50, description="加入者昵称（若用户不存在则自动注册）")


# ── 响应模型 ──

class RegisterResponse(BaseModel):
    """注册响应"""
    user_id: str
    nickname: str


class CreateGroupResponse(BaseModel):
    """创建家庭组响应"""
    family_id: str
    password: str
    user_id: str


class MemberOut(BaseModel):
    """组成员信息"""
    user_id: str
    nickname: str
    joined_at: datetime | None = None


class MyGroupResponse(BaseModel):
    """查询我的家庭组"""
    family_id: str | None = None
    password: str | None = None
    members: list[MemberOut] = []


class OkResponse(BaseModel):
    """通用成功响应"""
    ok: bool = True
