"""Security helpers — password hashing (bcrypt) + JWT sign/verify (auth foundation).

Design:
- bcrypt directly (no passlib wrapper, avoids passlib/bcrypt version warnings).
- JWT HS256, sub=user_id, role embedded for convenience; expiry from settings.
- Never expose password_hash in API payloads (FeedUser.to_dict omits it).
"""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import get_settings


def hash_password(password: str) -> str:
    """Return bcrypt hash (str) for a plaintext password."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Verify plaintext against a bcrypt hash. Empty/invalid hash -> False."""
    if not plain or not hashed:
        return False
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(user_id: str, role: str) -> str:
    """Sign a JWT access token for a user."""
    settings = get_settings()
    if not settings.JWT_SECRET:
        # 仓库不再留弱默认（2026-09-14 安全加固）：没配密钥就大声失败，别静默签出可伪造的 token
        raise ValueError("JWT_SECRET 未配置：请在 backend/.env 设置 JWT_SECRET")
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "role": role or "member",
        "iat": now,
        "exp": now + timedelta(minutes=settings.JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode + verify a JWT. Raises jwt.PyJWTError on invalid/expired."""
    settings = get_settings()
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
