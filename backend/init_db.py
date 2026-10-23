"""
初始化数据库表 + 数据迁移 —— 独立脚本
用法：cd backend && python init_db.py
"""
import asyncio
import os
from sqlalchemy import select, text
from app.db.session import engine, Base, BASE_DIR, AsyncSessionLocal
from app.models.card import Card, Conversation, ChatMessage  # noqa: F401
from app.models.folder import Folder  # noqa: F401
from app.models.profile import FamilyMember  # 家庭成员档案（si 保留）
from app.models.voice import CustomVoice  # 自定义音色（xia）
from app.models.family import User, FamilyGroup, FamilyMembership  # 家庭组（新增）


async def init_db():
    data_dir = os.path.join(BASE_DIR, "data")
    os.makedirs(data_dir, exist_ok=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print(f"✓ 数据库表创建成功（{BASE_DIR}/data/kinvoice.db）")


async def migrate_category_to_folder():
    """
    迁移旧数据：将 cards.category 转换为 folders + folder_id
    - 每个非空的 category 值创建同名文件夹
    - 设置对应 card 的 folder_id
    """
    async with AsyncSessionLocal() as session:
        # 检查 folders 表是否已有数据
        from sqlalchemy import func as sa_func
        f_result = await session.execute(select(sa_func.count(Folder.id)))
        folder_count = f_result.scalar() or 0
        if folder_count > 0:
            print(f"✓ 文件夹已存在 {folder_count} 个，跳过迁移")
            return

        # 获取所有非空 category 的卡片
        result = await session.execute(
            select(Card).where(Card.category.isnot(None), Card.category != "")
        )
        cards = result.scalars().all()
        if not cards:
            print("✓ 无需迁移（没有含 category 的旧卡片）")
            return

        # 收集唯一分类
        categories = list(set(c.category for c in cards if c.category))
        folder_map: dict[str, Folder] = {}

        for cat in categories:
            folder = Folder(name=cat, family_id="1")
            session.add(folder)
            await session.flush()
            folder_map[cat] = folder
            print(f"  创建文件夹: {cat} (id={folder.id})")

        # 设置 folder_id
        for card in cards:
            if card.category in folder_map:
                card.folder_id = folder_map[card.category].id

        await session.commit()
        print(f"✓ 迁移完成: {len(categories)} 个分类 → 文件夹, {len(cards)} 张卡片已关联")


async def migrate_conversation_user_id():
    """迁移：为 conversations 表添加 user_id 列（兼容旧数据库）"""
    async with engine.begin() as conn:
        # 检查列是否已存在
        result = await conn.execute(text("PRAGMA table_info(conversations)"))
        columns = [row[1] for row in result.fetchall()]
        if "user_id" in columns:
            print("✓ conversations.user_id 列已存在，跳过迁移")
            return
        await conn.execute(text("ALTER TABLE conversations ADD COLUMN user_id VARCHAR(36) DEFAULT '1'"))
        print("✓ 已为 conversations 表添加 user_id 列（默认值 '1'）")


async def migrate_family_id_to_string():
    """
    迁移：将 cards 和 conversations 的 family_id 从 Integer 改为 String(8)，
    与 family_groups.id (String(8)) 对齐。

    SQLite 不支持 ALTER COLUMN TYPE，需要重建表。
    """
    async with engine.begin() as conn:
        # 检查 cards.family_id 类型
        result = await conn.execute(text("PRAGMA table_info(cards)"))
        cards_cols = {row[1]: row[2] for row in result.fetchall()}
        cards_type = cards_cols.get("family_id", "").upper()

        # 检查 conversations.family_id 类型
        result = await conn.execute(text("PRAGMA table_info(conversations)"))
        conv_cols = {row[1]: row[2] for row in result.fetchall()}
        conv_type = conv_cols.get("family_id", "").upper()

        cards_need_migrate = "INT" in cards_type
        conv_need_migrate = "INT" in conv_type

        if not cards_need_migrate and not conv_need_migrate:
            print("✓ family_id 已是字符串类型，跳过迁移")
            return

        # ── 迁移 cards ──
        if cards_need_migrate:
            # 获取所有非主键列名
            result = await conn.execute(text("PRAGMA table_info(cards)"))
            all_cols = [row[1] for row in result.fetchall()]
            non_pk_cols = [c for c in all_cols if c != "id"]
            col_list = ", ".join(all_cols)
            non_pk_list = ", ".join(non_pk_cols)

            await conn.execute(text(f"""
                CREATE TABLE cards_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    {", ".join(f'{c} {"VARCHAR(8)" if c == "family_id" else cards_cols.get(c, "TEXT")}' for c in non_pk_cols)}
                )
            """))
            await conn.execute(text(f"INSERT INTO cards_new ({col_list}) SELECT {col_list} FROM cards"))
            await conn.execute(text("DROP TABLE cards"))
            await conn.execute(text("ALTER TABLE cards_new RENAME TO cards"))
            # 重建 FTS 触发器
            await conn.execute(text("DROP TRIGGER IF EXISTS cards_fts_ai"))
            await conn.execute(text("DROP TRIGGER IF EXISTS cards_fts_ad"))
            await conn.execute(text("DROP TRIGGER IF EXISTS cards_fts_au"))
            await conn.execute(text("DROP TABLE IF EXISTS cards_fts"))
            print("✓ cards.family_id 已迁移为 VARCHAR(8)")

        # ── 迁移 conversations ──
        if conv_need_migrate:
            result = await conn.execute(text("PRAGMA table_info(conversations)"))
            all_cols = [row[1] for row in result.fetchall()]
            non_pk_cols = [c for c in all_cols if c != "id"]
            col_list = ", ".join(all_cols)

            await conn.execute(text(f"""
                CREATE TABLE conversations_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    {", ".join(f'{c} {"VARCHAR(8)" if c == "family_id" else conv_cols.get(c, "TEXT")}' for c in non_pk_cols)}
                )
            """))
            await conn.execute(text(f"INSERT INTO conversations_new ({col_list}) SELECT {col_list} FROM conversations"))
            await conn.execute(text("DROP TABLE conversations"))
            await conn.execute(text("ALTER TABLE conversations_new RENAME TO conversations"))
            print("✓ conversations.family_id 已迁移为 VARCHAR(8)")

        # 重新初始化 FTS（卡片表被重建了）
        if cards_need_migrate:
            await init_fts()
            print("✓ FTS5 索引已重建")


async def init_fts():
    """创建 FTS5 全文检索虚拟表 + 触发器（用于陪伴页上下文检索）"""
    # 卡片 FTS5（精简：只索引 title + content + author）
    cards_fts_sql = [
        """CREATE VIRTUAL TABLE IF NOT EXISTS cards_fts USING fts5(
            title, content, author,
            content='cards', content_rowid='id'
        );""",
        """CREATE TRIGGER IF NOT EXISTS cards_fts_ai AFTER INSERT ON cards BEGIN
            INSERT INTO cards_fts(rowid, title, content, author)
            VALUES (new.id, new.title, new.content, new.author);
        END;""",
        """CREATE TRIGGER IF NOT EXISTS cards_fts_ad AFTER DELETE ON cards BEGIN
            INSERT INTO cards_fts(cards_fts, rowid, title, content, author)
            VALUES ('delete', old.id, old.title, old.content, old.author);
        END;""",
        """CREATE TRIGGER IF NOT EXISTS cards_fts_au AFTER UPDATE ON cards BEGIN
            INSERT INTO cards_fts(cards_fts, rowid, title, content, author)
            VALUES ('delete', old.id, old.title, old.content, old.author);
            INSERT INTO cards_fts(rowid, title, content, author)
            VALUES (new.id, new.title, new.content, new.author);
        END;""",
    ]

    # 对话消息 FTS5
    msgs_fts_sql = [
        """CREATE VIRTUAL TABLE IF NOT EXISTS chat_messages_fts USING fts5(
            content, role,
            content='chat_messages', content_rowid='id'
        );""",
        """CREATE TRIGGER IF NOT EXISTS chat_msgs_fts_ai AFTER INSERT ON chat_messages BEGIN
            INSERT INTO chat_messages_fts(rowid, content, role)
            VALUES (new.id, new.content, new.role);
        END;""",
        """CREATE TRIGGER IF NOT EXISTS chat_msgs_fts_ad AFTER DELETE ON chat_messages BEGIN
            INSERT INTO chat_messages_fts(chat_messages_fts, rowid, content, role)
            VALUES ('delete', old.id, old.content, old.role);
        END;""",
        """CREATE TRIGGER IF NOT EXISTS chat_msgs_fts_au AFTER UPDATE ON chat_messages BEGIN
            INSERT INTO chat_messages_fts(chat_messages_fts, rowid, content, role)
            VALUES ('delete', old.id, old.content, old.role);
            INSERT INTO chat_messages_fts(rowid, content, role)
            VALUES (new.id, new.content, new.role);
        END;""",
    ]

    # 重建已有数据的索引
    rebuild_sql = [
        "INSERT INTO cards_fts(rowid, title, content, author) SELECT id, title, content, author FROM cards;",
        "INSERT INTO chat_messages_fts(rowid, content, role) SELECT id, content, role FROM chat_messages;",
    ]

    async with engine.begin() as conn:
        for sql in cards_fts_sql + msgs_fts_sql:
            await conn.execute(text(sql))
        # 重建索引（FTS5 外部内容表需手动填充已有数据）
        for sql in rebuild_sql:
            try:
                await conn.execute(text(sql))
            except Exception:
                pass  # 表为空时忽略
    print("✓ FTS5 全文检索表创建完成")


async def migrate_cards_simplify():
    """
    迁移：精简 cards 表，删除不再需要的列。
    将旧 NVC 数据拼成 Markdown 存到 content 字段。
    """
    async with engine.begin() as conn:
        result = await conn.execute(text("PRAGMA table_info(cards)"))
        columns = {row[1] for row in result.fetchall()}

        # 需要删除的列
        cols_to_drop = [
            "type", "category", "emotion", "observation", "feeling", "need", "request",
            "conversation_id", "message_id", "original_text",
        ]
        existing_to_drop = [c for c in cols_to_drop if c in columns]

        if not existing_to_drop:
            print("✓ cards 表已精简，跳过迁移")
            return

        # 先把旧 NVC 数据合并到 content
        await conn.execute(text("""
            UPDATE cards SET content = TRIM(
                COALESCE(observation, '') || '\n\n' ||
                COALESCE(feeling, '') || '\n\n' ||
                COALESCE(need, '') || '\n\n' ||
                COALESCE(request, '') || '\n\n' ||
                COALESCE(content, '')
            )
            WHERE observation IS NOT NULL OR feeling IS NOT NULL
               OR need IS NOT NULL OR request IS NOT NULL
        """))

        # 保留的列
        keep_cols = ["id", "title", "content", "author", "folder_id", "family_id", "created_at", "updated_at"]
        keep_list = ", ".join(keep_cols)

        await conn.execute(text(f"""
            CREATE TABLE cards_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title VARCHAR(200),
                content TEXT,
                author VARCHAR(100),
                folder_id INTEGER REFERENCES folders(id),
                family_id VARCHAR(8) DEFAULT '1',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        await conn.execute(text(f"INSERT INTO cards_new ({keep_list}) SELECT {keep_list} FROM cards"))
        await conn.execute(text("DROP TABLE cards"))
        await conn.execute(text("ALTER TABLE cards_new RENAME TO cards"))
        print(f"✓ cards 表已精简（删除列: {existing_to_drop}）")


async def migrate_profile_user_id():
    """迁移：为 family_members 表添加 user_id 列 + 唯一索引"""
    async with engine.begin() as conn:
        result = await conn.execute(text("PRAGMA table_info(family_members)"))
        columns = {row[1] for row in result.fetchall()}
        if "user_id" in columns:
            print("✓ family_members.user_id 列已存在，跳过迁移")
            return
        await conn.execute(text("ALTER TABLE family_members ADD COLUMN user_id VARCHAR(64) DEFAULT '1'"))
        # 创建唯一索引（每个用户只能有一份档案）
        await conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_family_members_user_id ON family_members(user_id)"))
        print("✓ 已为 family_members 添加 user_id 列 + 唯一索引")


async def migrate_users_auth():
    """迁移：为 users 表添加 username 和 password_hash 列（账号密码登录）"""
    async with engine.begin() as conn:
        result = await conn.execute(text("PRAGMA table_info(users)"))
        columns = {row[1] for row in result.fetchall()}
        needs_migrate = False
        if "username" not in columns:
            await conn.execute(text("ALTER TABLE users ADD COLUMN username VARCHAR(50)"))
            needs_migrate = True
        if "password_hash" not in columns:
            await conn.execute(text("ALTER TABLE users ADD COLUMN password_hash VARCHAR(128)"))
            needs_migrate = True
        if needs_migrate:
            # 创建唯一索引
            try:
                await conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username ON users(username)"))
            except Exception:
                pass  # 索引已存在
            print("✓ users 表已添加 username + password_hash 列")
        else:
            print("✓ users.username/password_hash 列已存在，跳过迁移")


async def main():
    await init_db()
    await migrate_category_to_folder()
    await migrate_conversation_user_id()
    await migrate_family_id_to_string()
    await migrate_cards_simplify()
    await migrate_profile_user_id()
    await migrate_users_auth()
    await init_fts()


if __name__ == "__main__":
    asyncio.run(main())
