"""
自定义音色的数据库表结构
"""
from sqlalchemy import Column, Integer, String, DateTime, func
from app.db.session import Base


class CustomVoice(Base):
    __tablename__ = "custom_voices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True,
                  comment="用户自定义的音色名称")
    vcn = Column(String(200), nullable=False, comment="vivo 返回的音色 ID")
    voice_type = Column(String(50), nullable=True, comment="音色类型描述")
    status = Column(Integer, default=1,
                    comment="状态:1-等待, 2-提取中, 3-完成, 4-失败")
    created_at = Column(DateTime, server_default=func.now())
