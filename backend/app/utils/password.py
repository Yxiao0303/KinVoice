"""
密码哈希工具 —— 使用 PBKDF2-SHA256（无需额外依赖）
"""
import hashlib
import secrets


def hash_password(password: str) -> str:
    """对密码做加盐哈希，返回 'salt$hash_hex' 格式"""
    salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000)
    return f"{salt}${h.hex()}"


def verify_password(password: str, hashed: str) -> bool:
    """验证密码是否匹配已存储的哈希"""
    try:
        salt, stored_hash = hashed.split("$", 1)
        h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000)
        return h.hex() == stored_hash
    except (ValueError, AttributeError):
        return False
