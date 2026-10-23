"""
TTS 文本转语音服务 —— vivo WebSocket + 自定义音色支持
"""
import base64
import io
import json
import time
import uuid
import wave
from websocket import create_connection, ABNF
from app.config import settings
from app.utils.logger import logger

# 系统音色（vivo 短音频）
VOICES = {
    "vivoHelper": "奕雯",
    "yunye": "云野-温柔",
    "wanqing": "婉清-御姐",
    "xiaofu": "晓芙-少女",
    "yige_child": "小萌-女童",
    "yige": "依格",
    "yiyi": "依依",
    "xiaoming": "小茗",
}
DEFAULT_VOICE = "yunye"   # 默认温柔音色
ENGINE_ID = "short_audio_synthesis_jovi"


def _build_ws_url() -> str:
    """构造 WebSocket URL 参数"""
    now = str(int(time.time()))
    params = {
        "engineid": ENGINE_ID,
        "system_time": now,
        "user_id": "user_" + settings.tts_app_id,
        "model": "unknown",
        "product": "unknown",
        "package": "unknown",
        "client_version": "1.0.0",
        "system_version": "unknown",
        "sdk_version": "1.0.0",
        "android_version": "9",
        "requestId": str(uuid.uuid4()),
    }
    return "/tts?" + "&".join(f"{k}={v}" for k, v in params.items())


def _pcm2wav(pcm_data: bytes, sample_rate=24000, channels=1, bits=16) -> io.BytesIO:
    """PCM 转 WAV"""
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(bits // 8)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_data)
    buf.seek(0)
    return buf


async def text_to_pcm(text: str, voice: str = DEFAULT_VOICE,
                      speed: int = 50, volume: int = 40) -> bytes:
    """
    核心合成：连接 vivo WebSocket,返回 PCM 音频
    自动识别自定义音色(从数据库查找 vcn)
    """
    if not text or not text.strip():
        raise ValueError("文本不能为空")

    # 如果是自定义音色，从数据库获取真实 vcn
    final_voice = voice
    if voice not in VOICES:
        from sqlalchemy import select
        from app.db.session import AsyncSessionLocal
        from app.models.voice import CustomVoice

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(CustomVoice).where(
                    CustomVoice.name == voice,
                    CustomVoice.status == 3   # 仅已完成
                )
            )
            custom = result.scalar_one_or_none()
            if not custom:
                raise ValueError(f"音色 '{voice}' 不存在或尚未完成")
            final_voice = custom.vcn

    # 鉴权
    if not settings.tts_app_key or "your" in settings.tts_app_key.lower():
        raise RuntimeError("TTS AppKey 未配置")

    # WebSocket 连接
    ws_url = "wss://api-ai.vivo.com.cn" + _build_ws_url()
    headers = {
        "Authorization": f"Bearer {settings.tts_app_key}",
        "X-AI-GATEWAY-SIGNATURE": "developers-aigc",
    }
    logger.info(f"TTS 连接: {ws_url}")
    ws = create_connection(ws_url, header=headers, timeout=30)

    # 握手
    code, data = ws.recv_data(True)
    handshake = json.loads(data)
    if handshake.get("error_code") != 0:
        ws.close()
        raise RuntimeError(f"WebSocket 握手失败: {handshake}")
    logger.info("TTS 握手成功")

    # 发送合成请求
    req = {
        "aue": 0,
        "auf": "audio/L16;rate=24000",
        "vcn": final_voice,
        "speed": speed,
        "volume": volume,
        "text": base64.b64encode(text.encode("utf-8")).decode("utf-8"),
        "encoding": "utf8",
        "reqId": int(round(time.time() * 1000)),
    }
    ws.send(json.dumps(req))
    logger.info(f"发送合成请求，文本长度: {len(text)}")

    # 接收音频
    audio_buff = b''
    while True:
        code, data = ws.recv_data(True)
        if code == ABNF.OPCODE_CLOSE:
            break
        elif code == ABNF.OPCODE_TEXT:
            msg = json.loads(data)
            if msg.get("error_code") != 0:
                ws.close()
                raise RuntimeError(f"合成错误: {msg}")
            audio_data = msg.get("data", {})
            if "audio" in audio_data:
                audio_buff += base64.b64decode(audio_data["audio"])
            if audio_data.get("status") == 2:
                break
        else:
            break

    ws.close()
    if not audio_buff:
        raise RuntimeError("未收到音频数据")
    logger.info(f"TTS 合成成功，{len(audio_buff)} 字节")
    return audio_buff


async def text_to_speech(text: str, voice: str = DEFAULT_VOICE,
                         speed: int = 50, volume: int = 40) -> bytes:
    """文本 → WAV 音频字节"""
    pcm = await text_to_pcm(text, voice, speed, volume)
    return _pcm2wav(pcm).read()


async def text_to_base64(text: str, voice: str = DEFAULT_VOICE,
                         speed: int = 50, volume: int = 40) -> str:
    """文本 → base64 编码的 WAV"""
    wav_bytes = await text_to_speech(text, voice, speed, volume)
    return base64.b64encode(wav_bytes).decode("utf-8")
