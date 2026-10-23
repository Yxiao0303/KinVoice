"""
家庭组 ORM 模型 —— 用户 + 家庭组 + 组成员关系

三张独立表，与现有 cards/conversations/chat_messages 完全解耦。

表关系：
  users ──< family_memberships >── family_groups

注意：现有 family_members 表是"家庭成员档案"（父亲/母亲的名字生日），
      这里的 family_memberships 是"家庭组成员关系"，两个不同概念。
"""
from sqlalchemy import Column, String, DateTime, ForeignKey, func
from app.db.session import Base


class User(Base):
    """用户表 —— 支持账号密码登录，同时兼容设备 UUID 注册"""
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, comment="UUID，注册时服务端生成或前端传入")
    username = Column(String(50), unique=True, nullable=True, comment="登录用户名（唯一，设备注册时可为空）")
    password_hash = Column(String(128), nullable=True, comment="PBKDF2-SHA256 密码哈希（设备注册时可为空）")
    nickname = Column(String(50), nullable=False, default="", comment="用户昵称")
    created_at = Column(DateTime, server_default=func.now())

    def __repr__(self):
        return f"<User(id='{self.id}', nickname='{self.nickname}')>"


class FamilyGroup(Base):
    """家庭组表 —— 8位ID + 6位密码"""
    __tablename__ = "family_groups"

    id = Column(String(8), primary_key=True, comment="8位随机字母数字，如 K3X9M2A7")
    password = Column(String(6), nullable=False, comment="6位数字密码")
    created_by = Column(String(36), nullable=False, comment="创建者 user_id")
    created_at = Column(DateTime, server_default=func.now())

    def __repr__(self):
        return f"<FamilyGroup(id='{self.id}')>"


class FamilyMembership(Base):
    """家庭成员关系表 —— 用户与家庭组的多对一关联"""
    __tablename__ = "family_memberships"

    user_id = Column(String(36), ForeignKey("users.id"), primary_key=True, comment="用户 ID")
    family_id = Column(String(8), ForeignKey("family_groups.id"), primary_key=True, comment="家庭组 ID")
    joined_at = Column(DateTime, server_default=func.now())

    def __repr__(self):
        return f"<FamilyMembership(user='{self.user_id}', family='{self.family_id}')>"
