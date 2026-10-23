"""
音色克隆服务 —— vivo 声音复刻接口
"""

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.voice import CustomVoice
from app.services.replica_service import (
    create_vcn_task,
    get_vcn_status,
    list_vcn_tasks,
    delete_vcn,
    convert_audio_to_standard
)
from app.utils.logger import logger

router = APIRouter(prefix="/replica", tags=["音色克隆"])

@router.get("/sample-texts")
async def get_sample_texts():
    """获取推荐的录音样例文本，用于引导朗读"""
    samples = [
        "我会一直陪着你，无论开心还是难过，我都会在你身边。",
        "今天的天气真好，我们一起去公园散散步吧。",
        "你知道吗，你笑起来的样子特别好看。",
        "谢谢你一直以来的理解和支持，我很感激。",
    ]
    return {"samples": samples}


@router.post("/create")
async def create_replica(
    audio: UploadFile = File(..., description="wav 录音(24kHz, 16bit, 单通道)"),
    text: str = Form(..., description="录音对应文本"),
):
    """上传录音创建自定义音色，自动存入数据库"""
    if not audio.filename or not audio.filename.endswith(".wav"):
        raise HTTPException(400, "只支持 wav 格式音频")

    audio_bytes = await audio.read()
    try:
        # 统一转换为标准格式
        audio_bytes = convert_audio_to_standard(audio_bytes)
        result = await create_vcn_task(audio_bytes, text)
        vcn = result.get("vcn")
        if vcn:
            async with AsyncSessionLocal() as session:
                voice = CustomVoice(
                    name=f"自定义_{vcn[:8]}",
                    vcn=vcn,
                    status=1,   # 等待中
                )
                session.add(voice)
                await session.commit()
        return result
    except RuntimeError as e:
            raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"音色创建失败: {str(e)}")
        raise HTTPException(500, str(e))


@router.get("/status")
async def check_status(vcn: str):
    """查询音色生成状态"""
    try:
        result = await get_vcn_status(vcn)
        return result
    except Exception as e:
        logger.error(f"查询状态失败: {str(e)}")
        raise HTTPException(500, str(e))


@router.get("/list")
async def list_voices():
    """获取 vivo 侧所有音色列表"""
    try:
        vcn_list = await list_vcn_tasks()
        return {"count": len(vcn_list), "items": vcn_list}
    except Exception as e:
        logger.error(f"获取列表失败: {str(e)}")
        raise HTTPException(500, str(e))


@router.delete("/{vcn}")
async def remove_voice(vcn: str):
    """删除指定音色（同时删除本地数据库记录）"""
    try:
        result = await delete_vcn(vcn)
        # 同步删除数据库记录
        async with AsyncSessionLocal() as session:
            db_voice = await session.execute(
                select(CustomVoice).where(CustomVoice.vcn == vcn)
            )
            voice = db_voice.scalar_one_or_none()
            if voice:
                await session.delete(voice)
                await session.commit()
        return result
    except Exception as e:
        logger.error(f"删除音色失败: {str(e)}")
        raise HTTPException(500, str(e))


@router.put("/rename")
async def rename_voice(vcn: str, new_name: str):
    """重命名自定义音色( 之后可用新名字直接 TTS )"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(CustomVoice).where(CustomVoice.vcn == vcn)
        )
        voice = result.scalar_one_or_none()
        if not voice:
            raise HTTPException(404, "音色不存在")
        voice.name = new_name
        await session.commit()
        return {"message": "重命名成功", "name": new_name}


@router.post("/sync-status")
async def sync_voice_status(vcn: str):
    """手动同步音色状态（将 vivo 状态更新到数据库）"""
    try:
        vivo_status = await get_vcn_status(vcn)
        status = vivo_status.get("vcn_obj", {}).get("status", 1)
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(CustomVoice).where(CustomVoice.vcn == vcn)
            )
            voice = result.scalar_one_or_none()
            if voice:
                voice.status = status
                await session.commit()
                return {"vcn": vcn, "status": status, "ready": status == 3}
        raise HTTPException(404, "本地未找到该音色")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"同步状态失败: {str(e)}")
        raise HTTPException(500, str(e))
