"""
家庭成员档案 ORM 模型（每个用户只有一份自己的档案）
字段：id / user_id / name / relation / birth_date / avatar_url / content_md / created_at / updated_at
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, func
from app.db.session import Base


class FamilyMember(Base):
    __tablename__ = "family_members"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), nullable=False, index=True, default="1")  # 关联用户，唯一索引在 init_db 中
    name = Column(String(100), nullable=False, default="")
    relation = Column(String(50), nullable=False, default="本人")           # 关系（本人/父亲/母亲/...）
    birth_date = Column(String(20), nullable=True)                         # 生日：YYYY-MM-DD
    avatar_url = Column(String(500), nullable=True)                        # 头像链接（可选）
    content_md = Column(Text, nullable=False, default="")                  # Markdown 正文（档案详细内容）
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<FamilyMember(id={self.id}, user_id='{self.user_id}', name='{self.name}')>"
