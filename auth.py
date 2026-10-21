"""Security primitives: password hashing, JWT, current user and rate limiting."""

from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from passlib.context import CryptContext
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_db
from exceptions import AuthenticationError, NotFoundError, PermissionDeniedError
from models import Project, User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/login")

limiter = Limiter(
    key_func=get_remote_address,
    enabled=settings.rate_limit_enabled,
    storage_uri=settings.rate_limit_storage_uri,
)


def _bcrypt_safe(password: str) -> str:
    """bcrypt only consumes the first 72 bytes."""
    encoded = password.encode("utf-8")[:72]
    return encoded.decode("utf-8", errors="ignore")


def hash_password(password: str) -> str:
    return pwd_context.hash(_bcrypt_safe(password))


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return pwd_context.verify(_bcrypt_safe(plain_password), hashed_password)
    except ValueError:
        return False


def create_access_token(subject: int, username: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(subject),
        "username": username,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except jwt.PyJWTError as exc:
        raise AuthenticationError("جلسة الدخول غير صالحة أو منتهية. يرجى تسجيل الدخول مجدداً.") from exc


async def authenticate_user(db: AsyncSession, username: str, password: str) -> User:
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(password, user.hashed_password):
        raise AuthenticationError("اسم المستخدم أو كلمة المرور غير صحيحة.")
    return user


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    payload = decode_access_token(token)
    subject = payload.get("sub")
    if subject is None:
        raise AuthenticationError("رمز الدخول لا يحتوي على هوية المستخدم.")
    try:
        user_id = int(subject)
    except (TypeError, ValueError) as exc:
        raise AuthenticationError("رمز الدخول غير صالح.") from exc

    user = await db.get(User, user_id)
    if user is None:
        raise AuthenticationError("الحساب المرتبط برمز الدخول غير موجود.")
    return user


async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "admin":
        raise PermissionDeniedError("هذه العملية متاحة للمدير العام فقط.")
    return current_user


def is_admin(user: User) -> bool:
    return user.role == "admin"


async def get_owned_project(db: AsyncSession, project_id: int, user: User) -> Project:
    """Fetch a project enforcing tenant isolation (admins may access all)."""
    query = select(Project).where(Project.id == project_id)
    if not is_admin(user):
        query = query.where(Project.owner_id == user.id)
    project = (await db.execute(query)).scalar_one_or_none()
    if project is None:
        raise NotFoundError("المشروع غير موجود أو لا تملك صلاحية الوصول إليه.")
    return project
