"""
传承笔记 API（精简版）—— 文件夹 + Markdown 笔记
文件夹: GET/POST /folders
笔记:   GET/POST/PUT/DELETE /cards
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_session, AsyncSessionLocal
from app.models.card import Card
from app.models.folder import Folder
from app.schemas.memory import (
    FolderCreate, FolderOut, FolderListOut,
    CardCreate, CardUpdate, CardOut, CardListOut, DeleteResponse,
)
from app.middleware.user_identity import get_user_id
from app.services.family_service import get_user_family_id
from app.utils.logger import logger

router = APIRouter(tags=["传承笔记"])


# ── 辅助 ─────────────────────────────────────────────

async def resolve_family_id(user_id: str) -> str:
    async with AsyncSessionLocal() as session:
        fid = await get_user_family_id(session, user_id)
        return fid if fid is not None else "1"


# ═══════════════════════════════════════════════════
#  文件夹 CRUD
# ═══════════════════════════════════════════════════

@router.get("/folders", response_model=FolderListOut)
async def list_folders(
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_user_id),
):
    """获取当前家庭组的所有文件夹（含笔记计数）"""
    family_id = await resolve_family_id(user_id)

    f_result = await session.execute(
        select(Folder).where(Folder.family_id == family_id).order_by(Folder.created_at.asc())
    )
    folders = f_result.scalars().all()

    out_list = []
    for f in folders:
        cnt_result = await session.execute(
            select(func.count(Card.id)).where(Card.folder_id == f.id, Card.family_id == family_id)
        )
        count = cnt_result.scalar() or 0
        out_list.append(FolderOut(
            id=f.id, name=f.name, family_id=f.family_id,
            note_count=count, created_at=f.created_at,
        ))

    return FolderListOut(folders=out_list)


@router.post("/folders", response_model=FolderOut, status_code=201)
async def create_folder(
    data: FolderCreate,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_user_id),
):
    """创建新文件夹"""
    family_id = await resolve_family_id(user_id)
    folder = Folder(name=data.name, family_id=family_id)
    session.add(folder)
    await session.flush()
    await session.refresh(folder)
    logger.info(f"创建文件夹: id={folder.id} name={folder.name}")
    return FolderOut(id=folder.id, name=folder.name, family_id=family_id, note_count=0)


# ═══════════════════════════════════════════════════
#  笔记 CRUD
# ═══════════════════════════════════════════════════

@router.get("/cards", response_model=CardListOut)
async def list_cards(
    folder_id: int | None = Query(None, description="按文件夹筛选，不传则返回全部"),
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_user_id),
):
    """获取笔记列表（按 family_id 隔离，可选按文件夹筛选）"""
    family_id = await resolve_family_id(user_id)

    stmt = select(Card).where(Card.family_id == family_id)
    count_stmt = select(func.count(Card.id)).where(Card.family_id == family_id)

    if folder_id is not None:
        if folder_id == 0:
            stmt = stmt.where(Card.folder_id.is_(None))
            count_stmt = count_stmt.where(Card.folder_id.is_(None))
        else:
            stmt = stmt.where(Card.folder_id == folder_id)
            count_stmt = count_stmt.where(Card.folder_id == folder_id)

    stmt = stmt.order_by(Card.created_at.desc()).offset(offset).limit(limit)

    result = await session.execute(stmt)
    cards = result.scalars().all()

    total_result = await session.execute(count_stmt)
    total = total_result.scalar() or 0

    return CardListOut(
        cards=[CardOut.model_validate(c) for c in cards],
        total=total,
    )


@router.post("/cards", response_model=CardOut, status_code=201)
async def create_card(
    data: CardCreate,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_user_id),
):
    """创建新笔记"""
    family_id = await resolve_family_id(user_id)
    payload = data.model_dump()
    payload["family_id"] = family_id if family_id is not None else "1"

    card = Card(**payload)
    session.add(card)
    await session.flush()
    await session.refresh(card)
    logger.info(f"创建笔记: id={card.id} title={card.title} folder_id={card.folder_id}")
    return CardOut.model_validate(card)


@router.put("/cards/{card_id}", response_model=CardOut)
async def update_card(
    card_id: int,
    data: CardUpdate,
    session: AsyncSession = Depends(get_session),
):
    """更新笔记"""
    result = await session.execute(select(Card).where(Card.id == card_id))
    card = result.scalar_one_or_none()
    if not card:
        raise HTTPException(status_code=404, detail="笔记不存在")

    orm_fields = {c.name for c in Card.__table__.columns}
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        if key in orm_fields:
            setattr(card, key, value)

    await session.flush()
    await session.refresh(card)
    logger.info(f"更新笔记: id={card_id}")
    return CardOut.model_validate(card)


@router.delete("/cards/{card_id}")
async def delete_card(
    card_id: int,
    session: AsyncSession = Depends(get_session),
):
    """删除笔记"""
    result = await session.execute(select(Card).where(Card.id == card_id))
    card = result.scalar_one_or_none()
    if not card:
        raise HTTPException(status_code=404, detail="笔记不存在")
    await session.delete(card)
    await session.flush()
    logger.info(f"删除笔记: id={card_id}")
    return DeleteResponse(success=True)
