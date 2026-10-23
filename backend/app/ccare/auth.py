"""Isolated credential storage. Conversation content is never written here."""
import hashlib
import hmac
import secrets
import time
from pathlib import Path

import aiosqlite

ITERATIONS = 600000


def password_hash(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), ITERATIONS).hex()


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class AuthStore:
    def __init__(self, path: Path, ttl: int):
        self.path, self.ttl = path, ttl

    async def initialize(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.path) as db:
            await db.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL,
                    salt TEXT NOT NULL, password_hash TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions (
                    digest TEXT PRIMARY KEY, user_id TEXT NOT NULL, expires REAL NOT NULL);
            """)
            await db.execute("DELETE FROM sessions WHERE expires < ?", (time.time(),))
            await db.commit()

    async def register(self, username: str, password: str) -> str:
        # PBKDF2 runs outside the event loop through the API's thread pool.
        import asyncio
        salt, uid = secrets.token_hex(16), secrets.token_hex(16)
        digest = await asyncio.to_thread(password_hash, password, salt)
        async with aiosqlite.connect(self.path) as db:
            await db.execute("INSERT INTO users VALUES (?, ?, ?, ?)", (uid, username, salt, digest))
            await db.commit()
        return uid

    async def login(self, username: str, password: str) -> str | None:
        import asyncio
        async with aiosqlite.connect(self.path) as db:
            async with db.execute("SELECT id, salt, password_hash FROM users WHERE username=?", (username,)) as cursor:
                row = await cursor.fetchone()
        salt = row[1] if row else "00" * 16
        digest = await asyncio.to_thread(password_hash, password, salt)
        return row[0] if row and hmac.compare_digest(digest, row[2]) else None

    async def issue(self, uid: str) -> str:
        token = secrets.token_urlsafe(32)
        async with aiosqlite.connect(self.path) as db:
            await db.execute("DELETE FROM sessions WHERE expires < ?", (time.time(),))
            # One active session per account keeps this local prototype bounded.
            await db.execute("DELETE FROM sessions WHERE user_id=?", (uid,))
            await db.execute("INSERT INTO sessions SELECT ?, id, ? FROM users WHERE id=?", (token_hash(token), time.time() + self.ttl, uid))
            await db.commit()
        return token

    async def resolve(self, token: str) -> str | None:
        async with aiosqlite.connect(self.path) as db:
            async with db.execute("SELECT sessions.user_id FROM sessions JOIN users ON users.id=sessions.user_id WHERE digest=? AND expires>?", (token_hash(token), time.time())) as cursor:
                row = await cursor.fetchone()
        return row[0] if row else None

    async def revoke(self, token: str):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("DELETE FROM sessions WHERE digest=?", (token_hash(token),))
            await db.commit()

    async def erase(self, uid: str):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("PRAGMA secure_delete=ON")
            await db.execute("DELETE FROM sessions WHERE user_id=?", (uid,))
            await db.execute("DELETE FROM users WHERE id=?", (uid,))
            await db.commit()
