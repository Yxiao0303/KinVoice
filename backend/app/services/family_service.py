"""
家庭组业务逻辑 —— 创建/加入/退出/查询

完全独立模块，不依赖 chat/memory/profile 等任何现有模块。
"""
import secrets
import string
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.family import User, FamilyGroup, FamilyMembership
from app.utils.logger import logger


# ── 工具函数 ──

def generate_family_id() -> str:
    """生成 8 位随机字母数字 ID，如 K3X9M2A7"""
    chars = string.ascii_uppercase + string.digits
    # 去掉容易混淆的字符
    chars = chars.replace("O", "").replace("0", "").replace("I", "").replace("1", "")
    return "".join(secrets.choice(chars) for _ in range(8))


def generate_password() -> str:
    """生成 6 位数字密码"""
    return "".join(secrets.choice(string.digits) for _ in range(6))


# ── 用户操作 ──

async def ensure_user(session: AsyncSession, user_id: str, nickname: str) -> User:
    """
    确保用户存在：存在则返回，不存在则创建。

    Args:
        session: 数据库会话
        user_id: 前端生成的 UUID
        nickname: 用户昵称

    Returns:
        User 实例
    """
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user:
        user.nickname = nickname
        return user

    user = User(id=user_id, nickname=nickname)
    session.add(user)
    await session.flush()
    logger.info(f"创建新用户: id={user_id}, nickname={nickname}")
    return user


async def register_user(session: AsyncSession, user_id: str, nickname: str) -> User:
    """注册用户（首次使用）"""
    return await ensure_user(session, user_id, nickname)


# ── 家庭组操作 ──

async def create_group(session: AsyncSession, user_id: str) -> tuple[str, str]:
    """
    创建家庭组，创建者自动加入。

    Args:
        session: 数据库会话
        user_id: 创建者 ID（必须已注册）

    Returns:
        (family_id, password)
    """
    # 检查用户是否已有家庭组（一个用户只能在一个组）
    existing = await session.execute(
        select(FamilyMembership).where(FamilyMembership.user_id == user_id)
    )
    if existing.scalar_one_or_none():
        raise ValueError("你已在一个家庭组中，请先退出再加入新组")

    # 生成唯一 ID（最多重试 10 次）
    for _ in range(10):
        fid = generate_family_id()
        result = await session.execute(select(FamilyGroup).where(FamilyGroup.id == fid))
        if not result.scalar_one_or_none():
            break
    else:
        raise RuntimeError("无法生成唯一家庭组 ID，请重试")

    password = generate_password()

    group = FamilyGroup(id=fid, password=password, created_by=user_id)
    session.add(group)

    membership = FamilyMembership(user_id=user_id, family_id=fid)
    session.add(membership)

    await session.flush()
    logger.info(f"创建家庭组: id={fid}, created_by={user_id}")
    return fid, password


async def join_group(session: AsyncSession, user_id: str, family_id: str, password: str) -> None:
    """
    加入家庭组。

    Args:
        session: 数据库会话
        user_id: 加入者 ID
        family_id: 8位家庭组 ID
        password: 6位密码

    Raises:
        ValueError: 家庭组不存在、密码错误、已在该组中、已在其他组中
    """
    # 查找家庭组
    result = await session.execute(select(FamilyGroup).where(FamilyGroup.id == family_id.upper()))
    group = result.scalar_one_or_none()
    if not group:
        raise ValueError("家庭组不存在，请检查 ID 是否正确")

    if group.password != password:
        raise ValueError("密码错误")

    # 检查是否已在该组
    existing = await session.execute(
        select(FamilyMembership).where(
            FamilyMembership.user_id == user_id,
            FamilyMembership.family_id == family_id.upper(),
        )
    )
    if existing.scalar_one_or_none():
        raise ValueError("你已在此家庭组中")

    # 检查是否已在其他组
    other = await session.execute(
        select(FamilyMembership).where(FamilyMembership.user_id == user_id)
    )
    if other.scalar_one_or_none():
        raise ValueError("你已在另一个家庭组中，请先退出")

    membership = FamilyMembership(user_id=user_id, family_id=family_id.upper())
    session.add(membership)
    await session.flush()
    logger.info(f"用户 {user_id} 加入家庭组 {family_id.upper()}")


async def leave_group(session: AsyncSession, user_id: str) -> str | None:
    """
    退出当前家庭组。

    Returns:
        退出的 family_id，若本就不在任何组则返回 None
    """
    result = await session.execute(
        select(FamilyMembership).where(FamilyMembership.user_id == user_id)
    )
    membership = result.scalar_one_or_none()
    if not membership:
        return None

    fid = membership.family_id
    await session.delete(membership)
    await session.flush()

    # 如果组内没人了，删除家庭组
    remaining = await session.execute(
        select(FamilyMembership).where(FamilyMembership.family_id == fid)
    )
    if not remaining.scalars().all():
        await session.execute(delete(FamilyGroup).where(FamilyGroup.id == fid))
        logger.info(f"家庭组 {fid} 已无成员，自动解散")

    logger.info(f"用户 {user_id} 退出家庭组 {fid}")
    return fid


async def get_my_group(session: AsyncSession, user_id: str) -> dict:
    """
    查询用户当前家庭组信息。

    Returns:
        { family_id, password, members: [{user_id, nickname, joined_at}] }
        若未加入任何组，返回 { family_id: None, password: None, members: [] }
    """
    # 查用户的成员关系
    result = await session.execute(
        select(FamilyMembership).where(FamilyMembership.user_id == user_id)
    )
    membership = result.scalar_one_or_none()
    if not membership:
        return {"family_id": None, "password": None, "members": []}

    fid = membership.family_id

    # 查家庭组信息
    result = await session.execute(select(FamilyGroup).where(FamilyGroup.id == fid))
    group = result.scalar_one_or_none()

    # 查所有成员
    result = await session.execute(
        select(FamilyMembership, User.nickname)
        .join(User, FamilyMembership.user_id == User.id)
        .where(FamilyMembership.family_id == fid)
    )
    rows = result.all()

    members = [
        {
            "user_id": row.FamilyMembership.user_id,
            "nickname": row.nickname,
            "joined_at": row.FamilyMembership.joined_at,
        }
        for row in rows
    ]

    return {
        "family_id": fid,
        "password": group.password if group else None,
        "members": members,
    }


async def get_user_family_id(session: AsyncSession, user_id: str) -> str | None:
    """
    查询用户的 family_id（供其他模块调用）。

    特殊处理：user_id="1" 返回 "1"（兼容现有数据）。
    """
    if user_id == "1":
        return "1"

    result = await session.execute(
        select(FamilyMembership.family_id).where(FamilyMembership.user_id == user_id)
    )
    fid = result.scalar_one_or_none()
    return fid  # str | None
