"""
定义"经验卡片"的数据库表结构 (ORM 映射) 以及 Conversation, ChatMessage
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, func
from sqlalchemy.orm import relationship
from app.db.session import Base


class Conversation(Base):
    """对话会话"""
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(200), nullable=True, comment="会话标题（取第一条消息前50字）")
    user_id = Column(String(36), nullable=True, default="1", comment="所属用户 ID")
    family_id = Column(String(8), default="1", comment="关联 family_groups.id")
    # 聊天室扩展字段（家庭组成员互聊，与 AI 对话解耦）
    type = Column(String(20), default="ai", comment="会话类型: ai(默认)/private(私聊)/group(群聊)")
    sender_id = Column(String(36), nullable=True, comment="私聊发起者 user_id")
    receiver_id = Column(String(36), nullable=True, comment="私聊接收者 user_id")
    is_favorited = Column(Boolean, default=False, comment="整个会话是否被收藏")
    created_at = Column(DateTime, server_default=func.now())

    messages = relationship(
        "ChatMessage",
        back_populates="conversation",
        order_by="ChatMessage.created_at"
    )


class ChatMessage(Base):
    """聊天消息"""
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False)
    role = Column(String(36), nullable=False, comment="user/assistant 或聊天室 sender_id")
    content = Column(Text, nullable=False)
    is_favorited = Column(Boolean, default=False, comment="单条消息是否被收藏")
    created_at = Column(DateTime, server_default=func.now())

    conversation = relationship("Conversation", back_populates="messages")


class Card(Base):
    """
    传承笔记 —— 精简为文件夹+笔记的备忘录模式
    只保留：id / title / content(Markdown) / author / folder_id / family_id / created_at / updated_at
    """
    __tablename__ = "cards"

    id = Column(Integer, primary_key=True, autoincrement=True)

    title = Column(String(200), nullable=True, comment="笔记标题")
    content = Column(Text, nullable=True, comment="笔记正文（Markdown）")
    author = Column(String(100), nullable=True, comment="作者/讲述人")

    # 文件夹归属
    folder_id = Column(Integer, ForeignKey("folders.id"), nullable=True, comment="所属文件夹")

    # 通用
    family_id = Column(String(8), default="1", comment="关联 family_groups.id")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # 关系
    folder = relationship("Folder", foreign_keys=[folder_id])

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "author": self.author,
            "folder_id": self.folder_id,
            "family_id": self.family_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
