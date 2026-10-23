"""
文件夹模型 —— 用户自定义笔记文件夹
"""
from sqlalchemy import Column, Integer, String, DateTime, func
from app.db.session import Base


class Folder(Base):
    """笔记文件夹，用户可自由创建"""
    __tablename__ = "folders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False, comment="文件夹名称")
    family_id = Column(String(8), default="1", comment="关联 family_groups.id")
    created_at = Column(DateTime, server_default=func.now())
