"""
用户认证 —— 请求/响应 Pydantic 模型
"""
from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    """注册请求"""
    username: str = Field(..., min_length=2, max_length=50, description="用户名")
    password: str = Field(..., min_length=4, max_length=100, description="密码")
    nickname: str = Field(..., min_length=1, max_length=50, description="昵称")


class LoginRequest(BaseModel):
    """登录请求"""
    username: str = Field(..., min_length=1, max_length=50, description="用户名")
    password: str = Field(..., min_length=1, max_length=100, description="密码")


class AuthResponse(BaseModel):
    """认证成功响应"""
    user_id: str
    nickname: str
    message: str = "ok"
