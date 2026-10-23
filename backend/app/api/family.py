"""
家庭组 API —— 创建/加入/退出/查询

POST   /family/register-with-id — 注册用户（user_id 通过 X-User-Id Header）
POST   /family/create           — 创建家庭组
POST   /family/join             — 加入家庭组
POST   /family/leave            — 退出家庭组
GET    /family/my-group         — 查询我的家庭组

user_id 传递方式：所有接口统一通过 X-User-Id Header（由前端 ajax.js 自动注入）。
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import AsyncSessionLocal
from app.services.family_service import (
    register_user,
    ensure_user,
    create_group,
    join_group,
    leave_group,
    get_my_group,
)
from app.schemas.family import (
    RegisterResponse,
    CreateGroupResponse,
    MyGroupResponse,
    MemberOut,
    OkResponse,
)
from app.middleware.user_identity import get_user_id
from pydantic import BaseModel, Field
from app.utils.logger import logger

router = APIRouter(prefix="/family", tags=["家庭组"])


# ── 请求模型（user_id 统一从 X-User-Id Header 获取） ──

class RegisterWithIdRequest(BaseModel):
    nickname: str = Field(..., min_length=1, max_length=50)


class CreateGroupRequest(BaseModel):
    nickname: str = Field(..., min_length=1, max_length=50)


class JoinGroupRequest(BaseModel):
    family_id: str = Field(..., min_length=8, max_length=8)
    password: str = Field(..., min_length=6, max_length=6)
    nickname: str = Field(..., min_length=1, max_length=50)


# ── POST /family/register-with-id ──

@router.post("/register-with-id", response_model=RegisterResponse)
async def api_register_with_id(
    req: RegisterWithIdRequest,
    user_id: str = Depends(get_user_id),
):
    """注册用户（前端设置昵称，user_id 通过 X-User-Id Header 传入）"""
    async with AsyncSessionLocal() as session:
        user = await register_user(session, user_id, req.nickname)
        await session.commit()
        return RegisterResponse(user_id=user.id, nickname=user.nickname)


# ── POST /family/create ──

@router.post("/create", response_model=CreateGroupResponse)
async def api_create_group(
    req: CreateGroupRequest,
    user_id: str = Depends(get_user_id),
):
    """创建家庭组。创建者自动加入。"""
    async with AsyncSessionLocal() as session:
        try:
            await ensure_user(session, user_id, req.nickname)
            fid, pwd = await create_group(session, user_id)
            await session.commit()
            return CreateGroupResponse(family_id=fid, password=pwd, user_id=user_id)
        except ValueError as e:
            await session.rollback()
            raise HTTPException(status_code=400, detail=str(e))


# ── POST /family/join ──

@router.post("/join", response_model=OkResponse)
async def api_join_group(
    req: JoinGroupRequest,
    user_id: str = Depends(get_user_id),
):
    """加入家庭组。输入 8 位 ID + 6 位密码。"""
    async with AsyncSessionLocal() as session:
        try:
            await ensure_user(session, user_id, req.nickname)
            await join_group(session, user_id, req.family_id, req.password)
            await session.commit()
            return OkResponse()
        except ValueError as e:
            await session.rollback()
            raise HTTPException(status_code=400, detail=str(e))


# ── POST /family/leave ──

@router.post("/leave", response_model=OkResponse)
async def api_leave_group(
    user_id: str = Depends(get_user_id),
):
    """退出当前家庭组"""
    async with AsyncSessionLocal() as session:
        fid = await leave_group(session, user_id)
        await session.commit()
        if fid:
            logger.info(f"用户 {user_id} 已退出家庭组 {fid}")
        return OkResponse()


# ── GET /family/my-group ──

@router.get("/my-group", response_model=MyGroupResponse)
async def api_get_my_group(
    user_id: str = Depends(get_user_id),
):
    """查询当前用户所在的家庭组信息"""
    async with AsyncSessionLocal() as session:
        data = await get_my_group(session, user_id)
        return MyGroupResponse(
            family_id=data["family_id"],
            password=data["password"],
            members=[MemberOut(**m) for m in data["members"]],
        )
