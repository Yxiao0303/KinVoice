"""
用户档案接口 —— 每个用户只有一份自己的档案

GET    /profiles/mine      — 获取当前用户的档案（不存在返回空）
POST   /profiles            — 创建当前用户的档案
PUT    /profiles/{id}       — 更新档案（仅限自己的）
DELETE /profiles/{id}       — 删除档案（仅限自己的）
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_session
from app.models.profile import FamilyMember
from app.schemas.profile import ProfileCreate, ProfileUpdate, ProfileOut, ProfileListOut
from app.middleware.user_identity import get_user_id
from app.utils.logger import logger

router = APIRouter(prefix="/profiles", tags=["用户档案"])


@router.get("/mine", response_model=ProfileOut | dict)
async def get_my_profile(
    user_id: str = Depends(get_user_id),
    session: AsyncSession = Depends(get_session),
):
    """获取当前用户的档案。不存在则返回空对象。"""
    stmt = select(FamilyMember).where(FamilyMember.user_id == user_id)
    result = await session.execute(stmt)
    member = result.scalar_one_or_none()

    if not member:
        # 返回空对象，前端据此判断是否需要创建
        return {"id": 0, "user_id": user_id, "name": "", "relation": "本人",
                "birth_date": None, "avatar_url": None, "content_md": "",
                "created_at": None, "updated_at": None}

    return ProfileOut.model_validate(member)


@router.post("", response_model=ProfileOut, status_code=201)
async def create_profile(
    data: ProfileCreate,
    user_id: str = Depends(get_user_id),
    session: AsyncSession = Depends(get_session),
):
    """创建当前用户的档案。每个用户只能有一份，重复创建会报错。"""
    # 检查是否已存在
    stmt = select(FamilyMember).where(FamilyMember.user_id == user_id)
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="你已经创建过档案了，请使用更新接口")

    member = FamilyMember(user_id=user_id, **data.model_dump())
    session.add(member)
    await session.flush()
    await session.refresh(member)
    logger.info(f"创建档案: id={member.id}, user_id={user_id}, name={member.name}")
    return ProfileOut.model_validate(member)


@router.put("/{profile_id}", response_model=ProfileOut)
async def update_profile(
    profile_id: int,
    data: ProfileUpdate,
    user_id: str = Depends(get_user_id),
    session: AsyncSession = Depends(get_session),
):
    """更新当前用户的档案（只能更新自己的）"""
    result = await session.execute(
        select(FamilyMember).where(FamilyMember.id == profile_id)
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="档案不存在")
    if member.user_id != user_id:
        raise HTTPException(status_code=403, detail="只能编辑自己的档案")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(member, key, value)

    await session.flush()
    await session.refresh(member)
    logger.info(f"更新档案: id={profile_id}, user_id={user_id}, name={member.name}")
    return ProfileOut.model_validate(member)


@router.delete("/{profile_id}", status_code=204)
async def delete_profile(
    profile_id: int,
    user_id: str = Depends(get_user_id),
    session: AsyncSession = Depends(get_session),
):
    """删除当前用户的档案（只能删除自己的）"""
    result = await session.execute(
        select(FamilyMember).where(FamilyMember.id == profile_id)
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="档案不存在")
    if member.user_id != user_id:
        raise HTTPException(status_code=403, detail="只能删除自己的档案")

    await session.delete(member)
    logger.info(f"删除档案: id={profile_id}, user_id={user_id}")
