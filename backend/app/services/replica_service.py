"""
音色克隆服务 —— vivo 声音复刻接口
"""
import httpx
from app.config import settings
from app.utils.logger import logger

BASE_URL = "https://api-ai.vivo.com.cn"


async def create_vcn_task(audio_bytes: bytes, text: str) -> dict:
    """上传录音，创建音色生成任务"""
    url = f"{BASE_URL}/replica/create_vcn_task"
    headers = {
        "Authorization": f"Bearer {settings.tts_app_key}",
        "X-AI-GATEWAY-SIGNATURE": "developers-aigc",
    }
    params = {"req_id": settings.tts_app_id}
    files = {"audio": ("recording.wav", audio_bytes, "audio/wav")}
    data = {"text": text}

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, headers=headers, params=params,
                                 files=files, data=data)
        resp.raise_for_status()
        result = resp.json()
        if result.get("error_code") != 0:
            raise RuntimeError(f"创建任务失败: {result}")
        return result


async def get_vcn_status(vcn: str) -> dict:
    """查询音色生成状态"""
    url = f"{BASE_URL}/replica/get_vcn_task"
    headers = {
        "Authorization": f"Bearer {settings.tts_app_key}",
        "X-AI-GATEWAY-SIGNATURE": "developers-aigc",
        "Content-Type": "application/json",
    }
    params = {"req_id": settings.tts_app_id}
    body = {"vcn": vcn}

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, headers=headers, params=params, json=body)
        resp.raise_for_status()
        result = resp.json()
        if result.get("error_code") != 0:
            raise RuntimeError(f"查询音色失败: {result}")
        return result


async def list_vcn_tasks() -> list:
    """获取用户所有音色列表"""
    url = f"{BASE_URL}/replica/get_vcn_task_list"
    headers = {
        "Authorization": f"Bearer {settings.tts_app_key}",
        "X-AI-GATEWAY-SIGNATURE": "developers-aigc",
    }
    params = {"req_id": settings.tts_app_id}

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, headers=headers, params=params)
        resp.raise_for_status()
        result = resp.json()
        if result.get("error_code") != 0:
            raise RuntimeError(f"获取列表失败: {result}")
        return result.get("vcn_obj_list", [])


async def delete_vcn(vcn: str) -> dict:
    """删除指定音色"""
    url = f"{BASE_URL}/replica/del_task"
    headers = {
        "Authorization": f"Bearer {settings.tts_app_key}",
        "X-AI-GATEWAY-SIGNATURE": "developers-aigc",
        "Content-Type": "application/json",
    }
    params = {"req_id": settings.tts_app_id}
    body = {"vcn": vcn}

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, headers=headers, params=params, json=body)
        resp.raise_for_status()
        result = resp.json()
        if result.get("error_code") != 0:
            raise RuntimeError(f"删除音色失败: {result}")
        return result


def convert_audio_to_standard(audio_bytes: bytes) -> bytes:
    """
    将任意 WAV 转为 vivo 要求的标准格式：
    24kHz, 16bit, 单声道
    """
    try:
        from pydub import AudioSegment
        import io
        audio = AudioSegment.from_file(io.BytesIO(audio_bytes), format="wav")
        # 转为标准格式
        audio = audio.set_frame_rate(24000).set_channels(1).set_sample_width(2)
        buf = io.BytesIO()
        audio.export(buf, format="wav")
        buf.seek(0)
        return buf.read()
    except ImportError:
        raise RuntimeError(
            "需要安装 pydub 和 ffmpeg 才能自动转换音频格式。"
            "请执行: pip install pydub 并安装 ffmpeg"
        )
