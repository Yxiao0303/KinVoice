"""
TTS 接口 —— 文本转语音（支持系统音色和自定义音色）
"""
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from app.services.tts_service import text_to_speech, VOICES, DEFAULT_VOICE
from app.utils.logger import logger

router = APIRouter(prefix="/tts", tags=["语音合成"])


@router.post("")
async def tts_endpoint(
    text: str = Query(..., min_length=1, description="要合成的文本"),
    voice: str = Query(DEFAULT_VOICE, description="发音人名称（系统或自定义）"),
    speed: int = Query(43, ge=0, le=100, description="语速"),
    volume: int = Query(50, ge=1, le=100, description="音量"),
):
    """
    文本 → WAV 音频
    可直接使用自定义音色的命名（如"我的温柔女友"）调用
    """
    # voice 存在性检查（含自定义音色）将交由 service/tts_service.py 内部处理
    try:
        audio_bytes = await text_to_speech(text, voice, speed, volume)
        return Response(
            content=audio_bytes,
            media_type="audio/wav",
            headers={"Content-Disposition": f"attachment; filename=tts_{voice}.wav"},
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        logger.error(f"TTS 运行错误: {str(e)}")
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        logger.error(f"TTS 未知错误: {str(e)}")
        raise HTTPException(status_code=500, detail="语音生成失败")


@router.get("/voices")
async def list_voices():
    """获取所有可用音色（系统 + 已完成的自定义音色）"""
    from sqlalchemy import select
    from app.db.session import AsyncSessionLocal
    from app.models.voice import CustomVoice

    system_voices = [{"type": "system", "code": k, "name": v} for k, v in VOICES.items()]

    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(CustomVoice).where(CustomVoice.status == 3)
            )
            custom_voices = [
                {"type": "custom", "code": v.name, "name": v.name, "status": v.status}
                for v in result.scalars()
            ]
        return system_voices + custom_voices
    except Exception:
        return system_voices
