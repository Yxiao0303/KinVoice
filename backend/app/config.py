"""
应用配置管理 —— 从 .env 读取所有环境变量
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env.local",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # 应用基础配置
    APP_NAME: str = "KinVoice"
    # 用 str 类型避免与系统环境变量 DEBUG=release 冲突
    DEBUG: str = "true"

    # CORS 允许的前端地址
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://localhost:5173"

    # 大模型配置
    llm_api_key: str = ""       # 模型接口密钥
    llm_api_base: str = ""      # 模型接口根地址
    llm_model: str = ""         # 模型名称

    # 数据库
    database_url: str = "sqlite+aiosqlite:///./data/kinvoice.db"

    # 日志
    LOG_LEVEL: str = "INFO"

    # vivo TTS
    tts_app_id: str = ""
    tts_app_key: str = ""


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
