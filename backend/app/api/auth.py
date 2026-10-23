"""
用户认证 API —— 注册 + 登录

POST /auth/register — 注册新用户
POST /auth/login    — 登录验证
"""
import uuid
from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.family import User
from app.schemas.auth import RegisterRequest, LoginRequest, AuthResponse
from app.utils.password import hash_password, verify_password
from app.utils.logger import logger

router = APIRouter(prefix="/auth", tags=["用户认证"])


@router.post("/register", response_model=AuthResponse)
async def register(req: RegisterRequest):
    """注册新用户"""
    async with AsyncSessionLocal() as session:
        # 检查用户名是否已存在
        result = await session.execute(
            select(User).where(User.username == req.username)
        )
        if result.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="用户名已被注册")

        # 创建用户
        user = User(
            id=str(uuid.uuid4()),
            username=req.username,
            password_hash=hash_password(req.password),
            nickname=req.nickname,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

        logger.info(f"新用户注册: username={req.username}, id={user.id}")
        return AuthResponse(user_id=user.id, nickname=user.nickname, message="注册成功")


@router.post("/login", response_model=AuthResponse)
async def login(req: LoginRequest):
    """用户登录"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(User).where(User.username == req.username)
        )
        user = result.scalar_one_or_none()

        if not user or not user.password_hash:
            raise HTTPException(status_code=401, detail="用户名或密码错误")

        if not verify_password(req.password, user.password_hash):
            raise HTTPException(status_code=401, detail="用户名或密码错误")

        logger.info(f"用户登录: username={req.username}, id={user.id}")
        return AuthResponse(user_id=user.id, nickname=user.nickname, message="登录成功")
